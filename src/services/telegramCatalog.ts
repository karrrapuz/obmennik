import { useEffect, useSyncExternalStore } from 'react';
import { type Gift, type FilterOption, getFilterOptions, giftCollectionKey, isUnpricedGift, matchesGiftCollection } from '../pages/ExchangePage/data/gifts';

export type TelegramModel = { id: string; name: string; image: string; rarity: string; crafted: boolean };
export type TelegramSymbol = { id: string; name: string; image: string; rarity: string };
export type TelegramBackdrop = { id: number; name: string; rarity: string; centerColor: string; edgeColor: string; patternColor: string; textColor: string };
export type TelegramCollection = { telegramId: string; catalogId: number; title: string; sourceTitle?: string | null; titleKind?: string; image: string; stars: string; firstSaleAt: number | null; upgradeAvailable: boolean; attributes: { models: TelegramModel[]; symbols: TelegramSymbol[]; backdrops: TelegramBackdrop[] } };
export type TelegramManifest = { schema: 1; importedAt: string; collections: TelegramCollection[]; halloweenCatalogIds: number[] };
type CatalogState = { manifest: TelegramManifest | null; error: boolean };
export type TelegramAttributeKind = 'models' | 'symbols' | 'backdrops';
export const telegramAttributeKey = (kind: TelegramAttributeKind, collectionId: string, attributeId: string | number) => kind === 'models' ? `tg:model:${collectionId}:${attributeId}` : `tg:${kind === 'symbols' ? 'symbol' : 'backdrop'}:${attributeId}`;
let state: CatalogState = { manifest: null, error: false };
let request: Promise<void> | undefined;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
const getSnapshot = () => state;
const string = (value: unknown): value is string => typeof value === 'string' && value.length <= 1024;
const id = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const media = (value: unknown): value is string => string(value) && (value.startsWith('/gifts/') || /^https:\/\//.test(value) || value === '');
const color = (value: unknown): value is string => typeof value === 'string' && /^#[\da-f]{6}$/i.test(value);
export function applyTelegramLabels(manifest: TelegramManifest, raw: unknown): TelegramManifest {
  const data = raw as { schema: number; labels: { telegramId: string; displayTitle: string; kind: string }[] };
  if (!data || data.schema !== 1 || !Array.isArray(data.labels) || data.labels.length > 1000) throw new Error('Invalid catalog labels');
  const titles = new Map<string, string>();
  for (const item of data.labels) {
    if (!item || typeof item.telegramId !== 'string' || !/^[1-9]\d{0,19}$/.test(item.telegramId) || titles.has(item.telegramId)
      || typeof item.displayTitle !== 'string' || !item.displayTitle.trim() || item.displayTitle.length > 120 || [...item.displayTitle].some(char => char.charCodeAt(0) < 32)
      || item.kind !== 'descriptive') throw new Error('Invalid catalog label');
    titles.set(item.telegramId, item.displayTitle.trim());
  }
  return { ...manifest, collections: manifest.collections.map(collection => collection.sourceTitle || !titles.has(collection.telegramId)
    ? collection : { ...collection, title: titles.get(collection.telegramId)!, titleKind: 'descriptive' }) };
}
function displayTitle(collection: TelegramCollection, previous?: string): string {
  return collection.sourceTitle || (collection.titleKind === 'descriptive' ? collection.title : previous && !/^Gift (?:\p{Extended_Pictographic}|\d)/u.test(previous) ? previous : collection.title);
}
export function parseTelegramManifest(raw: unknown): TelegramManifest {
  const value = raw as TelegramManifest;
  if (!value || value.schema !== 1 || !string(value.importedAt) || !Number.isFinite(Date.parse(value.importedAt))
    || !Array.isArray(value.collections) || value.collections.length > 1000 || !Array.isArray(value.halloweenCatalogIds)) throw new Error('Invalid Telegram catalog');
  const ids = new Set<number>(); const telegramIds = new Set<string>();
  for (const item of value.collections) {
    if (!item || !/^[1-9]\d{0,19}$/.test(item.telegramId) || BigInt(item.telegramId) > 18446744073709551615n
      || typeof item.telegramId !== 'string' || !id(item.catalogId) || item.catalogId <= 20 || ids.has(item.catalogId) || telegramIds.has(item.telegramId)
      || !string(item.title) || !item.title.trim() || !media(item.image) || typeof item.stars !== 'string' || !/^\d{1,20}$/.test(item.stars)
      || !(item.sourceTitle === undefined || item.sourceTitle === null || string(item.sourceTitle))
      || !(item.titleKind === undefined || ['official', 'descriptive', 'unavailable'].includes(item.titleKind))
      || !(item.firstSaleAt === null || (id(item.firstSaleAt) && item.firstSaleAt < 8640000000000)) || typeof item.upgradeAvailable !== 'boolean' || !item.attributes) throw new Error('Invalid Telegram collection');
    ids.add(item.catalogId); telegramIds.add(item.telegramId);
    for (const key of ['models', 'symbols', 'backdrops'] as const) {
      const attributes = item.attributes[key]; const seen = new Set<string | number>();
      if (!Array.isArray(attributes) || attributes.length > 20000) throw new Error('Invalid Telegram attributes');
      for (const attribute of attributes) {
        if (!attribute || !string(attribute.name) || !attribute.name.trim() || !string(attribute.rarity) || seen.has(attribute.id)
          || (key === 'backdrops' ? !Number.isSafeInteger(attribute.id) : typeof attribute.id !== 'string' || !/^[1-9]\d{0,19}$/.test(attribute.id))) throw new Error('Invalid Telegram attribute');
        if (key === 'backdrops') {
          const backdrop = attribute as TelegramBackdrop;
          if (![backdrop.centerColor, backdrop.edgeColor, backdrop.patternColor, backdrop.textColor].every(color)) throw new Error('Invalid Telegram backdrop');
        } else if (!media((attribute as TelegramModel).image) || (key === 'models' && typeof (attribute as TelegramModel).crafted !== 'boolean')) throw new Error('Invalid Telegram model');
        seen.add(attribute.id);
      }
    }
  }
  if (!value.halloweenCatalogIds.every(item => id(item) && ids.has(item)) || new Set(value.halloweenCatalogIds).size !== value.halloweenCatalogIds.length) throw new Error('Invalid seasonal catalog');
  return value;
}
export function loadTelegramCatalog(): Promise<void> {
  request ??= (async () => {
    try {
      const labels = fetch('/gifts/telegram/labels.json', { signal: AbortSignal.timeout(5000) })
        .then(response => response.ok ? response.json() as Promise<unknown> : null).catch(() => null);
      const response = await fetch('/gifts/telegram/catalog.json', { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error('Telegram catalog unavailable');
      let manifest = parseTelegramManifest(await response.json());
      try {
        const raw = await labels;
        if (raw) manifest = applyTelegramLabels(manifest, raw);
      } catch { /* Optional labels must not prevent catalog access. */ }
      state = { manifest, error: false };
    } catch { state = { manifest: null, error: true }; }
    listeners.forEach(listener => listener());
  })();
  return request;
}
export function useTelegramCatalog() {
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => { void loadTelegramCatalog(); }, []);
  return snapshot;
}
export function collectionGift(collection: TelegramCollection): Gift {
  return { id: collection.catalogId, name: collection.title, model: '—', price: '0.000', image: collection.image, collectionId: collection.telegramId, telegramCatalog: true, tradeSupported: false, pledgeSupported: false, priceSource: 'unpriced', stars: collection.stars };
}
export function mergeTelegramCatalog(catalog: Gift[], manifest: TelegramManifest | null): Gift[] {
  if (!manifest) return catalog;
  const byId = new Map(manifest.collections.map(item => [item.telegramId, item]));
  const used = new Set(catalog.map(gift => gift.id));
  return [...catalog.map(gift => { const collection = gift.collectionId ? byId.get(gift.collectionId) : undefined; return collection ? { ...gift, name: displayTitle(collection, gift.name) } : gift; }), ...manifest.collections.filter(item => !used.has(item.catalogId)).map(collectionGift)];
}
export function nameTelegramGifts(list: Gift[], manifest: TelegramManifest | null): Gift[] {
  if (!manifest) return list;
  const collections = new Map(manifest.collections.map(collection => [collection.telegramId, collection]));
  return list.map(gift => { const collection = collections.get(gift.collectionId ?? ''); return collection ? { ...gift, name: displayTitle(collection, gift.name) } : gift; });
}
export function previewTelegramGift(gift: Gift, collection: TelegramCollection | undefined, selected: Record<string, string[]>, source: 'inventory' | 'exchange' = 'exchange'): Gift | null {
  if (source === 'inventory' || !collection || !isUnpricedGift(gift)) return gift;
  if (!matchesGiftCollection(gift, selected.collection ?? [])) return null;
  const matches = (kind: TelegramAttributeKind, item: { id: string | number; name: string }) => selected[kind]?.includes(telegramAttributeKey(kind, collection.telegramId, item.id)) || selected[kind]?.includes(item.name);
  const model = selected.models?.length ? collection.attributes.models.find(item => matches('models', item)) : undefined;
  const symbol = selected.symbols?.length ? collection.attributes.symbols.find(item => matches('symbols', item)) : undefined;
  const backdrop = selected.backdrops?.length ? collection.attributes.backdrops.find(item => matches('backdrops', item)) : undefined;
  if ((selected.models?.length && !model) || (selected.symbols?.length && !symbol) || (selected.backdrops?.length && !backdrop)) return null;
  return { ...gift, ...(model ? { image: model.image || collection.image, modelName: model.name, modelFilterId: telegramAttributeKey('models', collection.telegramId, model.id) } : {}), ...(symbol ? { symbol } : {}), ...(backdrop ? { backdrop } : {}), previewOnly: Boolean(model || symbol || backdrop), tradeSupported: false, pledgeSupported: false };
}
export function telegramFilterOptions(catalog: Gift[], manifest: TelegramManifest | null, collections: string[]): Record<string, FilterOption[]> {
  const scoped = collections.length ? catalog.filter(gift => matchesGiftCollection(gift, collections)) : catalog;
  const options = getFilterOptions(scoped);
  const byKey = new Map(catalog.map(gift => [giftCollectionKey(gift), gift]));
  options.collection = getFilterOptions(catalog).collection.map(option => {
    const gift = byKey.get(option.value ?? option.name);
    if (!gift || !isUnpricedGift(gift)) return option;
    return { ...option, price: undefined, description: `${gift.stars ?? manifest?.collections.find(item => item.telegramId === gift.collectionId)?.stars ?? '—'} Stars · ID ${gift.collectionId ?? gift.id}` };
  });
  const available = new Set(scoped.map(gift => gift.collectionId));
  const maps = Object.fromEntries(Object.entries(options).map(([key, values]) => [key, new Map(values.map(option => [option.value ?? option.name, option]))]));
  const raritySets = new Map<string, Set<string>>();
  const recordRarity = (key: string, rarity: string) => { const values = raritySets.get(key) ?? new Set<string>(); values.add(rarity); raritySets.set(key, values); return values.size === 1 ? rarity : undefined; };
  for (const collection of manifest?.collections ?? []) {
    if (!available.has(collection.telegramId)) continue;
    for (const model of collection.attributes.models) { const value = telegramAttributeKey('models', collection.telegramId, model.id); maps.models.set(value, { value, name: model.name, description: collection.title, image: model.image, rarity: model.rarity }); }
    for (const symbol of collection.attributes.symbols) { const value = telegramAttributeKey('symbols', collection.telegramId, symbol.id); maps.symbols.set(value, { value, name: symbol.name, image: symbol.image, rarity: recordRarity(value, symbol.rarity) }); }
    for (const backdrop of collection.attributes.backdrops) { const value = telegramAttributeKey('backdrops', collection.telegramId, backdrop.id); maps.backdrops.set(value, { value, name: backdrop.name, color: backdrop.centerColor, rarity: recordRarity(value, backdrop.rarity) }); }
  }
  return Object.fromEntries(Object.entries(maps).map(([key, values]) => [key, [...values.values()]]));
}
