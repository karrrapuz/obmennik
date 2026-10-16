import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SlideNotice from '../../../components/feedback/SlideNotice/SlideNotice';
import type { Gift } from '../../ExchangePage/data/gifts';
import GiftArtwork from '../../../components/gifts/GiftArtwork/GiftArtwork';
import ton from '../../../assets/ton.svg';
import close from '../../ExchangePage/components/FilterModal/assets/Union.svg';
import yes from '../../ProfilePage/assets/vivod_yes.svg';
import no from '../../ProfilePage/assets/vivod_no.svg';
import greenBackdrop from '../assets/zalog-modal-one-nedelya.svg';
import blueBackdrop from '../assets/zalog-modal-two-nedelya.svg';
import processing from '../assets/obrabotka-zaloga.svg';
import { useModalScrollLock } from '../../../hooks/useModalScrollLock';
import { pledgeStore, pledgeTerms, type Pledge } from '../services/pledgeStore';
import './PledgeModal.css';

export default function PledgeModal({ gift, open, onClose, pledge, onCreated }: { gift: Gift | null; open: boolean; onClose: () => void; pledge?: Pledge; onCreated: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [mountedOpen, setMountedOpen] = useState(false);
  const [weeks, setWeeks] = useState<1 | 2 | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState('');
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const underfunded = pledge?.status === 'active' && pledgeStore.getSnapshot().balance < pledge.repayment;
  const displayedNotice = underfunded ? 'Баланса недостаточно!' : notice;
  useModalScrollLock(open || mountedOpen);
  useEffect(() => {
    let frame = 0; let next = 0; let timer = 0;
    if (open) {
      setMountedOpen(true);
      if (!dialog.current?.open) dialog.current?.showModal();
      if (dialog.current) dialog.current.scrollTop = 0;
      setWeeks(null); setConfirm(false); setNotice('');
      if (scroll.current) scroll.current.scrollTop = 0;
      frame = requestAnimationFrame(() => { next = requestAnimationFrame(() => {
        if (dialog.current) dialog.current.scrollTop = 0;
        if (scroll.current) scroll.current.scrollTop = 0;
        setVisible(true);
      }); });
    } else { setVisible(false); timer = window.setTimeout(() => { dialog.current?.close(); setMountedOpen(false); }, 420); }
    return () => { cancelAnimationFrame(frame); cancelAnimationFrame(next); clearTimeout(timer); };
  }, [open, gift?.id]);
  useEffect(() => { if (confirm) confirmButton.current?.focus(); }, [confirm]);
  useEffect(() => () => clearTimeout(noticeTimer.current), []);
  const notify = (message: string) => { setNotice(message); clearTimeout(noticeTimer.current); noticeTimer.current = setTimeout(() => setNotice(''), 2500); };
  const repay = () => {
    if (!gift) return;
    if (pledgeStore.repay(gift.id)) { onClose(); } else notify('Баланса недостаточно!');
  };
  return createPortal(<dialog ref={dialog} className="pledge-dialog" data-visible={visible} aria-label="Залог подарка" onCancel={(event) => { event.preventDefault(); if (confirm) setConfirm(false); else onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="pledge-dialog__scrim" onClick={onClose} aria-hidden="true" />
    <section className="pledge-sheet" data-status={pledge?.status} data-underfunded={Boolean(pledge && pledgeStore.getSnapshot().balance < pledge.repayment)}>
      <div className="pledge-sheet__body" inert={confirm}>
        <header><span /><button autoFocus onClick={onClose} aria-label="Закрыть"><img src={close} alt="" /></button></header>
        <div className="pledge-sheet__scroll" ref={scroll}>
          {gift && <><div className="pledge-preview"><GiftArtwork gift={gift} /><span><img src={ton} alt="" />{gift.price}</span><div className="pledge-preview__caption"><strong>{gift.name}</strong><small>{gift.model}</small></div></div>
            <dl className="pledge-attributes">{[['Модель', gift.modelName ?? 'Модель', ''], ['Символ', gift.symbol?.name ?? '—', gift.symbol?.rarity], ['Фон', gift.backdrop?.name ?? '—', gift.backdrop?.rarity]].map(([label, value, rarity]) => <div key={label}><dt>{label}</dt><dd><span>{value}{rarity && <small>{rarity}</small>}</span></dd></div>)}</dl>
            {!pledge && <div className="pledge-terms">{pledgeTerms.map((term) => <button key={term.weeks} aria-pressed={weeks === term.weeks} onClick={() => setWeeks(weeks === term.weeks ? null : term.weeks)} data-weeks={term.weeks}><img src={term.weeks === 1 ? greenBackdrop : blueBackdrop} alt="" /><span>{term.weeks === 1 ? '1 неделя' : '2 недели'}</span><strong>{term.principal.toFixed(3)} TON</strong><small>Возврат {term.repayment.toFixed(3)} TON</small><b>{weeks === term.weeks ? 'Выбран' : 'Выбрать'}</b></button>)}</div>}
            {pledge?.status === 'processing' && <div className="pledge-processing" role="status"><img src={processing} alt="" /><strong>Обработка<span>...</span></strong><p>Займ в настоящее время обрабатывается, и будет осуществлен в ближайшее время.</p></div>}
            {pledge?.status === 'active' && <div className="pledge-details">
              <section className="pledge-details__summary"><h3>{pledge.weeks * 7} дней</h3><strong>{pledge.principal.toFixed(3)} TON</strong><p>Для погашения {pledge.repayment.toFixed(3)} TON</p></section>
              <section><h3>Предстоящий платеж</h3><p>Не забывайте регулярно платить проценты по займу, чтобы продолжать использовать заемные средства. Вы можете сделать это в любое время до наступления срока погашения.</p><div className="pledge-payment"><div><strong>{new Date(pledge.dueAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })} ({new Date(pledge.dueAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })})</strong><small>К оплате — {(pledge.repayment - pledge.principal).toFixed(3)} TON</small></div><button onClick={() => notify(pledgeStore.payInterest(gift.id) ? 'Успешно!' : 'Баланса недостаточно!')}>Оплатить</button></div></section>
              <section><h3>Автоплатеж</h3><p>Мы автоматически спишем средства с вашего счета до истечения срока займа и уведомим вас, если средств недостаточно.</p><button className="pledge-autopay" data-active={pledge.autopay} onClick={() => pledgeStore.toggleAutopay(gift.id)}>{pledge.autopay ? 'Отключить' : 'Включить'}</button></section>
            </div>}
          </>}
        </div>
        {pledge?.status !== 'processing' && <footer><button disabled={underfunded || (!pledge && !weeks)} onClick={() => pledge ? repay() : setConfirm(true)}>{pledge ? `Закрыть займ за ${pledge.repayment.toFixed(3)} TON` : weeks ? 'Получить 1.200 TON' : 'Выберите срок'}</button></footer>}
      </div>
      <SlideNotice show={Boolean(displayedNotice)}><div className="pledge-notice" data-error={displayedNotice === 'Баланса недостаточно!'} role="status">{displayedNotice}</div></SlideNotice>
    </section>
      {confirm && gift && <div className="pledge-confirm-backdrop"><section className="pledge-confirm" role="alertdialog" aria-modal="true" aria-label="Подтверждение залога"><p>Вы уверены, что хотите получить 1.200 TON, передав ваш {gift.name} в залог на {weeks === 1 ? '1 неделю' : '2 недели'}?</p><div><button ref={confirmButton} aria-label="Отменить" onClick={() => setConfirm(false)}><img src={no} alt="" /></button><button aria-label="Подтвердить" onClick={() => { if (weeks) { pledgeStore.create(gift.id, weeks); setConfirm(false); onCreated(); } }}><img src={yes} alt="" /></button></div></section></div>}
  </dialog>, document.body);
}
