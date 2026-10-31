import sample from './catalog-sample.json';
export type Gift = {
  id: number; name: string; model: string; price: string;
  collectionId?: string; modelName?: string; image?: string; blockTradeGift?: boolean; pledgeSupported?: boolean;
  telegramCatalog?: boolean; tradeSupported?: boolean; priceSource?: string; stars?: string; previewOnly?: boolean;
  symbol?: { name: string; image: string; rarity: string };
  backdrop?: { name: string; rarity: string; centerColor: string; edgeColor: string; patternColor: string; textColor: string };
};
export const isUnpricedGift = (gift: Pick<Gift, 'telegramCatalog' | 'tradeSupported' | 'priceSource'>) => gift.telegramCatalog === true || gift.tradeSupported === false || gift.priceSource === 'unpriced';
export const giftCollectionKey = (gift: Pick<Gift, 'collectionId' | 'name'>) => gift.collectionId ? `telegram:${gift.collectionId}` : gift.name;
export const matchesGiftCollection = (gift: Pick<Gift, 'collectionId' | 'name'>, values: string[]) => !values.length || values.includes(giftCollectionKey(gift)) || values.includes(gift.name);
export const gifts: Gift[] = sample.map((gift, index) => ({ ...gift, blockTradeGift: index === 0 }));
export const inventoryGifts: Gift[] = sample.slice(0, 5).map((gift, index) => ({ ...gift, id: 101 + index, model: `#${9998 - index}`, pledgeSupported: index < 3 }));
export function matchesGiftAttributes(gift: Gift, selected: Record<string, string[]>) {
  const attributes: Record<string, string | undefined> = { collection: gift.name, models: gift.modelName, symbols: gift.symbol?.name, backdrops: gift.backdrop?.name };
  return Object.entries(selected).every(([key, values]) => key === 'collection' ? matchesGiftCollection(gift, values) : !values.length || values.includes(attributes[key] ?? ''));
}
export type FilterOption = { name: string; value?: string; description?: string; price?: string; rarity?: string; image?: string; color?: string };
export function getFilterOptions(list: Gift[]): Record<string, FilterOption[]> {
  const result: Record<string, FilterOption[]> = { collection: [], models: [], symbols: [], backdrops: [] };
  for (const gift of list) {
    const options: Record<string, FilterOption> = {
      collection: { name: gift.name, value: giftCollectionKey(gift), image: gift.image, price: isUnpricedGift(gift) ? undefined : gift.price },
      models: { name: gift.modelName ?? '', image: gift.image },
      symbols: { name: gift.symbol?.name ?? '', image: gift.symbol?.image, rarity: gift.symbol?.rarity },
      backdrops: { name: gift.backdrop?.name ?? '', color: gift.backdrop?.centerColor, rarity: gift.backdrop?.rarity },
    };
    for (const [key, option] of Object.entries(options)) if (option.name && !result[key].some((entry) => (entry.value ?? entry.name) === (option.value ?? option.name))) result[key].push(option);
  }
  return result;
}
