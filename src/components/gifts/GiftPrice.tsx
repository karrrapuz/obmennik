import type { Gift } from '../../pages/ExchangePage/data/gifts';
import { isUnpricedGift } from '../../pages/ExchangePage/data/gifts';
import { hasMarketPrice, marketPriceLabel } from '../../services/telegramPrices';
import { formatNano } from '../../wallet/wallet';
import { useTelegramPrices } from '../../hooks/useTelegramPrices';
import tonIcon from '../../assets/ton.svg';
import './GiftPrice.css';

type PriceGift = Omit<Gift, 'price'> & { price: string | number };
export default function GiftPrice({ gift, referenceOnly = false }: { gift: PriceGift; referenceOnly?: boolean }) {
  const { now } = useTelegramPrices();
  if (!referenceOnly && !isUnpricedGift(gift)) return <><img src={tonIcon} alt="TON" />{typeof gift.price === 'number' ? gift.price.toFixed(3) : gift.price}</>;
  const fresh = hasMarketPrice(gift, now);
  return <span className="gift-price-reference" data-fresh={fresh} title={fresh ? 'Минимум среди проверенных объявлений коллекции, не оценка этого варианта' : undefined}>
    {fresh ? <>от <img src={tonIcon} alt="" />{formatNano(gift.marketPrice!.floorNano)} TON</> : marketPriceLabel(gift, now)}
  </span>;
}
