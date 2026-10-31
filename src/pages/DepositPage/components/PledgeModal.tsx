import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
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
import success from '../../ProfilePage/assets/yspeh_galoshka.svg';
import failure from '../../ProfilePage/assets/oshibka_krestik.svg';
import { useModalScrollLock } from '../../../hooks/useModalScrollLock';
import { pledgeStore, type Pledge } from '../services/pledgeStore';
import './PledgeModal.css';
import { useLoanTerms } from '../../../loans/LoanProvider';

type Payment = { action: 'repay' | 'interest'; phase: 'confirm' | 'pending' | 'success' | 'error'; giftId: number; giftName: string; amount: number; legacy: boolean; message?: string };

export default function PledgeModal({ gift, open, onClose, pledge, onCreated }: { gift: Gift | null; open: boolean; onClose: () => void; pledge?: Pledge; onCreated: () => void }) {
  const pledgeTerms = useLoanTerms();
  const storeState = useSyncExternalStore(pledgeStore.subscribe, pledgeStore.getSnapshot);
  const dialog = useRef<HTMLDialogElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [mountedOpen, setMountedOpen] = useState(false);
  const [weeks, setWeeks] = useState<1 | 2 | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [notice, setNotice] = useState('');
  const [payment, setPayment] = useState<Payment | null>(null);
  const pending = useRef(false);
  const generation = useRef(0);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const confirmButton = useRef<HTMLButtonElement>(null);
  const feedback = useRef<HTMLElement>(null);
  const underfunded = pledge?.status === 'active' && storeState.balance < pledge.repayment;
  const displayedNotice = underfunded ? 'Баланса недостаточно!' : notice;
  useModalScrollLock(open || mountedOpen);
  useEffect(() => {
    generation.current++;
    let frame = 0; let next = 0; let timer = 0;
    if (open) {
      setMountedOpen(true);
      if (!dialog.current?.open) dialog.current?.showModal();
      if (dialog.current) dialog.current.scrollTop = 0;
      setWeeks(null); setConfirm(false); setNotice(''); setPayment(null);
      if (scroll.current) scroll.current.scrollTop = 0;
      frame = requestAnimationFrame(() => { next = requestAnimationFrame(() => {
        if (dialog.current) dialog.current.scrollTop = 0;
        if (scroll.current) scroll.current.scrollTop = 0;
        setVisible(true);
      }); });
    } else { setVisible(false); timer = window.setTimeout(() => { dialog.current?.close(); setMountedOpen(false); }, 420); }
    return () => { cancelAnimationFrame(frame); cancelAnimationFrame(next); clearTimeout(timer); };
  }, [open, gift?.id]);
  useEffect(() => {
    if (confirm || payment?.phase === 'confirm') confirmButton.current?.focus();
    else if (payment) feedback.current?.focus();
  }, [confirm, payment]);
  useEffect(() => () => { generation.current++; clearTimeout(noticeTimer.current); }, []);
  const notify = (message: string) => { setNotice(message); clearTimeout(noticeTimer.current); noticeTimer.current = setTimeout(() => setNotice(''), 2500); };
  const dismiss = () => {
    if (pending.current) return;
    if (payment) {
      if (payment.phase === 'success' && payment.action === 'repay') onClose();
      else setPayment(null);
    } else onClose();
  };
  const beginPayment = (action: Payment['action']) => {
    if (!gift || !pledge || pending.current || (action === 'interest' && pledge.legacy)) return;
    const amount = action === 'repay' ? pledge.repayment : pledge.interest ?? (pledge.repayment - pledge.principal);
    if (storeState.balance < amount) { notify('Баланса недостаточно!'); return; }
    setPayment({ action, phase: 'confirm', giftId: gift.id, giftName: gift.name, amount, legacy: Boolean(pledge.legacy) });
  };
  const submitPayment = async (operation: Payment) => {
    if (pending.current) return;
    pending.current = true;
    const version = generation.current;
    setPayment({ ...operation, phase: 'pending', message: undefined });
    try {
      const ok = operation.action === 'repay' ? await pledgeStore.repay(operation.giftId) : await pledgeStore.payInterest(operation.giftId);
      if (version !== generation.current) return;
      if (!ok) notify('Баланса недостаточно!');
      setPayment({ ...operation, phase: ok ? 'success' : 'error', message: ok ? undefined : 'Баланса недостаточно!' });
    } catch {
      if (version === generation.current) setPayment({ ...operation, phase: 'error', message: 'Не удалось подтвердить платеж. Проверьте баланс и повторите попытку.' });
    }
    finally { pending.current = false; }
  };
  const create = async () => {
    if (!gift || !weeks || pending.current) return;
    pending.current = true;
    try { if (await pledgeStore.create(gift.id, weeks)) { setConfirm(false); onCreated(); } else notify('Подарок недоступен'); }
    catch { setConfirm(false); notify('Не удалось заложить подарок'); }
    finally { pending.current = false; }
  };
  return createPortal(<dialog ref={dialog} className="pledge-dialog" data-visible={visible} aria-label="Залог подарка" onCancel={(event) => { event.preventDefault(); if (pending.current) return; if (confirm) setConfirm(false); else dismiss(); }} onClick={(event) => { if (event.target === event.currentTarget) dismiss(); }}>
    <div className="pledge-dialog__scrim" onClick={dismiss} aria-hidden="true" />
    <section className="pledge-sheet" data-status={pledge?.status} data-underfunded={Boolean(underfunded)} inert={Boolean(payment)}>
      <div className="pledge-sheet__body" inert={confirm}>
        <header><span /><button autoFocus onClick={dismiss} aria-label="Закрыть"><img src={close} alt="" /></button></header>
        <div className="pledge-sheet__scroll" ref={scroll}>
          {gift && <><div className="pledge-preview"><GiftArtwork gift={gift} /><span><img src={ton} alt="" />{gift.price}</span><div className="pledge-preview__caption"><strong>{gift.name}</strong><small>{gift.model}</small></div></div>
            <dl className="pledge-attributes">{[['Модель', gift.modelName ?? 'Модель', ''], ['Символ', gift.symbol?.name ?? '—', gift.symbol?.rarity], ['Фон', gift.backdrop?.name ?? '—', gift.backdrop?.rarity]].map(([label, value, rarity]) => <div key={label}><dt>{label}</dt><dd><span>{value}{rarity && <small>{rarity}</small>}</span></dd></div>)}</dl>
            {!pledge && <div className="pledge-terms">{pledgeTerms.map((term) => <button key={term.weeks} aria-pressed={weeks === term.weeks} onClick={() => setWeeks(weeks === term.weeks ? null : term.weeks)} data-weeks={term.weeks}><img src={term.weeks === 1 ? greenBackdrop : blueBackdrop} alt="" /><span>{term.weeks === 1 ? '1 неделя' : '2 недели'}</span><strong>{term.principal.toFixed(3)} TON</strong><small>Возврат {term.repayment.toFixed(3)} TON</small><b>{weeks === term.weeks ? 'Выбран' : 'Выбрать'}</b></button>)}</div>}
            {pledge?.status === 'processing' && <div className="pledge-processing" role="status"><img src={processing} alt="" /><strong>Обработка<span>...</span></strong><p>Займ в настоящее время обрабатывается, и будет осуществлен в ближайшее время.</p></div>}
            {pledge?.legacy && <small>Подарок зарезервирован. Возврат без списания.</small>}
            {pledge?.status === 'active' && !pledge.legacy && <div className="pledge-details">
              <section className="pledge-details__summary"><h3>{pledge.weeks * 7} дней</h3><strong>{pledge.principal.toFixed(3)} TON</strong><p>Для погашения {pledge.repayment.toFixed(3)} TON</p></section>
              <section><h3>Предстоящий платеж</h3><p>Не забывайте регулярно платить проценты по займу, чтобы продолжать использовать заемные средства. Вы можете сделать это в любое время до наступления срока погашения.</p><div className="pledge-payment"><div><strong>{new Date(pledge.dueAt).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })} ({new Date(pledge.dueAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })})</strong><small>К оплате — {(pledge.interest ?? (pledge.repayment - pledge.principal)).toFixed(3)} TON</small></div><button onClick={() => beginPayment('interest')}>Оплатить</button></div></section>
              <section><h3>Автоплатеж</h3><p>Демо-автоплатеж проверяется при наступлении срока, раз в минуту во время работы сервиса. Бесплатный демо-сервер может выполнить проверку после пробуждения или при следующем обновлении. Просроченные подарки не изымаются.</p><button className="pledge-autopay" data-active={pledge.autopay} onClick={async () => { if (pending.current) return; pending.current = true; try { await pledgeStore.toggleAutopay(gift.id); } catch { notify('Не удалось изменить автоплатеж'); } finally { pending.current = false; } }}>{pledge.autopay ? 'Отключить' : 'Включить'}</button></section>
            </div>}
          </>}
        </div>
        {pledge?.status !== 'processing' && <footer><button disabled={!pledge && !weeks} onClick={() => pledge ? beginPayment('repay') : setConfirm(true)}>{pledge ? pledge.legacy ? 'Вернуть подарок бесплатно' : `Закрыть займ за ${pledge.repayment.toFixed(3)} TON` : weeks ? `Получить ${pledgeTerms.find((term) => term.weeks === weeks)?.principal.toFixed(3)} TON` : 'Выберите срок'}</button></footer>}
      </div>
      <SlideNotice show={Boolean(displayedNotice)}><div className="pledge-notice" data-error={displayedNotice === 'Баланса недостаточно!'} role="status">{displayedNotice}</div></SlideNotice>
    </section>
      {confirm && gift && <div className="pledge-confirm-backdrop"><section className="pledge-confirm" role="alertdialog" aria-modal="true" aria-label="Подтверждение залога"><p>Вы уверены, что хотите получить {pledgeTerms.find((term) => term.weeks === weeks)?.principal.toFixed(3)} TON, передав ваш {gift.name} в залог на {weeks === 1 ? '1 неделю' : '2 недели'}?</p><div><button ref={confirmButton} aria-label="Отменить" onClick={() => setConfirm(false)}><img src={no} alt="" /></button><button aria-label="Подтвердить" onClick={create}><img src={yes} alt="" /></button></div></section></div>}
      {payment && <div className="pledge-confirm-backdrop" onClick={(event) => { if (event.target === event.currentTarget) dismiss(); }}>
        {payment.phase === 'confirm' ? <section className="pledge-confirm" role="alertdialog" aria-modal="true" aria-label={payment.action === 'repay' ? 'Подтверждение возврата подарка' : 'Подтверждение оплаты процентов'}>
          <p>{payment.action === 'repay' ? payment.legacy ? `Вернуть ${payment.giftName} в инвентарь бесплатно? Средства списаны не будут.` : `Погасить займ за ${payment.amount.toFixed(3)} TON и вернуть ${payment.giftName} в инвентарь?` : `Оплатить проценты ${payment.amount.toFixed(3)} TON и продлить займ по ${payment.giftName}?`}</p>
          <div><button ref={confirmButton} aria-label="Отменить" onClick={() => setPayment(null)}><img src={no} alt="" /></button><button aria-label="Подтвердить" onClick={() => void submitPayment(payment)}><img src={yes} alt="" /></button></div>
        </section> : <section ref={feedback} tabIndex={-1} className="pledge-feedback" data-phase={payment.phase} role="dialog" aria-modal="true" aria-labelledby="pledge-feedback-title" aria-describedby="pledge-feedback-message" aria-busy={payment.phase === 'pending'}>
          <h2 id="pledge-feedback-title">{payment.phase === 'pending' ? 'Обработка...' : payment.phase === 'success' ? 'Успешно!' : 'Ошибка'}</h2>
          <div className="pledge-feedback__icon"><img className={payment.phase === 'pending' ? 'pledge-feedback__spinner' : ''} src={payment.phase === 'pending' ? processing : payment.phase === 'success' ? success : failure} alt="" /></div>
          <p id="pledge-feedback-message" role={payment.phase === 'error' ? 'alert' : 'status'}>{payment.phase === 'pending' ? 'Пожалуйста, подождите...' : payment.phase === 'error' ? payment.message : payment.action === 'repay' ? payment.legacy ? `${payment.giftName} возвращен в инвентарь без списания средств.` : `Займ погашен. ${payment.giftName} возвращен в инвентарь.` : 'Проценты оплачены. Срок займа продлен.'}</p>
          {payment.phase !== 'pending' && <div className="pledge-feedback__actions">{payment.phase === 'error' && <button onClick={() => void submitPayment(payment)}>Попробовать снова</button>}<button onClick={dismiss}>{payment.phase === 'success' ? 'Вернуться назад' : 'Вернуться к займу'}</button></div>}
        </section>}
      </div>}
  </dialog>, document.body);
}
