import { isUnpricedGift, type Gift } from '../pages/ExchangePage/data/gifts';
import { formatNano, parseTon } from '../wallet/wallet';

export type MarketPrice = { floorNano: string; checkedAt: number; validUntil: number; source: 'telegram-resale'; kind: 'lowest_observed_listing'; sampleCount: number; hasMore: boolean };
export type PriceCollection = { telegramId: string; catalogId: number; checkedAt: number; status: 'available' | 'no_ton_listings' | 'not_collectible' | 'error'; floorNano: string | null; sampleCount: number; hasMore: boolean };
export type TelegramPrices = { schema: 1; source: 'telegram-resale'; kind: 'lowest_observed_listing'; capturedAt: number; validUntil: number; complete: boolean; collections: PriceCollection[] };
type PriceGift = Pick<Gift, 'marketPrice' | 'collectionId' | 'telegramCatalog' | 'tradeSupported' | 'priceSource'> & { price: string | number };
const MAX_NANO = 100_000_000_000_000n;
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value);
const timestamp = (value: unknown): value is number => integer(value) && value > 0 && value <= 8640000000000;
const positiveNano = (value: unknown): value is string => typeof value === 'string' && /^[1-9]\d{0,18}$/.test(value) && BigInt(value) <= MAX_NANO;
const telegramId = (value: unknown): value is string => typeof value === 'string' && /^[1-9]\d{0,19}$/.test(value) && BigInt(value) <= 18446744073709551615n;
const clockSkew = 60;

export function parseTelegramPrices(raw: unknown, now = Math.floor(Date.now() / 1000)): TelegramPrices {
  const feed = raw as TelegramPrices;
  if (!timestamp(now) || !feed || feed.schema !== 1 || feed.source !== 'telegram-resale' || feed.kind !== 'lowest_observed_listing'
    || typeof feed.complete !== 'boolean' || !timestamp(feed.capturedAt) || feed.capturedAt > now + clockSkew
    || !timestamp(feed.validUntil) || feed.validUntil <= feed.capturedAt || feed.validUntil > feed.capturedAt + 86400
    || !Array.isArray(feed.collections) || feed.collections.length > 1000) throw new Error('Invalid Telegram prices');
  const ids = new Set<string>(); const catalogIds = new Set<number>();
  for (const item of feed.collections) {
    if (!item || !telegramId(item.telegramId) || ids.has(item.telegramId) || !integer(item.catalogId) || item.catalogId < 100000 || catalogIds.has(item.catalogId)
      || !timestamp(item.checkedAt) || item.checkedAt < feed.capturedAt || item.checkedAt >= feed.validUntil || item.checkedAt > now + clockSkew
      || !['available', 'no_ton_listings', 'not_collectible', 'error'].includes(item.status)
      || !integer(item.sampleCount) || item.sampleCount < 0 || typeof item.hasMore !== 'boolean'
      || (item.status === 'available' ? !positiveNano(item.floorNano) || item.sampleCount === 0 : item.floorNano !== null || item.sampleCount !== 0)) throw new Error('Invalid Telegram collection price');
    ids.add(item.telegramId); catalogIds.add(item.catalogId);
  }
  return feed;
}

function validMarketPrice(gift: Pick<Gift, 'marketPrice'>, now: number): boolean {
  const price = gift.marketPrice;
  return Boolean(price && positiveNano(price.floorNano) && price.source === 'telegram-resale' && price.kind === 'lowest_observed_listing'
    && timestamp(price.checkedAt) && price.checkedAt <= now + clockSkew && timestamp(price.validUntil) && price.validUntil > price.checkedAt
    && price.validUntil <= price.checkedAt + 86400 && integer(price.sampleCount) && price.sampleCount > 0 && typeof price.hasMore === 'boolean');
}

export function hasMarketPrice(gift: Pick<Gift, 'marketPrice'>, now: number): boolean {
  return validMarketPrice(gift, now) && now < gift.marketPrice!.validUntil;
}

export function marketPriceLabel(gift: Pick<Gift, 'marketPrice' | 'marketStatus'>, now: number): string {
  if (hasMarketPrice(gift, now)) return `от ${formatNano(gift.marketPrice!.floorNano)} TON`;
  const price = gift.marketPrice;
  if (validMarketPrice(gift, now) && price && now >= price.validUntil) return 'Цена устарела';
  return gift.marketStatus === 'not_collectible' || gift.marketStatus === 'no_ton_listings' ? 'Нет предложений в TON' : 'Нет TON-цены';
}

export function mergeMarketPrices<T extends Pick<Gift, 'collectionId' | 'marketPrice' | 'marketStatus'>>(gifts: T[], feed: TelegramPrices | null, manifest: { collections: readonly { telegramId: string; catalogId: number }[] } | null): T[] {
  const prices = new Map(feed?.collections.map(item => [item.telegramId, item]) ?? []);
  const catalogIds = new Map(manifest?.collections.map(item => [item.telegramId, item.catalogId]) ?? []);
  return gifts.map(gift => {
    const { marketPrice: previous, marketStatus: previousStatus, ...rest } = gift;
    void previous;
    void previousStatus;
    const item = prices.get(gift.collectionId ?? '');
    if (!feed || !item || item.catalogId !== catalogIds.get(item.telegramId)) return rest as T;
    if (item.status !== 'available' || item.floorNano === null) return { ...rest, marketStatus: item.status } as T;
    return { ...rest, marketPrice: { floorNano: item.floorNano, checkedAt: item.checkedAt, validUntil: feed.validUntil, source: feed.source, kind: feed.kind, sampleCount: item.sampleCount, hasMore: item.hasMore } } as T;
  });
}

export function comparePriceAvailability(first: PriceGift, second: PriceGift, now: number): number {
  return Number(browsingPriceNano(first, now) === null) - Number(browsingPriceNano(second, now) === null);
}

export function browsingPriceNano(gift: PriceGift, now: number): bigint | null {
  if (isUnpricedGift(gift)) return hasMarketPrice(gift, now) ? BigInt(gift.marketPrice!.floorNano) : null;
  return parseTon(String(gift.price));
}

export function compareBrowsingPrices(first: PriceGift, second: PriceGift, direction: 'asc' | 'desc', now: number): number {
  const a = browsingPriceNano(first, now); const b = browsingPriceNano(second, now);
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  const comparison = a < b ? -1 : a > b ? 1 : 0;
  return direction === 'asc' ? comparison : -comparison;
}

export function matchesBrowsingPrice(gift: PriceGift, from: string, to: string, now: number): boolean {
  if (!from && !to) return true;
  const price = browsingPriceNano(gift, now);
  const minimum = from ? parseTon(from) : null; const maximum = to ? parseTon(to) : null;
  return price !== null && (!from || minimum !== null && price >= minimum) && (!to || maximum !== null && price <= maximum);
}
