import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Gift } from '../../data/gifts';
import giftIcon from '../../assets/gift.svg';
import GiftArtwork from '../../../../components/gifts/GiftArtwork/GiftArtwork';
import tonIcon from '../../../../assets/ton.svg';
import closeIcon from '../FilterModal/assets/Union.svg';
import viewIcon from './assets/modal-gift-posmotret.svg';
import shareIcon from './assets/modal-gift-share.svg';
import './GiftDetailsModal.css';

type Props = {
  gift: Gift | null;
  source: 'inventory' | 'exchange';
  open: boolean;
  selected: boolean;
  onClose: () => void;
  onSelect: () => void;
};

export default function GiftDetailsModal({ gift, source, open, selected, onClose, onSelect }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const scrollArea = useRef<HTMLDivElement>(null);
  const scrollBody = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [preview, setPreview] = useState(false);
  const [notice, setNotice] = useState('');
  const [scrolledToEnd, setScrolledToEnd] = useState(false);

  const updateScrollState = () => {
    const element = scrollArea.current;
    if (!element) return;
    setScrolledToEnd(element.scrollHeight - element.scrollTop - element.clientHeight <= 2);
  };

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    let firstFrame = 0;
    let secondFrame = 0;
    let closeTimer = 0;
    if (open) {
      if (!element.open) element.showModal();
      element.scrollTop = 0;
      setNotice('');
      setPreview(false);
      setScrolledToEnd(false);
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => {
          setVisible(true);
          const content = scrollArea.current;
          if (content) content.scrollTop = 0;
          updateScrollState();
        });
      });
    } else {
      setVisible(false);
      closeTimer = window.setTimeout(() => element.close(), 420);
    }
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
      clearTimeout(closeTimer);
    };
  }, [open]);

  // Пересчитываем конец списка при смене подарка, размера окна и высоты текста.
  useEffect(() => {
    if (!open || !scrollArea.current || !scrollBody.current) return;
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(scrollArea.current);
    observer.observe(scrollBody.current);
    document.fonts.ready.then(updateScrollState);
    return () => observer.disconnect();
  }, [open, gift?.id]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, [open]);

  const share = async () => {
    if (!gift) return;
    const text = `${gift.name} ${gift.model} — ${gift.price} TON`;
    try {
      if (navigator.share) await navigator.share({ title: gift.name, text });
      else {
        await navigator.clipboard.writeText(text);
        setNotice('Информация о подарке скопирована');
      }
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        setNotice('Не удалось поделиться подарком');
      }
    }
  };

  return createPortal(
    <dialog ref={dialog} className="gift-details" data-visible={visible} aria-label={gift ? `Подарок ${gift.name}` : 'Подарок'} onCancel={(event) => {
      event.preventDefault();
      if (preview) setPreview(false);
      else onClose();
    }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <button className="gift-details__scrim" type="button" aria-label="Закрыть подарок" onClick={onClose} />
      <section className="gift-details__sheet">
        <header className="gift-details__header">
          <span className="gift-details__handle" aria-hidden="true" />
          <button autoFocus type="button" className="gift-details__close" aria-label="Закрыть подарок" onClick={onClose}><img src={closeIcon} alt="" /></button>
        </header>
        {gift && <div ref={scrollArea} className="gift-details__scroll" onScroll={updateScrollState}>
          <div ref={scrollBody} className="gift-details__body">
          <div className="gift-details__art">
            <GiftArtwork gift={gift} />
            <span className="gift-details__price"><span><img src={tonIcon} alt="TON" /></span>{gift.price}</span>
            <div className="gift-details__caption"><h2>{gift.name}</h2><span>{gift.model}</span></div>
          </div>
          <dl className="gift-details__traits">
            <div><dt>Модель</dt><dd>{gift.modelName ?? 'Модель'}</dd></div>
            <div><dt>Символ</dt><dd>{gift.symbol?.name ?? '—'} <small>{gift.symbol?.rarity}</small></dd></div>
            <div><dt>Фон</dt><dd>{gift.backdrop?.name ?? '—'} <small>{gift.backdrop?.rarity}</small></dd></div>
          </dl>
          <div className="gift-details__actions">
            <button type="button" onClick={() => setPreview(true)}><img src={viewIcon} alt="" /><span>Посмотреть</span></button>
            <button type="button" onClick={share}><img src={shareIcon} alt="" /><span>Поделиться</span></button>
          </div>
          <section className="gift-details__offer">
            <h3>{source === 'inventory' ? 'Не нравится?' : 'Нравится?'}</h3>
            <p>{source === 'inventory' ? 'Обменяй подарок на любой понравившийся!' : 'Обменяй на свой подарок и хвастайся!'}</p>
            <button type="button" onClick={onSelect}>{selected ? 'Убрать' : 'В Обмен'}</button>
          </section>
          {source === 'inventory' && <section className="gift-details__offer">
            <h3>Нужны тоны?</h3>
            <p>Возьми их у нас под залог своего подарка!</p>
            <button type="button" onClick={() => setNotice('Залог пока недоступен')}>В Залог</button>
          </section>}
          {notice && <p className="gift-details__notice" role="status">{notice}</p>}
          </div>
        </div>}
        <footer className="gift-details__footer" data-at-end={scrolledToEnd}>
          <button className="gift-details__done" type="button" onClick={source === 'exchange' ? onSelect : onClose}>
            {source === 'exchange' ? (selected ? 'Убрать из обмена' : 'В обмен!') : 'Закрыть'}
          </button>
        </footer>
        {preview && <div className="gift-details__preview">
          <button className="gift-details__close" type="button" aria-label="Закрыть просмотр" onClick={() => setPreview(false)}><img src={closeIcon} alt="" /></button>
          <img src={gift?.image ?? giftIcon} alt={gift?.name} />
          <strong>{gift?.name} {gift?.model}</strong>
        </div>}
      </section>
    </dialog>, document.body,
  );
}
