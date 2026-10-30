import { useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { createPortal } from 'react-dom';
import GiftArtwork from '../../../../components/gifts/GiftArtwork/GiftArtwork';
import type { ProfileGift } from '../../ProfilePage';
import tonIcon from '../../../../assets/ton.svg';
import { displayName, useUser } from '../../../../auth/AuthProvider';
import UserAvatar from '../../../../components/layout/UserAvatar';
import { useInventory } from '../../../../inventory/InventoryProvider';
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
import './ProfileModal.css';
import { useModalScrollLock } from '../../../../hooks/useModalScrollLock';

export type ProfileModalKind =
  | 'deposit-choice' | 'withdraw-choice' | 'wallet-warning' | 'wallet-connect'
  | 'gift-deposit' | 'gift-empty' | 'deposit-amount' | 'crypto-amount'
  | 'withdraw-amount' | 'gift-withdraw'
  | 'gift-result-success' | 'gift-result-error'
  | 'referral-claim' | 'result-success' | 'result-error';

type ProfileModalProps = {
  kind: ProfileModalKind | null;
  setKind: (kind: ProfileModalKind | null) => void;
  wallet: string;
  setWallet: (wallet: string) => void;
  balance: number;
  setBalance: Dispatch<SetStateAction<number>>;
  gifts: ProfileGift[];
  referralReward: number;
  setReferralReward: Dispatch<SetStateAction<number>>;
  withdrawalBusy: boolean;
  onWithdraw: (gifts: ProfileGift[]) => void;
  giftResultText: string;
};

function ProfileModal({ kind: requestedKind, setKind, wallet, setWallet, balance, setBalance, gifts, referralReward, setReferralReward, withdrawalBusy, onWithdraw, giftResultText }: ProfileModalProps) {
  const { mutate } = useInventory();
  const user = useUser();
  const [lastKind, setLastKind] = useState(requestedKind);
  const kind = requestedKind ?? lastKind;
  const [mounted, setMounted] = useState(kind !== null);
  const [visible, setVisible] = useState(false);
  const [amount, setAmount] = useState('');
  const [walletInput, setWalletInput] = useState('');
  const [selectedGiftIds, setSelectedGiftIds] = useState<number[]>([]);
  const [resultText, setResultText] = useState('');
  const [pending, setPending] = useState(false);
  const [resultReturn, setResultReturn] = useState<ProfileModalKind | null>(null);
  const [demoWalletBalance, setDemoWalletBalance] = useState(849.28);
  const depositAttempts = useRef({ 'deposit-amount': 0, 'crypto-amount': 0 });
  const withdrawalTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const withdrawalAttempt = useRef(0);
  const pendingRef = useRef(false);
  useEffect(() => {
    clearTimeout(withdrawalTimer.current);
    pendingRef.current = false;
    setPending(false);
    return () => clearTimeout(withdrawalTimer.current);
  }, [requestedKind]);
  const [walletReturn, setWalletReturn] = useState<ProfileModalKind>('deposit-choice');
  useModalScrollLock(mounted);

  useEffect(() => {
    let firstFrame = 0;
    let secondFrame = 0;
    let closeTimer = 0;
    if (requestedKind) {
      setLastKind(requestedKind);
      setMounted(true);
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => setVisible(true));
      });
    } else {
      setVisible(false);
      closeTimer = window.setTimeout(() => setMounted(false), 360);
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

  const complete = (message: string, success: boolean, withdrawal = false) => {
    setResultReturn(withdrawal ? 'withdraw-amount' : kind === 'deposit-amount' || kind === 'crypto-amount' ? kind : null);
    setResultText(message);
    setKind(success ? 'result-success' : 'result-error');
  };

  const submitAmount = () => {
    const value = Number(amount);
    if (!Number.isFinite(value) || value <= 0 || pendingRef.current) return;
    if (kind === 'withdraw-amount') {
      if (value > balance || !wallet) return;
      pendingRef.current = true;
      setPending(true);
      const success = withdrawalAttempt.current++ % 2 === 0;
      withdrawalTimer.current = setTimeout(() => {
        pendingRef.current = false;
        setPending(false);
        if (success) setBalance((current) => Math.max(0, Math.round((current - value) * 1e9) / 1e9));
        complete(success ? `Вы успешно вывели ${value.toFixed(3)} TON!` : 'Вывод не удался...', success, true);
      }, 1800);
    } else if (kind === 'deposit-amount' || kind === 'crypto-amount') {
      if (kind === 'deposit-amount' && (!wallet || value > demoWalletBalance)) return;
      const source = kind;
      const success = depositAttempts.current[source]++ % 2 === 0;
      pendingRef.current = true;
      setPending(true);
      // Demo payment outcome until a payment provider is connected.
      withdrawalTimer.current = setTimeout(() => {
        pendingRef.current = false;
        setPending(false);
        if (success) {
          setBalance((current) => Math.round((current + value) * 1e9) / 1e9);
          if (source === 'deposit-amount') setDemoWalletBalance((current) => Math.max(0, Math.round((current - value) * 1e9) / 1e9));
        }
        complete(success ? `Вы успешно пополнили ${value.toFixed(3)} TON!` : 'Пополнить не удалось...', success);
      }, 1800);
    }
  };

  const back = () => {
    if (kind === 'wallet-connect') setKind('wallet-warning');
    else if (kind === 'wallet-warning') setKind(walletReturn === 'withdraw-amount' ? 'withdraw-choice' : 'deposit-choice');
    else if (kind === 'gift-deposit' || kind === 'crypto-amount' || kind === 'deposit-amount') setKind('deposit-choice');
    else if (kind === 'gift-withdraw' || kind === 'gift-empty' || kind === 'withdraw-amount') setKind('withdraw-choice');
    else setKind(null);
  };

  if (!mounted) return null;

  const title = kind === 'deposit-choice' ? 'Пополнение'
    : kind === 'deposit-amount' ? 'Балансом'
    : kind === 'crypto-amount' ? 'CryptoBot'
    : kind === 'gift-deposit' ? 'Подарки'
    : kind === 'withdraw-choice' ? 'Вывод'
      : kind === 'gift-withdraw' || kind === 'gift-empty' ? 'Подарки'
      : kind === 'gift-result-success' ? 'Успешно!' : kind === 'gift-result-error' ? 'Ошибка'
      : kind === 'wallet-warning' && walletReturn === 'withdraw-amount' ? 'Баланс'
        : kind === 'wallet-warning' || kind === 'wallet-connect' ? 'Кошелёк'
          : kind === 'result-success' ? 'Успешно!' : kind === 'result-error' ? 'Ошибка' : 'Баланс';
  const short = kind === 'wallet-warning' || kind === 'wallet-connect' || kind === 'referral-claim';
  const selectedGifts = gifts.filter((gift) => selectedGiftIds.includes(gift.id));

  return createPortal(<div className="profile-modal-layer" data-visible={visible} onTransitionEnd={(event) => {
    if (event.target === event.currentTarget && !requestedKind && event.propertyName === 'background-color') setMounted(false);
  }}>
    <button className="profile-modal-scrim" type="button" aria-label="Закрыть окно" onClick={() => setKind(null)} />
    <section className="profile-modal" data-short={short} data-kind={kind} role="dialog" aria-modal="true" aria-label={title}>
      <div className="profile-modal__handle" aria-hidden="true" />
      <header className="profile-modal__header">
        <h2>{title}</h2>
        <button className="profile-modal__close" type="button" aria-label="Закрыть окно" onClick={() => setKind(null)}><img src={closeIcon} alt="" /></button>
        {kind !== 'deposit-choice' && kind !== 'withdraw-choice' && !kind?.includes('result-') && <button className="profile-modal__back" type="button" aria-label="Назад" onClick={back}>‹</button>}
      </header>

      {kind === 'deposit-choice' && <div className="profile-modal__choices">
        <button type="button" onClick={() => chooseWalletFlow('deposit-amount')}><i className="profile-modal__choice-icon"><i><img src={withdrawBalanceIcon} alt="" /></i></i><span>Балансом</span><small>Вашего кошелька</small></button>
        <button type="button" onClick={() => { setAmount(''); setKind('crypto-amount'); }}><i className="profile-modal__choice-icon profile-modal__choice-icon--crypto"><i><img src={cryptoIcon} alt="" /></i></i><span>CryptoBot</span><small>Создайте и оплатите чек</small></button>
        <button type="button" onClick={() => setKind('gift-deposit')}><i className="profile-modal__choice-icon"><i><img src={withdrawGiftIcon} alt="" /></i></i><span>Подарками</span><small>С вашего профиля</small></button>
      </div>}

      {kind === 'withdraw-choice' && <div className="profile-modal__choices">
        <button type="button" onClick={() => chooseWalletFlow('withdraw-amount')}><i className="profile-modal__choice-icon"><i><img src={withdrawBalanceIcon} alt="" /></i></i><span>Баланс</span><small>На ваш кошелёк</small></button>
        <button type="button" onClick={() => { setSelectedGiftIds([]); setKind(gifts.length ? 'gift-withdraw' : 'gift-empty'); }}><i className="profile-modal__choice-icon"><i><img src={withdrawGiftIcon} alt="" /></i></i><span>Подарки</span><small>В ваш профиль</small></button>
      </div>}

      {kind === 'wallet-warning' && <div className="profile-modal__wallet-warning"><p>Вы не подключили свой кошелёк :(</p><button type="button" onClick={() => { setWalletInput(''); setKind('wallet-connect'); }}>Подключить</button></div>}

      {kind === 'wallet-connect' && <div className="profile-modal__form"><label>Кошелёк<input value={walletInput} onChange={(event) => setWalletInput(event.target.value.trim())} placeholder="Адрес TON кошелька" autoComplete="off" /></label><button type="button" disabled={walletInput.length < 10} onClick={() => { setWallet(walletInput); setKind(walletReturn); }}>Подключить</button></div>}

      {kind === 'gift-deposit' && <><div className="profile-modal__gift-deposit"><p>Тестовые подарки</p><button type="button" disabled={pending} onClick={async () => { if (pendingRef.current) return; pendingRef.current = true; setPending(true); try { await mutate('deposit'); complete('Тестовые подарки добавлены', true); } catch { complete('Не удалось добавить подарки', false); } finally { pendingRef.current = false; setPending(false); } }}>{pending ? 'Ожидание...' : 'Добавить'}</button></div><button className="profile-modal__bottom profile-modal__bottom--glass" type="button" onClick={() => setKind(null)}>Закрыть</button></>}

      {kind === 'gift-empty' && <><div className="profile-modal__empty-gifts"><strong>В вашем инвентаре пусто!</strong><p>Отправьте подарок нам что бы это исправить!</p><button type="button" onClick={() => setKind('gift-deposit')}>GiftRelayer</button></div><button className="profile-modal__bottom profile-modal__bottom--glass" type="button" onClick={() => setKind('withdraw-choice')}>Вернуться назад</button></>}

      {kind === 'withdraw-amount' && <form className="balance-withdraw" onSubmit={(event) => { event.preventDefault(); submitAmount(); }} aria-busy={pending}>
        <div className="balance-withdraw__wallet"><span><img src={walletIcon} alt="" /></span><span>{wallet.slice(0, 5)}...{wallet.slice(-6)}</span></div>
        <label className="balance-withdraw__input">
          <span className="balance-withdraw__coin"><i><img src={tonIcon} alt="" /></i></span>
          <input aria-label="Сумма вывода TON" inputMode="decimal" value={amount} placeholder="0.00" disabled={pending} onChange={(event) => { const value = event.target.value.replace(',', '.'); if (/^\d*(\.\d{0,9})?$/.test(value)) setAmount(value); }} />
          {Number(amount) > 0 && <small>{Number(amount) > balance ? 'Недостаточно TON' : `Останется: ${(balance - Number(amount)).toFixed(3)} TON`}</small>}
        </label>
        <p className="balance-withdraw__available">Доступно для вывода: {balance.toFixed(3)} TON</p>
        <button type="submit" disabled={pending || !Number.isFinite(Number(amount)) || Number(amount) <= 0 || Number(amount) > balance || !wallet}>{pending ? <>Ожидание<span className="balance-withdraw__dots">...</span></> : 'Вывести'}</button>
      </form>}

      {(kind === 'deposit-amount' || kind === 'crypto-amount') && <form className="balance-withdraw" onSubmit={(event) => { event.preventDefault(); submitAmount(); }} aria-busy={pending}>
        {kind === 'deposit-amount' && <div className="balance-withdraw__wallet"><span><img src={walletIcon} alt="" /></span><span>{wallet.slice(0, 5)}...{wallet.slice(-6)}</span></div>}
        <label className="balance-withdraw__input">
          <span className="balance-withdraw__coin"><i><img src={tonIcon} alt="" /></i></span>
          <input aria-label="Сумма пополнения TON" inputMode="decimal" value={amount} placeholder="0.00" disabled={pending} onChange={(event) => { const value = event.target.value.replace(',', '.'); if (/^\d*(\.\d{0,9})?$/.test(value)) setAmount(value); }} />
          {kind === 'deposit-amount' && Number(amount) > 0 && <small>{Number(amount) > demoWalletBalance ? 'Недостаточно TON' : `Останется: ${(demoWalletBalance - Number(amount)).toFixed(3)} TON`}</small>}
        </label>
        {kind === 'deposit-amount' && <p className="balance-withdraw__available">Доступно для пополнения: {demoWalletBalance.toFixed(3)} TON</p>}
        <button type="submit" disabled={pending || !Number.isFinite(Number(amount)) || Number(amount) <= 0 || (kind === 'deposit-amount' && (!wallet || Number(amount) > demoWalletBalance))}>{pending ? <>{kind === 'crypto-amount' ? 'Ожидание оплаты' : 'Ожидание'}<span className="balance-withdraw__dots">...</span></> : kind === 'crypto-amount' ? 'Создать чек' : 'Пополнить'}</button>
      </form>}

      {kind === 'gift-withdraw' && <>
        <div className="profile-modal__recipient"><UserAvatar user={user} /><span title={displayName(user)}>{displayName(user)}</span></div>
        <div className="profile-modal__gift-grid">{gifts.map((gift) => <article className="profile-gifts__card" key={gift.id}>
          <div className="profile-gifts__card-art" style={{ position: 'relative' }}><GiftArtwork gift={{ ...gift, price: String(gift.price) }} /></div>
          <div className="profile-gifts__card-info"><strong>{gift.name}</strong><span>Модель&nbsp;&nbsp;{gift.model}</span></div>
          <div className="profile-gifts__card-price"><img src={tonIcon} alt="" />{gift.price.toFixed(3)}</div>
          <button type="button" className="profile-gifts__select" aria-label={`Выбрать ${gift.name}`} aria-pressed={selectedGiftIds.includes(gift.id)} disabled={withdrawalBusy} onClick={() => setSelectedGiftIds((current) => current.includes(gift.id) ? current.filter((id) => id !== gift.id) : [...current, gift.id])}>
            <img src={selectedGiftIds.includes(gift.id) ? selectActive : selectInactive} alt="" /><span><img src={selectedGiftIds.includes(gift.id) ? selectCheck : selectPlus} alt="" /></span>
          </button>
        </article>)}</div>
        <button className="profile-modal__bottom" type="button" disabled={selectedGifts.length === 0 || withdrawalBusy} onClick={() => onWithdraw(selectedGifts)}>{withdrawalBusy ? 'Ожидание...' : 'Вывести подарки'}</button>
      </>}

      {(kind === 'gift-result-success' || kind === 'gift-result-error') && <div className="profile-modal__result"><span className="profile-modal__result-icon"><img src={kind === 'gift-result-success' ? successIcon : errorIcon} alt="" /></span><p>{giftResultText}</p><button type="button" onClick={() => setKind(gifts.length ? 'gift-withdraw' : 'gift-empty')}>{kind === 'gift-result-success' ? 'Вернуться назад' : 'Попробовать снова'}</button></div>}

      {kind === 'referral-claim' && <div className="profile-modal__message"><h3>Заработано</h3><p>{referralReward.toFixed(3)} TON</p><button type="button" disabled={referralReward === 0} onClick={() => { setBalance((current) => current + referralReward); setReferralReward(0); complete(`Вы забрали ${referralReward.toFixed(3)} TON`, true); }}>Забрать</button></div>}

      {(kind === 'result-success' || kind === 'result-error') && <div className="profile-modal__result"><span className="profile-modal__result-icon"><img src={kind === 'result-success' ? successIcon : errorIcon} alt="" /></span><p>{resultText}</p><button type="button" onClick={() => { if (kind === 'result-success') setAmount(''); setKind(resultReturn); }}>{resultReturn ? kind === 'result-error' ? 'Попробовать снова' : 'Вернуться назад' : 'Готово'}</button></div>}
    </section>
  </div>, document.body);
}

export default ProfileModal;
