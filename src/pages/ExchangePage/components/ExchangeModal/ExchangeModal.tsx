import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import GiftArtwork from '../../../../components/gifts/GiftArtwork/GiftArtwork';
import activeGiftIcon from '../../assets/obmen_gift_active.svg';
import tonIcon from '../../../../assets/ton.svg';
import closeIcon from '../FilterModal/assets/Union.svg';
import deleteGiftIcon from './deleta-gift.svg';
import ShortageNotice from '../ShortageNotice/ShortageNotice';
import './ExchangeModal.css';
import successIcon from '../../../ProfilePage/assets/yspeh_galoshka.svg';
import errorIcon from '../../../ProfilePage/assets/oshibka_krestik.svg';
import type { useTradeQuote } from '../../hooks/useTradeQuote';
import { formatNano } from '../../../../wallet/wallet';

type ExchangeGift = {
  id: number;
  name: string;
  model: string;
  price: string;
  blockTradeGift?: boolean;
};

type ExchangeModalProps = {
  trade: ReturnType<typeof useTradeQuote>;
  open: boolean;
  gifts: ExchangeGift[];
  offeredGifts: ExchangeGift[];
  offeredAmount: number;
  receivedAmount: number;
  onRemove: (id: number, side: 'offer' | 'receive') => void;
  onClear: (side: 'offer' | 'receive') => void;
  onClose: () => void;
  onSuccess: () => Promise<void>;
};

const formatAmount = (amount: number) => amount.toFixed(3);

const getGiftWord = (count: number) => {
  const lastTwoDigits = count % 100;
  if (lastTwoDigits >= 11 && lastTwoDigits <= 14) return 'подарков';
  const lastDigit = count % 10;
  if (lastDigit === 1) return 'подарок';
  if (lastDigit >= 2 && lastDigit <= 4) return 'подарка';
  return 'подарков';
};

function ExchangeModal({ trade, open, gifts, offeredGifts, offeredAmount, receivedAmount, onRemove, onClear, onClose, onSuccess }: ExchangeModalProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const [notice, setNotice] = useState(false);
  const [result, setResult] = useState<'success' | 'error' | null>(null);
  const [receivedCount, setReceivedCount] = useState(0);
  const [pending, setPending] = useState(false);
  const submitted = useRef(false);
  const [activeSide, setActiveSide] = useState<'offer' | 'receive'>('receive');
  const modalRef = useRef<HTMLElement>(null);
  const [noticeOverGifts, setNoticeOverGifts] = useState(false);

  useLayoutEffect(() => {
    const modal = modalRef.current;
    if (!mounted || !modal) return;
    const list = modal.querySelector<HTMLElement>('.exchange-modal__gifts');
    const notification = modal.querySelector<HTMLElement>('.exchange-modal__shortage');
    if (!list || !notification) {
      setNoticeOverGifts(false);
      return;
    }

    // Стекло включается только над видимой частью карточек, с учётом прокрутки.
    const updateOverlap = () => {
      const bounds = notification.getBoundingClientRect();
      const viewport = list.getBoundingClientRect();
      const overlaps = Array.from(list.children).some((card) => {
        const rect = card.getBoundingClientRect();
        return Math.max(rect.top, viewport.top, bounds.top) < Math.min(rect.bottom, viewport.bottom, bounds.bottom)
          && Math.max(rect.left, viewport.left, bounds.left) < Math.min(rect.right, viewport.right, bounds.right);
      });
      setNoticeOverGifts(overlaps);
    };
    updateOverlap();
    const observer = new ResizeObserver(updateOverlap);
    observer.observe(modal);
    observer.observe(list);
    list.addEventListener('scroll', updateOverlap, { passive: true });
    notification.addEventListener('transitionend', updateOverlap);
    return () => {
      observer.disconnect();
      list.removeEventListener('scroll', updateOverlap);
      notification.removeEventListener('transitionend', updateOverlap);
    };
  }, [mounted, activeSide, gifts.length, offeredGifts.length]);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setNotice(false);
      setResult(null);
      submitted.current = false;
      setActiveSide('receive');
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
      return () => cancelAnimationFrame(frame);
    }
    setVisible(false);
  }, [open]);

  useEffect(() => {
    if (!mounted) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [mounted, onClose]);

  if (!mounted) return null;

  const displayedGifts = activeSide === 'receive' ? gifts : offeredGifts;
  const shortage = Math.max(receivedAmount - offeredAmount, 0);
  const hasBlockedGift = gifts.some((gift) => gift.blockTradeGift);
  const submit = async () => {
    if (submitted.current) return;
    if (hasBlockedGift) return;
    const offer = offeredGifts.reduce((sum, gift) => sum + Number(gift.price), 0);
    const receive = gifts.reduce((sum, gift) => sum + Number(gift.price), 0);
    if (trade.server ? !trade.uncertain && !trade.canExecute : !gifts.length || !offeredGifts.length || offer + 0.000001 < receive) { setNotice(true); return; }
    submitted.current = true;
    setReceivedCount(gifts.length);
    setPending(true);
    try { await onSuccess(); setResult('success'); } catch { if (!trade.server) setResult('error'); }
    finally { setPending(false); submitted.current = false; }
  };

  return createPortal(
    <div className="exchange-modal-layer" data-visible={visible} onTransitionEnd={(event) => {
      if (event.target === event.currentTarget && !open) setMounted(false);
    }}>
      <button className="exchange-modal-scrim" type="button" aria-label="Закрыть обмен" onClick={onClose} />
      <section ref={modalRef} className="exchange-modal" data-server={trade.server} data-result={result ?? undefined} role="dialog" aria-modal="true" aria-label={result === 'success' ? 'Успешно!' : result === 'error' ? 'Ошибка' : 'Обмен'}>
        <div className="exchange-modal__handle" aria-hidden="true" />
        {result ? <div className="exchange-result">
          <h2>{result === 'success' ? 'Успешно!' : 'Ошибка'}</h2>
          <button className="exchange-modal__close" aria-label="Закрыть" onClick={onClose}><img src={closeIcon} alt="" /></button>
          <div className="exchange-result__icon"><img src={result === 'success' ? successIcon : errorIcon} alt="" /></div>
          <p role="status">{result === 'success' ? receivedCount === 1 ? 'Подарок добавлен в инвентарь.' : 'Подарки добавлены в инвентарь.' : 'Не удалось выполнить обмен. Повторите попытку.'}</p>
          <button className="exchange-result__return" onClick={onClose}>{result === 'success' ? 'Вернуться к обмену' : 'Выбрать другой'}</button>
        </div> : <>
        <header className="exchange-modal__header">
          <h2>Обмен</h2>
          <button className="exchange-modal__close" type="button" aria-label="Закрыть обмен" onClick={onClose}><img src={closeIcon} alt="" /></button>
          <div className="exchange-modal__totals">
            <button className="exchange-modal__total" type="button" data-active={activeSide === 'offer'} data-muted={offeredAmount < receivedAmount} aria-pressed={activeSide === 'offer'} onClick={() => setActiveSide('offer')}>
              <span>Предлагаете</span><strong><img src={tonIcon} alt="" />{trade.server ? trade.quote ? formatNano(trade.quote.offered_nano) : '—' : formatAmount(offeredAmount)}</strong>
            </button>
            <button className="exchange-modal__total exchange-modal__total--receive" type="button" data-active={activeSide === 'receive'} data-muted={gifts.length === 0} aria-pressed={activeSide === 'receive'} onClick={() => setActiveSide('receive')}>
              <span>Получаете</span><strong><img src={tonIcon} alt="" />{trade.server ? trade.quote ? formatNano(trade.quote.received_nano) : '—' : formatAmount(receivedAmount)}</strong>
            </button>
          </div>
          <div className="exchange-modal__tools">
            <div className="exchange-modal__quantity"><span><img src={activeGiftIcon} alt="" /></span>{displayedGifts.length} {getGiftWord(displayedGifts.length)}</div>
            <button type="button" onClick={() => { onClear(activeSide); setNotice(false); }} disabled={pending || trade.locked || displayedGifts.length === 0}>Очистить</button>
          </div>
        </header>
        {displayedGifts.length === 0 ? <p className="exchange-modal__empty">{activeSide === 'offer' ? 'Вы ничего не предлагаете' : 'Вы ничего не получаете'}</p> : (
          <div className="exchange-modal__gifts">
            {displayedGifts.map((gift) => <article className={`exchange-modal__gift${gift.blockTradeGift ? ' block-trade-gift' : ''}`} aria-label={gift.blockTradeGift ? `${gift.name}: уже обменяли` : undefined} key={gift.id}>
              <div className="exchange-modal__visual" style={{ position: 'relative' }}><GiftArtwork gift={gift} /></div>
              <strong>{gift.name}</strong>
              <span className="exchange-modal__model"><span>Модель</span><span>{gift.model}</span></span>
              <span className="exchange-modal__price">
                <span className="exchange-modal__ton"><img src={tonIcon} alt="" /></span>
                <span className="exchange-modal__price-value">{trade.server ? (() => { const unit = activeSide === 'offer' ? trade.quote?.offered.find(item => item.gift_id === gift.id)?.unit_nano : trade.quote?.received.find(item => item.catalog_id === gift.id)?.unit_nano; return unit ? formatNano(unit) : '—'; })() : gift.price}</span>
              </span>
              <button className="exchange-modal__remove" type="button" disabled={pending || trade.locked} aria-label={`Удалить ${gift.name}`} onClick={() => onRemove(gift.id, activeSide)}><img src={deleteGiftIcon} alt="" /></button>
            </article>)}
          </div>
        )}
        <ShortageNotice
          className="exchange-modal__shortage"
          label="Вам не хватает:"
          amount={shortage}
          visible={!trade.server && !hasBlockedGift && shortage > 0.0005}
          glass={noticeOverGifts}
        />
        {hasBlockedGift && <p className="exchange-modal__blocked-notice" role="status">Выбранный вами подарок уже обменяли, пожалуйста выберите другой!</p>}
        {!hasBlockedGift && notice && <p className="exchange-modal__notice" role="status">{offeredGifts.length === 0 ? 'Для обмена добавьте подарок из инвентаря' : 'Стоимость предлагаемых подарков меньше получаемых'}</p>}
        {trade.server && <div className="exchange-modal__quote" role="status">
          {trade.quote && <span>Наценка {trade.quote.markup_bps / 100}%<br />{BigInt(trade.quote.wallet_delta_nano) < 0n ? `Доплата: ${formatNano(-BigInt(trade.quote.wallet_delta_nano))} TON` : BigInt(trade.quote.wallet_delta_nano) > 0n ? `Остаток на баланс: ${formatNano(trade.quote.wallet_delta_nano)} TON` : 'Без доплаты'}<br />Нужно на балансе: {formatNano(trade.quote.required_balance_nano)} · {trade.expired ? 'Котировка истекла' : `До ${new Date(trade.quote.expires_at * 1000).toLocaleTimeString('ru-RU')}`}</span>}
          {trade.loading ? <span>Расчёт котировки…</span> : <span>{trade.error}</span>}
          {!trade.locked && <button type="button" onClick={trade.refresh} disabled={trade.loading}>Обновить котировку</button>}
        </div>}
        <button className="exchange-modal__submit" type="button" disabled={pending || trade.pending || (trade.server ? !trade.uncertain && !trade.canExecute : gifts.length === 0)} aria-disabled={hasBlockedGift || gifts.length === 0} onClick={submit}>{pending ? 'Ожидание...' : trade.uncertain ? 'Повторить тот же обмен' : 'Обменять'}</button>
        </>}
      </section>
    </div>,
    document.body,
  );
}

export default ExchangeModal;
