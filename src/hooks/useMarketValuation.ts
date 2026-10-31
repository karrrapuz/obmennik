import { useEffect, useMemo, useState } from 'react';
import type { Gift } from '../pages/ExchangePage/data/gifts';
import { telegramAttributeKey, type TelegramCollection } from '../services/telegramCatalog';
import type { MarketPrice } from '../services/telegramPrices';

const apiUrl = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '');
const telegramId = (value: string) => /^[1-9]\d{0,18}$/.test(value) && BigInt(value) <= 9223372036854775807n;

export function marketValuationQuery(gift: Gift, collection: TelegramCollection, selected: Record<string, string[]>): string | null {
  if (gift.collectionId !== collection.telegramId || !telegramId(collection.telegramId)) return null;
  const query = new URLSearchParams({ collection_id: collection.telegramId });
  const actual: Record<string, string | undefined> = {
    models: gift.modelFilterId,
    symbols: gift.symbol?.id ? telegramAttributeKey('symbols', collection.telegramId, gift.symbol.id) : undefined,
    backdrops: gift.backdrop?.id !== undefined ? telegramAttributeKey('backdrops', collection.telegramId, gift.backdrop.id) : undefined,
  };
  for (const [kind, param] of [['models', 'model_id'], ['symbols', 'symbol_id'], ['backdrops', 'backdrop_id']] as const) {
    const values = selected[kind];
    if (values && values.length > 1) return null;
    const value = values?.[0] ?? actual[kind];
    if (!value) continue;
    const item = collection.attributes[kind].find(item => telegramAttributeKey(kind, collection.telegramId, item.id) === value);
    if (!item || (kind === 'backdrops'
      ? !Number.isInteger(item.id) || Number(item.id) < -2147483648 || Number(item.id) > 2147483647
      : !telegramId(String(item.id)))) return null;
    query.set(param, value);
  }
  return query.toString();
}

export function parseMarketValuation(raw: unknown, query: string, now = Math.floor(Date.now() / 1000)): MarketPrice | null {
  if (!raw || typeof raw !== 'object') throw new Error('Invalid market valuation');
  const value = raw as Record<string, unknown>;
  const params = new URLSearchParams(query);
  if (value.collectionId !== params.get('collection_id') || value.modelId !== params.get('model_id')
    || value.symbolId !== params.get('symbol_id') || value.backdropId !== params.get('backdrop_id')
    || value.source !== 'telegram-resale' || value.kind !== 'lowest_observed_listing'
    || value.readOnly !== true || value.guaranteedValuation !== false
    || !['available', 'stale', 'unknown'].includes(String(value.status))
    || !Number.isSafeInteger(value.sampleCount) || Number(value.sampleCount) < 0) throw new Error('Invalid market valuation');
  if (value.status === 'unknown') {
    if (value.floorNano !== null || value.sampleCount !== 0 || value.checkedAt !== null || value.ageSeconds !== null) throw new Error('Invalid unknown valuation');
    return null;
  }
  const { floorNano, checkedAt, validUntil, sampleCount, ageSeconds } = value;
  if (typeof floorNano !== 'string' || !/^[1-9]\d{0,14}$/.test(floorNano) || BigInt(floorNano) > 100000000000000n
    || typeof checkedAt !== 'number' || !Number.isSafeInteger(checkedAt) || checkedAt <= 0 || checkedAt > now + 60
    || typeof validUntil !== 'number' || !Number.isSafeInteger(validUntil) || validUntil <= checkedAt || validUntil > checkedAt + 86400
    || typeof sampleCount !== 'number' || sampleCount <= 0 || !Number.isSafeInteger(ageSeconds) || Number(ageSeconds) < 0
    || (value.status === 'available' && validUntil <= now) || (value.status === 'stale' && validUntil > now)) throw new Error('Invalid market valuation');
  return { floorNano, checkedAt, validUntil, sampleCount, source: 'telegram-resale', kind: 'lowest_observed_listing', hasMore: false };
}

export function applyMarketValuation<T extends Pick<Gift, 'marketPrice'>>(gift: T, result: { price: MarketPrice | null } | null, specific: boolean): T {
  if (!specific && gift.marketPrice && (!result?.price || gift.marketPrice.checkedAt > result.price.checkedAt)) return gift;
  return specific || result ? { ...gift, marketPrice: result?.price ?? undefined } : gift;
}

export function useMarketValuation(query: string | null) {
  // A new request identity prevents cached results resurfacing after close/reopen or A -> B -> A.
  const identity = useMemo(() => ({ query }), [query]);
  const [result, setResult] = useState<{ identity: typeof identity; price: MarketPrice | null } | null>(null);
  useEffect(() => {
    if (!query) return;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`${apiUrl}/api/market/valuation?${query}`, { signal: controller.signal, cache: 'no-store' });
        if (!response.ok) throw new Error('Market valuation unavailable');
        const price = parseMarketValuation(await response.json(), query);
        if (active) setResult({ identity, price });
      } catch { if (active) setResult({ identity, price: null }); }
      finally { clearTimeout(timer); }
    })();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [query, identity]);
  return result?.identity === identity ? result : null;
}
