import { useEffect, useSyncExternalStore } from 'react';
import { type Gift, type FilterOption, getFilterOptions, giftCollectionKey, isUnpricedGift, matchesGiftCollection } from '../pages/ExchangePage/data/gifts';

export type TelegramModel = { id: string; name: string; image: string; rarity: string; crafted: boolean };
export type TelegramSymbol = { id: string; name: string; image: string; rarity: string };
export type TelegramBackdrop = { id: number; name: string; rarity: string; centerColor: string; edgeColor: string; patternColor: string; textColor: string };
export type TelegramCollection = { telegramId: string; catalogId: number; title: string; image: string; stars: string; firstSaleAt: number | null; upgradeAvailable: boolean; attributes: { models: TelegramModel[]; symbols: TelegramSymbol[]; backdrops: TelegramBackdrop[] } };
export type TelegramManifest = { schema: 1; importedAt: string; collections: TelegramCollection[]; halloweenCatalogIds: number[] };
type CatalogState = { manifest: TelegramManifest | null; error: boolean };
let state: CatalogState = { manifest: null, error: false };
let request: Promise<void> | undefined;
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
const getSnapshot = () => state;
const string = (value: unknown): value is string => typeof value === 'string' && value.length <= 1024;
const id = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0;
const media = (value: unknown): value is string => string(value) && (value.startsWith('/gifts/') || /^https:\/\//.test(value) || value === '');
const color = (value: unknown): value is string => typeof value === 'string' && /^#[\da-f]{6}$/i.test(value);
export function parseTelegramManifest(raw: unknown): TelegramManifest {
  const value = raw as TelegramManifest;
  if (!value || value.schema !== 1 || !string(value.importedAt) || !Number.isFinite(Date.parse(value.importedAt))
    || !Array.isArray(value.collections) || value.collections.length > 1000 || !Array.isArray(value.halloweenCatalogIds)) throw new Error('Invalid Telegram catalog');
  const ids = new Set<number>(); const telegramIds = new Set<string>();
  for (const item of value.collections) {
    if (!item || !/^[1-9]\d{0,19}$/.test(item.telegramId) || BigInt(item.telegramId) > 18446744073709551615n
      || typeof item.telegramId !== 'string' || !id(item.catalogId) || item.catalogId <= 20 || ids.has(item.catalogId) || telegramIds.has(item.telegramId)
      || !string(item.title) || !item.title.trim() || !media(item.image) || typeof item.stars !== 'string' || !/^\d{1,20}$/.test(item.stars)
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
      const response = await fetch('/gifts/telegram/catalog.json', { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error('Telegram catalog unavailable');
      state = { manifest: parseTelegramManifest(await response.json()), error: false };
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
  const byId = new Map(manifest.collections.map(item => [item.catalogId, item]));
  const used = new Set(catalog.map(gift => gift.id));
  return [...catalog.map(gift => { const collection = byId.get(gift.id); return collection ? { ...gift, ...collectionGift(collection) } : gift; }), ...manifest.collections.filter(item => !used.has(item.catalogId)).map(collectionGift)];
}
export function previewTelegramGift(gift: Gift, collection: TelegramCollection | undefined, selected: Record<string, string[]>): Gift | null {
  if (!collection || !isUnpricedGift(gift)) return gift;
  if (!matchesGiftCollection(gift, selected.collection ?? [])) return null;
  const model = selected.models?.length ? collection.attributes.models.find(item => selected.models.includes(item.name)) : undefined;
  const symbol = selected.symbols?.length ? collection.attributes.symbols.find(item => selected.symbols.includes(item.name)) : undefined;
  const backdrop = selected.backdrops?.length ? collection.attributes.backdrops.find(item => selected.backdrops.includes(item.name)) : undefined;
  if ((selected.models?.length && !model) || (selected.symbols?.length && !symbol) || (selected.backdrops?.length && !backdrop)) return null;
  return { ...gift, ...(model ? { image: model.image || collection.image, modelName: model.name } : {}), ...(symbol ? { symbol } : {}), ...(backdrop ? { backdrop } : {}), previewOnly: Boolean(model || symbol || backdrop), tradeSupported: false, pledgeSupported: false };
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
  for (const collection of manifest?.collections ?? []) {
    if (!available.has(collection.telegramId)) continue;
    for (const model of collection.attributes.models) maps.models.set(model.name, { name: model.name, image: model.image, rarity: model.rarity });
    for (const symbol of collection.attributes.symbols) maps.symbols.set(symbol.name, { name: symbol.name, image: symbol.image, rarity: symbol.rarity });
    for (const backdrop of collection.attributes.backdrops) maps.backdrops.set(backdrop.name, { name: backdrop.name, color: backdrop.centerColor, rarity: backdrop.rarity });
  }
  return Object.fromEntries(Object.entries(maps).map(([key, values]) => [key, [...values.values()]]));
}
