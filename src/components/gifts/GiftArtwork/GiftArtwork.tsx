import type { Gift } from '../../../pages/ExchangePage/data/gifts';
import placeholder from '../../../pages/ExchangePage/assets/gift.svg';
import './GiftArtwork.css';
export default function GiftArtwork({ gift }: { gift: Gift }) {
  return <div className="catalog-artwork" style={{ background: gift.backdrop ? `radial-gradient(ellipse at center, ${gift.backdrop.centerColor}, ${gift.backdrop.edgeColor})` : '#131313' }}>
    {gift.symbol?.image && <div className="catalog-artwork__pattern" style={{ backgroundColor: gift.backdrop?.patternColor ?? '#fff', maskImage: `url("${gift.symbol.image}")` }} />}
    <img src={gift.image || placeholder} alt={gift.name} loading="lazy" onError={(event) => { event.currentTarget.onerror = null; event.currentTarget.src = placeholder; }} />
  </div>;
}
