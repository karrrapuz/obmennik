import { compareBrowsingPrices, comparePriceAvailability } from '../../../services/telegramPrices';
import type { SortOption } from '../components/SortModal/SortModal';
import type { Gift } from '../data/gifts';

function modelRarity(gift: Gift) {
  const value = gift.modelRarity?.trim();
  return value && /^\d+(?:[.,]\d+)?\s*%$/.test(value)
    ? Number(value.slice(0, -1).replace(',', '.'))
    : NaN;
}

function compareRarity(first: Gift, second: Gift, descending: boolean) {
  const a = modelRarity(first);
  const b = modelRarity(second);
  if (!Number.isFinite(a) || !Number.isFinite(b)) {
    return Number(Number.isFinite(b)) - Number(Number.isFinite(a));
  }
  return descending ? b - a : a - b;
}

export function compareExchangeGifts(first: Gift, second: Gift, section: 'inventory' | 'exchange', options: readonly SortOption[], now: number) {
  if (options.length === 0) {
    if (section === 'inventory') return 0;
    return Number(Boolean(second.telegramSlug)) - Number(Boolean(first.telegramSlug))
      || comparePriceAvailability(first, second, now);
  }

  for (const option of options) {
    let difference = 0;
    if (option === 'newest') difference = second.id - first.id;
    if (option === 'price-asc') difference = compareBrowsingPrices(first, second, 'asc', now);
    if (option === 'price-desc') difference = compareBrowsingPrices(first, second, 'desc', now);
    if (option === 'rarity-asc' || option === 'rarity-desc') {
      difference = compareRarity(first, second, option === 'rarity-desc');
    }
    if (difference !== 0) return difference;
  }
  return 0;
}
