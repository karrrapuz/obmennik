import type { Gift } from '../pages/ExchangePage/data/gifts';

export type PresentationBackdrop = {
  centerColor: string;
  edgeColor: string;
  patternColor: string;
  textColor: string;
};

export type GiftPresentation = {
  kind: 'decorative';
  backdrop: PresentationBackdrop;
  symbol?: { image: string };
};

// Existing Telegram backdrop colors, not collectible attributes of the gift.
const palettes: readonly PresentationBackdrop[] = [
  { centerColor: '#b2aea7', edgeColor: '#88847e', patternColor: '#3d382d', textColor: '#e9e7e2' },
  { centerColor: '#adb070', edgeColor: '#6b7d54', patternColor: '#39501b', textColor: '#d3e6bb' },
  { centerColor: '#ca70c6', edgeColor: '#9662d4', patternColor: '#620fb4', textColor: '#ebceff' },
  { centerColor: '#44826b', edgeColor: '#2f6369', patternColor: '#002624', textColor: '#b7e6d3' },
  { centerColor: '#58b4c8', edgeColor: '#538bc2', patternColor: '#07609b', textColor: '#cde8fd' },
  { centerColor: '#e7a75a', edgeColor: '#c5675f', patternColor: '#ad0e00', textColor: '#ffe4d7' },
  { centerColor: '#da896b', edgeColor: '#c4654f', patternColor: '#891200', textColor: '#ffd9d2' },
  { centerColor: '#5c6985', edgeColor: '#354057', patternColor: '#030a18', textColor: '#bfcce0' },
];

const colorPattern = /^#[0-9a-f]{6}$/i;

function validPresentation(value: GiftPresentation | undefined): value is GiftPresentation {
  return value?.kind === 'decorative' && !!value.backdrop
    && [value.backdrop.centerColor, value.backdrop.edgeColor, value.backdrop.patternColor, value.backdrop.textColor]
      .every(color => typeof color === 'string' && colorPattern.test(color));
}

function validDecorativeSymbol(value: unknown): value is { image: string } {
  if (!value || typeof value !== 'object' || !('image' in value)) return false;
  const image = value.image;
  if (typeof image !== 'string' || !image || /[\s\x00-\x1f\x7f"'\\()<>]/.test(image)) return false;
  if (image.startsWith('/') && !image.startsWith('//')) return true;
  if (!image.startsWith('https://')) return false;
  try {
    const url = new URL(image);
    return !!url.hostname && !url.username && !url.password;
  } catch {
    return false;
  }
}

type PresentableGift = Pick<Gift, 'collectionId' | 'telegramCatalog' | 'priceSource' | 'presentation' | 'backdrop' | 'symbol'>;

export function getGiftPresentation(gift: PresentableGift): {
  backdrop?: PresentationBackdrop;
  symbol?: { image: string };
} {
  const imported = gift.telegramCatalog === true || gift.priceSource === 'unpriced';
  let decorative: GiftPresentation | undefined;
  if (imported) {
    if (validPresentation(gift.presentation)) decorative = gift.presentation;
    else if (gift.collectionId) {
      let hash = 0;
      for (let index = 0; index < gift.collectionId.length; index++) {
        hash = (Math.imul(hash, 31) + gift.collectionId.charCodeAt(index)) >>> 0;
      }
      decorative = { kind: 'decorative', backdrop: palettes[hash % palettes.length] };
    }
  }
  return {
    backdrop: gift.backdrop ?? decorative?.backdrop,
    symbol: gift.symbol ?? (validDecorativeSymbol(decorative?.symbol) ? decorative.symbol : undefined),
  };
}
