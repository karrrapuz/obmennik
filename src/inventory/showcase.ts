import extra from '../pages/ExchangePage/data/catalog-showcase-extra.json';
import { gifts, isUnpricedGift, type Gift } from '../pages/ExchangePage/data/gifts';

export const showcaseEnabled = import.meta.env.VITE_SHOWCASE_MODE !== 'false';
export const showcaseGifts: Gift[] = [...gifts, ...extra];

// This is a reversible presentation selection, never deletion of owned assets.
export function presentationCatalog(catalog: Gift[]): Gift[] {
  if (!showcaseEnabled) return catalog;
  const available = new Map(catalog.map(gift => [gift.id, gift]));
  return showcaseGifts.map(template => available.get(template.id) ?? template);
}

export function presentationOwned(list: Gift[]): Gift[] {
  return showcaseEnabled ? list.filter(gift => !isUnpricedGift(gift)) : list;
}
