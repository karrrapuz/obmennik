import manifest from './gift-media.json';
import type { Gift } from '../pages/ExchangePage/data/gifts';

const normalize = (name: string) => name.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');
const media = new Map(manifest.entries.map(entry => [`${entry.collectionId}:${normalize(entry.modelName)}`, entry]));
const posters = new Map(manifest.entries.map(entry => [entry.originalImage, entry.poster]));

export function upgradeGiftImage(image: string) {
  return posters.get(image) ?? image;
}

export function getGiftMedia(gift: Pick<Gift, 'collectionId' | 'modelName'>) {
  return gift.collectionId && gift.modelName ? media.get(`${gift.collectionId}:${normalize(gift.modelName)}`) : undefined;
}

export function giftPoster(gift: Pick<Gift, 'collectionId' | 'modelName' | 'image'>) {
  return getGiftMedia(gift)?.poster ?? gift.image;
}
