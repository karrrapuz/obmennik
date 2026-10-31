import type { Gift } from '../../../pages/ExchangePage/data/gifts';
import placeholder from '../../../pages/ExchangePage/assets/gift.svg';
import { getGiftPresentation } from '../../../services/giftPresentation';
import './GiftArtwork.css';
export default function GiftArtwork({ gift }: { gift: Gift }) {
  const { backdrop, symbol } = getGiftPresentation(gift);
  return <div className="catalog-artwork" style={{ background: backdrop ? `radial-gradient(ellipse at center, ${backdrop.centerColor}, ${backdrop.edgeColor})` : '#131313' }}>
    {symbol?.image && <div className="catalog-artwork__pattern" style={{ backgroundColor: backdrop?.patternColor ?? '#fff', maskImage: `url("${symbol.image}")` }} />}
    <img src={gift.image || placeholder} alt={gift.name} loading="lazy" onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = placeholder; }} />
  </div>;
}
