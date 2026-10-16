import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import SlideNotice from '../../../../components/feedback/SlideNotice/SlideNotice';
import type { ProfileGift } from '../../ProfilePage';
import yes from '../../assets/vivod_yes.svg';
import no from '../../assets/vivod_no.svg';
import './GiftWithdrawal.css';
import { useModalScrollLock } from '../../../../hooks/useModalScrollLock';

export default function GiftWithdrawal({ gifts, onClose, onSuccess, onBusy, onResult }: {
  gifts: ProfileGift[]; onClose: () => void; onSuccess: (ids: number[]) => void; onBusy: (busy: boolean) => void;
  onResult?: (success: boolean, gifts: ProfileGift[]) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const attempt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [status, setStatus] = useState('');
  useModalScrollLock(gifts.length > 0);
  useEffect(() => {
    if (!gifts.length) { dialog.current?.close(); return; }
    dialog.current?.showModal();
  }, [gifts.length]);
  useEffect(() => () => clearTimeout(timer.current), []);
  const confirm = () => {
    if (status === 'pending') return;
    const ids = gifts.map((gift) => gift.id);
    onClose();
    onBusy(true);
    setStatus('pending');
    clearTimeout(timer.current);
    // Тестовый вывод: успешная и неуспешная попытки по очереди.
    const success = attempt.current++ % 2 === 0;
    timer.current = setTimeout(() => {
      if (success) onSuccess(ids);
      if (onResult) {
        setStatus('');
        onBusy(false);
        onResult(success, gifts);
        return;
      }
      setStatus(success ? 'success' : 'error');
      timer.current = setTimeout(() => { setStatus(''); onBusy(false); }, 2500);
    }, 1800);
  };
  return createPortal(<>
    <dialog ref={dialog} className="gift-withdraw-confirm" onCancel={(event) => { event.preventDefault(); onClose(); }} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }} aria-label="Подтверждение вывода">
      <section><p>Вы уверены что хотите вывести<br />{gifts.map((gift) => gift.name).join(', ')} стоимостью {gifts.reduce((sum, gift) => sum + gift.price, 0).toFixed(3)} TON?</p>
        <div><button autoFocus type="button" aria-label="Отменить вывод" onClick={onClose}><img src={no} alt="" /></button><button type="button" aria-label="Подтвердить вывод" onClick={confirm}><img src={yes} alt="" /></button></div>
      </section>
    </dialog>
    <SlideNotice show={Boolean(status)}><output className="gift-withdraw-notice" data-status={status} role="status">{status === 'pending' ? <>Ожидание вывода<span className="gift-withdraw-dots" aria-hidden="true">...</span></> : status === 'success' ? 'Успешно!' : 'Ошибка!'}</output></SlideNotice>
  </>, document.body);
}
