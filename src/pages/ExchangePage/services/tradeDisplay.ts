import { parseTon } from '../../../wallet/wallet';
import type { TradeQuote } from '../hooks/useTradeQuote';

type PricedGift = { id: number; price: string };

export function tradeDisplayTotals(offered: PricedGift[], received: PricedGift[], quote: TradeQuote | null) {
  const sum = (gifts: PricedGift[]) => gifts.reduce((total, gift) => total + (parseTon(gift.price) ?? 0n), 0n);
  const same = (actual: number[], gifts: PricedGift[]) => actual.length === gifts.length && gifts.every(gift => actual.includes(gift.id));
  const current = quote && quote.expires_at * 1000 > Date.now() && same(quote.offered.map(item => item.gift_id), offered)
    && same(quote.received.map(item => item.catalog_id), received) ? quote : null;
  const offeredNano = current ? BigInt(current.offered_nano) : sum(offered);
  const receivedNano = current ? BigInt(current.received_nano) : sum(received);
  return { offeredNano, receivedNano, requiredNano: receivedNano > offeredNano ? receivedNano - offeredNano : 0n };
}
