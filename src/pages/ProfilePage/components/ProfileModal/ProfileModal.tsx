import { useEffect, useRef, useState } from 'react';
import { useWallet } from '../../../../wallet/WalletProvider';
import { useModalFocus } from '../../../../hooks/useModalFocus';
import { formatNano, MAX_ACTION, MAX_BALANCE, parseTon } from '../../../../wallet/wallet';
import { createPortal, flushSync } from 'react-dom';
import GiftArtwork from '../../../../components/gifts/GiftArtwork/GiftArtwork';
import type { ProfileGift } from '../../ProfilePage';
import tonIcon from '../../../../assets/gram.svg';
import { displayName, useUser } from '../../../../auth/AuthProvider';
import UserAvatar from '../../../../components/layout/UserAvatar';
import { openGiftRelayer } from '../../../../services/giftRelayer';
import { telegramHaptic } from '../../../../services/telegram';
import selectActive from '../../assets/profile-use-gift-active.svg';
import selectInactive from '../../assets/profile-use-gift-inactive.svg';
import selectCheck from '../../../ExchangePage/assets/galochka.svg';
import selectPlus from '../../../../assets/plus.svg';
import closeIcon from '../../../ExchangePage/components/FilterModal/assets/Union.svg';
import walletIcon from '../../assets/coshelek.svg';
import cryptoIcon from '../../assets/cryptobot.svg';
import withdrawBalanceIcon from '../../assets/vivod_modal_balance.svg';
import withdrawGiftIcon from '../../assets/vivod_modal_gift.svg';
import successIcon from '../../assets/yspeh_galoshka.svg';
import errorIcon from '../../assets/oshibka_krestik.svg';
import processingIcon from '../../../DepositPage/assets/obrabotka-zaloga.svg';
import './ProfileModal.css';
import SlideNotice from '../../../../components/feedback/SlideNotice/SlideNotice';
import { useModalScrollLock } from '../../../../hooks/useModalScrollLock';

export type ProfileModalKind =
  | 'deposit-choice' | 'withdraw-choice' | 'wallet-warning' | 'wallet-connect'
  | 'gift-deposit' | 'gift-empty' | 'deposit-amount' | 'crypto-amount'
  | 'withdraw-amount' | 'gift-withdraw'
  | 'gift-result-success' | 'gift-result-error'
  | 'result-success' | 'result-error';

type ProfileModalProps = {
  kind: ProfileModalKind | null;
  setKind: (kind: ProfileModalKind | null) => void;
  wallet: string;
  setWallet: (wallet: string) => void;
  gifts: ProfileGift[];
  withdrawalBusy: boolean;
  onWithdraw: (gifts: ProfileGift[]) => void;
  giftResultText: string;
};

const SHEET_TRANSITION_MS = 400;
const MIN_PROCESSING_MS = 1000;
const pause = (duration: number) => new Promise<void>(resolve => window.setTimeout(resolve, duration));

function ProfileModal({ kind: requestedKind, setKind, wallet, setWallet, gifts, withdrawalBusy, onWithdraw, giftResultText }: ProfileModalProps) {
  const { wallet: walletSnapshot, operate, pending: walletPending, error: walletError, available: walletAvailable, reload } = useWallet();
  const balanceNano = BigInt(walletSnapshot.balance_nano);
  const user = useUser();
  const [lastKind, setLastKind] = useState(requestedKind);
  const [processing, setProcessing] = useState(false);
  const kind = processing ? 'payment-processing' : requestedKind ?? lastKind;
  const [mounted, setMounted] = useState(kind !== null);
  const [visible, setVisible] = useState(false);
  const [parked, setParked] = useState(false);
  const [amount, setAmount] = useState('');
  const [walletInput, setWalletInput] = useState('');
  const [selectedGiftIds, setSelectedGiftIds] = useState<number[]>([]);
  const [resultText, setResultText] = useState('');
  const [paymentNotice, setPaymentNotice] = useState<{ success: boolean; message: string } | null>(null);
  const [pending, setPending] = useState(false);
  const [resultReturn, setResultReturn] = useState<ProfileModalKind | null>(null);
  const pendingRef = useRef(false);
  const currentKind = useRef(requestedKind);
  const displayGeneration = useRef(0);
  const contentRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  useModalFocus(panelRef, mounted);
  currentKind.current = requestedKind;
  const alive = useRef(false);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  const [walletReturn, setWalletReturn] = useState<ProfileModalKind>('deposit-choice');
  useModalScrollLock(mounted);

  useEffect(() => {
    if (!paymentNotice) return;
    const timer = window.setTimeout(() => setPaymentNotice(null), 6500);
    return () => clearTimeout(timer);
  }, [paymentNotice]);

  useEffect(() => {
    displayGeneration.current++;
    let firstFrame = 0;
    let secondFrame = 0;
    let closeTimer = 0;
    if (requestedKind) {
      setParked(false);
      setProcessing(false);
      setLastKind(requestedKind);
      setMounted(true);
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => { contentRef.current?.scrollTo(0, 0); setVisible(true); });
      });
    } else {
      setVisible(false);
      closeTimer = window.setTimeout(() => { setMounted(false); setProcessing(false); }, 360);
    }
    return () => {
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
      clearTimeout(closeTimer);
    };
  }, [requestedKind]);

  useEffect(() => {
    if (!mounted) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) setKind(null);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [mounted, setKind]);

  const chooseWalletFlow = (target: ProfileModalKind) => {
    setAmount('');
    if (wallet) {
      setKind(target);
    } else {
      setWalletReturn(target);
      setKind('wallet-warning');
    }
  };

  const complete = (message: string, success: boolean, returnTo: ProfileModalKind) => {
    telegramHaptic(success ? 'success' : 'error');
    setResultReturn(returnTo);
    setResultText(message);
    setProcessing(false);
    setKind(success ? 'result-success' : 'result-error');
  };

  const amountNano = parseTon(amount);
  const validAmount = amountNano !== null && amountNano > 0n && amountNano <= MAX_ACTION;
  const canWithdraw = validAmount && amountNano <= balanceNano && Boolean(wallet);
  const canTopUp = validAmount && balanceNano + amountNano <= MAX_BALANCE && (kind === 'crypto-amount' || Boolean(wallet));
  const hidePaymentSheet = async (isCurrent: () => boolean) => {
    flushSync(() => setVisible(false));
    // Force style resolution before collecting the exit transition, including on slower WebViews.
    panelRef.current?.getBoundingClientRect();
    const transitions = panelRef.current?.getAnimations() ?? [];
    await Promise.all([pause(SHEET_TRANSITION_MS), ...transitions.map(animation => animation.finished.catch(() => {}))]);
    if (isCurrent()) flushSync(() => setParked(true));
  };
  const submitAmount = async () => {
    const withdrawal = kind === 'withdraw-amount';
    if (pendingRef.current || walletPending || !walletAvailable || amountNano === null || !(withdrawal ? canWithdraw : canTopUp)) return;
    if (kind !== 'withdraw-amount' && kind !== 'deposit-amount' && kind !== 'crypto-amount') return;
    const submittedKind = kind;
    const generation = displayGeneration.current;
    const sameScreen = () => alive.current && currentKind.current === submittedKind && displayGeneration.current === generation;
    pendingRef.current = true; setPending(true);
    const outcome = operate(withdrawal ? 'withdraw' : 'topup', withdrawal ? { amount_nano: amountNano.toString(), destination: wallet } : { amount_nano: amountNano.toString(), source: submittedKind === 'crypto-amount' ? 'cryptobot' : 'wallet' })
      .then(() => ({ success: true, message: `${withdrawal ? 'Вывод' : 'Пополнение'}: ${formatNano(amountNano)} GRAM` }),
        () => ({ success: false, message: 'Не удалось подтвердить операцию. Повторите попытку.' }));
    let shownInSheet = false;
    try {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      await hidePaymentSheet(sameScreen);
      if (!sameScreen()) return;
      setProcessing(true);
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      if (!sameScreen()) return;
      setParked(false);
      setVisible(true);
      // Keep a full second of readable processing after the sheet finishes entering.
      await pause(SHEET_TRANSITION_MS + MIN_PROCESSING_MS);
      const result = await outcome;
      if (!sameScreen()) return;
      await hidePaymentSheet(sameScreen);
      if (sameScreen()) {
        complete(result.message, result.success, submittedKind);
        shownInSheet = true;
      }
    } finally {
      if (!shownInSheet && alive.current) {
        const result = await outcome;
        if (alive.current) {
          telegramHaptic(result.success ? 'success' : 'error');
          setPaymentNotice(result);
        }
      }
      pendingRef.current = false;
      if (alive.current) setPending(false);
    }
  };

  const back = () => {
    if (kind === 'wallet-connect') setKind('wallet-warning');
    else if (kind === 'wallet-warning') setKind(walletReturn === 'withdraw-amount' ? 'withdraw-choice' : 'deposit-choice');
    else if (kind === 'gift-deposit' || kind === 'crypto-amount' || kind === 'deposit-amount') setKind('deposit-choice');
    else if (kind === 'gift-withdraw' || kind === 'gift-empty' || kind === 'withdraw-amount') setKind('withdraw-choice');
    else setKind(null);
  };

  const notice = createPortal(
    <SlideNotice show={paymentNotice !== null}>
      <output className="profile-payment-notice" data-success={paymentNotice?.success} role="status">
        {paymentNotice?.message}
      </output>
    </SlideNotice>, document.body,
  );
  if (!mounted) return notice;

  const title = kind === 'deposit-choice' ? 'Пополнение'
    : kind === 'payment-processing' ? 'Обработка…'
    : kind === 'deposit-amount' ? 'Балансом'
    : kind === 'crypto-amount' ? 'CryptoBot'
    : kind === 'gift-deposit' ? 'Подарки'
    : kind === 'withdraw-choice' ? 'Вывод'
      : kind === 'gift-withdraw' || kind === 'gift-empty' ? 'Подарки'
      : kind === 'gift-result-success' ? 'Успешно!' : kind === 'gift-result-error' ? 'Ошибка'
      : kind === 'wallet-warning' && walletReturn === 'withdraw-amount' ? 'Баланс'
        : kind === 'wallet-warning' || kind === 'wallet-connect' ? 'Кошелёк'
          : kind === 'result-success' ? 'Успешно!' : kind === 'result-error' ? 'Ошибка' : 'Баланс';
  const short = kind === 'wallet-warning' || kind === 'wallet-connect';
  const selectedGifts = gifts.filter((gift) => selectedGiftIds.includes(gift.id));

  return <>{notice}{createPortal(<div className="profile-modal-layer" data-visible={visible} onTransitionEnd={(event) => {
    if (event.target === event.currentTarget && !requestedKind && event.propertyName === 'background-color') setMounted(false);
  }}>
    <button className="profile-modal-scrim" type="button" aria-label="Закрыть окно" onClick={() => setKind(null)} />
    <section ref={panelRef} tabIndex={-1} className="profile-modal" data-parked={parked} data-short={short} data-kind={kind} role="dialog" aria-modal="true" aria-label={title} aria-busy={processing}>
      <div className="profile-modal__handle" aria-hidden="true" />
      <header className="profile-modal__header">
        <h2>{title}</h2>
        <button className="profile-modal__close" type="button" aria-label="Закрыть окно" onClick={() => setKind(null)}><img src={closeIcon} alt="" /></button>
        {kind !== 'payment-processing' && kind !== 'deposit-choice' && kind !== 'withdraw-choice' && !kind?.includes('result-') && <button className="profile-modal__back" type="button" aria-label="Назад" onClick={back}>‹</button>}
      </header>

      <div ref={contentRef} className="profile-modal__content">
      {kind === 'payment-processing' && <div className="profile-modal__processing" role="status"><img src={processingIcon} alt="" /><p>Пожалуйста, подождите…</p></div>}
      {kind === 'deposit-choice' && <div className="profile-modal__choices">
        <button type="button" onClick={() => chooseWalletFlow('deposit-amount')}><i className="profile-modal__choice-icon"><i><img src={withdrawBalanceIcon} alt="" /></i></i><span>Кошелёк</span><small>Пополнение</small></button>
        <button type="button" onClick={() => { setAmount(''); setKind('crypto-amount'); }}><i className="profile-modal__choice-icon profile-modal__choice-icon--crypto"><i><img src={cryptoIcon} alt="" /></i></i><span>CryptoBot</span><small>Пополнение</small></button>
        <button type="button" onClick={() => setKind('gift-deposit')}><i className="profile-modal__choice-icon"><i><img src={withdrawGiftIcon} alt="" /></i></i><span>Подарками</span><small>С вашего профиля</small></button>
      </div>}

      {kind === 'withdraw-choice' && <div className="profile-modal__choices">
        <button type="button" onClick={() => chooseWalletFlow('withdraw-amount')}><i className="profile-modal__choice-icon"><i><img src={withdrawBalanceIcon} alt="" /></i></i><span>Баланс</span><small>Вывод</small></button>
        <button type="button" onClick={() => { setSelectedGiftIds([]); setKind(gifts.length ? 'gift-withdraw' : 'gift-empty'); }}><i className="profile-modal__choice-icon"><i><img src={withdrawGiftIcon} alt="" /></i></i><span>Подарки</span><small>В ваш профиль</small></button>
      </div>}

      {kind === 'wallet-warning' && <div className="profile-modal__wallet-warning"><p>Кошелёк не выбран</p><button type="button" onClick={() => { setWalletInput(''); setKind('wallet-connect'); }}>Выбрать</button></div>}

      {kind === 'wallet-connect' && <div className="profile-modal__form"><label>Адрес кошелька<input value={walletInput} onChange={(event) => setWalletInput(event.target.value.trim())} placeholder="Адрес кошелька" autoComplete="off" maxLength={256} /></label><button type="button" disabled={walletInput.length < 10} onClick={() => { setWallet(walletInput); setKind(walletReturn); }}>Сохранить адрес</button></div>}

      {kind === 'gift-deposit' && <><div className="profile-modal__gift-deposit"><p>Подарки</p><button type="button" onClick={openGiftRelayer}>GiftRelayer</button></div><button className="profile-modal__bottom profile-modal__bottom--glass" type="button" onClick={() => setKind(null)}>Закрыть</button></>}

      {kind === 'gift-empty' && <><div className="profile-modal__empty-gifts"><strong>В вашем инвентаре пусто!</strong><p>Отправьте подарок нам что бы это исправить!</p><button type="button" onClick={openGiftRelayer}>GiftRelayer</button></div><button className="profile-modal__bottom profile-modal__bottom--glass" type="button" onClick={() => setKind('withdraw-choice')}>Вернуться назад</button></>}

      {kind === 'withdraw-amount' && <form className="balance-withdraw" onSubmit={(event) => { event.preventDefault(); submitAmount(); }} aria-busy={pending}>
        <div className="balance-withdraw__wallet"><span><img src={walletIcon} alt="" /></span><span>{wallet.slice(0, 5)}...{wallet.slice(-6)}</span></div>
        <label className="balance-withdraw__input">
          <span className="balance-withdraw__coin"><i><img src={tonIcon} alt="" /></i></span>
          <input aria-label="Сумма вывода GRAM" inputMode="decimal" value={amount} placeholder="0.00" disabled={pending} onChange={(event) => { const value = event.target.value.replace(',', '.'); if (/^\d*(\.\d{0,9})?$/.test(value)) setAmount(value); }} />
          {amountNano !== null && amountNano > 0n && <small>{amountNano > balanceNano ? 'Недостаточно GRAM' : amountNano > MAX_ACTION ? 'Максимум 10000 GRAM' : `Останется: ${formatNano(balanceNano - amountNano)} GRAM`}</small>}
        </label>
        <p className="balance-withdraw__available">{walletError ? <><span role="alert">Нет связи. </span><button type="button" onClick={() => void reload().catch(() => {})}>Обновить</button></> : <>Доступно: {formatNano(balanceNano)} GRAM</>}</p>
        <button type="submit" disabled={pending || walletPending || !walletAvailable || !canWithdraw}>{pending ? <>Ожидание<span className="balance-withdraw__dots">...</span></> : 'Вывести'}</button>
      </form>}

      {(kind === 'deposit-amount' || kind === 'crypto-amount') && <form className="balance-withdraw" onSubmit={(event) => { event.preventDefault(); submitAmount(); }} aria-busy={pending}>
        {kind === 'deposit-amount' && <div className="balance-withdraw__wallet"><span><img src={walletIcon} alt="" /></span><span>{wallet.slice(0, 5)}...{wallet.slice(-6)}</span></div>}
        <label className="balance-withdraw__input">
          <span className="balance-withdraw__coin"><i><img src={tonIcon} alt="" /></i></span>
          <input aria-label="Сумма пополнения GRAM" inputMode="decimal" value={amount} placeholder="0.00" disabled={pending} onChange={(event) => { const value = event.target.value.replace(',', '.'); if (/^\d*(\.\d{0,9})?$/.test(value)) setAmount(value); }} />
          {amountNano !== null && amountNano > 0n && <small>{amountNano > MAX_ACTION ? 'Максимум 10000 GRAM' : balanceNano + amountNano > MAX_BALANCE ? 'Лимит баланса 100000 GRAM' : `Будет: ${formatNano(balanceNano + amountNano)} GRAM`}</small>}
        </label>
        <p className="balance-withdraw__available">{walletError ? <><span role="alert">Нет связи. </span><button type="button" onClick={() => void reload().catch(() => {})}>Обновить</button></> : <>Доступно: {formatNano(balanceNano)} GRAM</>}</p>
        <button type="submit" disabled={pending || walletPending || !walletAvailable || !canTopUp}>{pending ? <>Ожидание<span className="balance-withdraw__dots">...</span></> : 'Пополнить'}</button>
      </form>}

      {kind === 'gift-withdraw' && <>
        <div className="profile-modal__recipient"><UserAvatar user={user} /><span title={displayName(user)}>{displayName(user)}</span></div>
        <div className="profile-modal__gift-grid">{gifts.map((gift) => <article className="profile-gifts__card" key={gift.id}>
          <div className="profile-gifts__card-art" style={{ position: 'relative' }}><GiftArtwork gift={{ ...gift, price: String(gift.price) }} autoPlay={Boolean(requestedKind && visible)} /></div>
          <div className="profile-gifts__card-info"><strong>{gift.name}</strong><span>Модель&nbsp;&nbsp;{gift.model}</span></div>
          <div className="profile-gifts__card-price"><img src={tonIcon} alt="" />{gift.price.toFixed(3)}</div>
          <button type="button" className="profile-gifts__select" aria-label={`Выбрать ${gift.name}`} aria-pressed={selectedGiftIds.includes(gift.id)} disabled={withdrawalBusy} onClick={() => setSelectedGiftIds((current) => current.includes(gift.id) ? current.filter((id) => id !== gift.id) : [...current, gift.id])}>
            <img src={selectedGiftIds.includes(gift.id) ? selectActive : selectInactive} alt="" /><span><img src={selectedGiftIds.includes(gift.id) ? selectCheck : selectPlus} alt="" /></span>
          </button>
        </article>)}</div>
        <button className="profile-modal__bottom" type="button" disabled={selectedGifts.length === 0 || withdrawalBusy} onClick={() => onWithdraw(selectedGifts)}>{withdrawalBusy ? 'Ожидание...' : 'Вывести подарки'}</button>
      </>}

      {(kind === 'gift-result-success' || kind === 'gift-result-error') && <div className="profile-modal__result"><span className="profile-modal__result-icon"><img src={kind === 'gift-result-success' ? successIcon : errorIcon} alt="" /></span><p>{giftResultText}</p><button type="button" onClick={() => setKind(gifts.length ? 'gift-withdraw' : 'gift-empty')}>{kind === 'gift-result-success' ? 'Вернуться назад' : 'Попробовать снова'}</button></div>}


      {(kind === 'result-success' || kind === 'result-error') && <div className="profile-modal__result"><span className="profile-modal__result-icon"><img src={kind === 'result-success' ? successIcon : errorIcon} alt="" /></span><p>{resultText}</p><button type="button" onClick={() => { if (kind === 'result-success') setAmount(''); setKind(resultReturn); }}>{resultReturn ? kind === 'result-error' ? 'Попробовать снова' : 'Вернуться назад' : 'Готово'}</button></div>}
      </div>
    </section>
  </div>, document.body)}</>;
}

export default ProfileModal;
