import { useEffect, useRef, useState } from 'react';
import { useWallet } from '../../wallet/WalletProvider';
import { displayTon, formatNano } from '../../wallet/wallet';
import { useAnimatedBalance } from '../../hooks/useAnimatedBalance';
import '../../styles/press-feedback.css';
import SlideNotice from '../../components/feedback/SlideNotice/SlideNotice';
import { type Gift } from '../ExchangePage/data/gifts';
import { useInventory } from '../../inventory/InventoryProvider';
import GiftArtwork from '../../components/gifts/GiftArtwork/GiftArtwork';
import GiftWithdrawal from './components/GiftWithdrawal/GiftWithdrawal';
import ProfileModal, { type ProfileModalKind } from './components/ProfileModal/ProfileModal';
import { displayName, useUser } from '../../auth/AuthProvider';
import UserAvatar from '../../components/layout/UserAvatar';
import tonIcon from '../../assets/ton.svg';
import giftSelectedIcon from './assets/profile-use-gift-active.svg';
import giftInactiveIcon from './assets/profile-use-gift-inactive.svg';
import referralIcon from './assets/ref-ssilka.svg';
import selectionCheck from '../ExchangePage/assets/galochka.svg';
import selectionPlus from '../../assets/plus.svg';
import copyIcon from './assets/copy_referal_ssilka.svg';
import copiedIcon from './assets/copy_referal_ssilka_skopirovano.svg';
import walletIcon from './assets/coshelek.svg';
import walletCopyIcon from './assets/copy_coshelek.svg';
import walletUnlinkIcon from './assets/otvyasat_coshelek.svg';
import giftBackdrop from './assets/gift_add_backdrop.svg';
import giftBackdropMuted from './assets/gift_add_backdrop-nocolor.svg';
import giftSmallIcon from './assets/gift-small.svg';
import giftLargeIcon from './assets/gift-large.svg';
import giftExpandIcon from './assets/gift-expand.svg';
import giftCollapseIcon from './assets/gift-collapse.svg';
import inviteBackdrop from './assets/referal_invite_backdrop.svg';
import earnedBackdrop from './assets/referal_zarabotano_backdrop.svg';
import './ProfilePage.css';

export type ProfileGift = Omit<Gift, 'price'> & { price: number };


function ProfilePage({ balance, topUpRequest }: { balance: number; topUpRequest: number }) {
  const { wallet: walletSnapshot, pending: walletPending, error: walletError, available: walletAvailable, operate, reload } = useWallet();
  const referralReward = displayTon(walletSnapshot.referral_nano);
  const claimBusy = useRef(false);
  const [claimError, setClaimError] = useState('');
  const claimReferral = async () => {
    if (claimBusy.current || walletPending || !walletAvailable || BigInt(walletSnapshot.referral_nano) <= 0n) return;
    claimBusy.current = true; setClaimError('');
    try { await operate('referral'); }
    catch { setClaimError('Не удалось забрать демо-награду. Повторите попытку.'); }
    finally { claimBusy.current = false; }
  };
  const user = useUser();
  const name = displayName(user);
  const displayedBalance = useAnimatedBalance(balance);
  const [wallet, setWallet] = useState('');
  const [walletOpen, setWalletOpen] = useState(false);
  const { inventory, mutate } = useInventory();
  const gifts: ProfileGift[] = inventory.map((gift) => ({ ...gift, price: Number(gift.price) }));
  const [selectedGiftIds, setSelectedGiftIds] = useState<number[]>([]);
  const [withdrawalGifts, setWithdrawalGifts] = useState<ProfileGift[]>([]);
  const [withdrawalBusy, setWithdrawalBusy] = useState(false);
  const [withdrawalFromModal, setWithdrawalFromModal] = useState(false);
  const [giftResultText, setGiftResultText] = useState('');
  const [giftsExpanded, setGiftsExpanded] = useState(true);
  const [modal, setModal] = useState<ProfileModalKind | null>(null);
  const [referralCopied, setReferralCopied] = useState(false);
  const [walletCopied, setWalletCopied] = useState(false);
  useEffect(() => { if (topUpRequest > 0) setModal('deposit-choice'); }, [topUpRequest]);
  const referralLink = `${window.location.origin}/?ref=${encodeURIComponent(user.referral_code)}`;

  const copyText = async (value: string, onCopied: (copied: boolean) => void) => {
    try {
      await navigator.clipboard.writeText(value);
      onCopied(true);
      window.setTimeout(() => onCopied(false), 2000);
    } catch {
      onCopied(false);
    }
  };

  return <div className="profile-page">
    <div className="profile-page__glow" aria-hidden="true" />
    <header className="profile-header">
      <button className="profile-header__user" type="button" aria-label={`Профиль ${name}`}><UserAvatar user={user} /><span title={name}>{name}</span></button>
      <div className="profile-header__wallet-wrap" data-open={Boolean(wallet && walletOpen)}>
        <button className="profile-header__wallet" type="button" aria-expanded={walletOpen} onClick={() => wallet ? setWalletOpen((value) => !value) : setModal('wallet-connect')}>
          <span className="profile-header__wallet-icon"><img src={walletIcon} alt="" /></span>
          <span>{wallet ? `${wallet.slice(0, 4)}...` : 'Кошелёк'}</span>
          {wallet && <span className="profile-header__chevron" aria-hidden="true" />}
        </button>
        {wallet && walletOpen && <div className="profile-header__wallet-menu">
          <button type="button" onClick={() => copyText(wallet, setWalletCopied)}><span><img src={walletCopyIcon} alt="" /></span>{walletCopied ? 'Скопировано' : 'Скопировать'}</button>
          <button type="button" onClick={() => { setWallet(''); setWalletOpen(false); }}><span><img src={walletUnlinkIcon} alt="" /></span>Отвязать</button>
        </div>}
      </div>
    </header>

    <section className="profile-balance" aria-label="Ваш баланс">
      <span>Ваш баланс</span>
      <strong><img src={tonIcon} alt="" />{displayedBalance.toFixed(2)}</strong>
    </section>

    <div className="profile-actions">
      <button type="button" onClick={() => setModal('deposit-choice')}><span className="profile-actions__arrow" aria-hidden="true">↙</span>Пополнить</button>
      <button type="button" onClick={() => setModal('withdraw-choice')}><span className="profile-actions__arrow" aria-hidden="true">↗</span>Вывести</button>
      <button className="profile-actions__gift" type="button" aria-label="Пополнить подарки" onClick={() => setModal('gift-deposit')}><img src={giftLargeIcon} alt="" /><span aria-hidden="true">+</span></button>
    </div>

    <main className="profile-content">
      <p className="demo-inventory-caption">Тестовые подарки</p>
      {(walletError || claimError) && <p className="demo-wallet-error" role="alert">{claimError || walletError} <button type="button" disabled={walletPending} onClick={() => { setClaimError(''); void reload().catch(() => {}); }}>Обновить</button></p>}
      <section className="profile-gifts" aria-label="Ваши подарки">
        <div className="profile-gifts__header">
          <div className="profile-gifts__title"><span><img src={giftSmallIcon} alt="" /></span>Ваши подарки</div>
          <button type="button" disabled={gifts.length === 0} aria-label={gifts.length === 0 ? 'Нет подарков для сворачивания' : giftsExpanded ? 'Скрыть подарки' : 'Показать подарки'} aria-expanded={gifts.length === 0 || giftsExpanded} onClick={() => setGiftsExpanded((value) => !value)}><img src={gifts.length > 0 ? giftCollapseIcon : giftExpandIcon} alt="" /></button>
        </div>
        <div className="profile-gifts__collapse" data-expanded={gifts.length === 0 || giftsExpanded} inert={gifts.length > 0 && !giftsExpanded}>
          <div className="profile-gifts__collapse-inner"><div className="profile-gifts__grid">
          {gifts.length === 0 ? <>
            <button className="profile-gifts__placeholder" type="button" onClick={() => setModal('gift-deposit')}><img src={giftBackdrop} alt="" /><span>Добавить</span></button>
            <div className="profile-gifts__placeholder profile-gifts__placeholder--muted"><img src={giftBackdropMuted} alt="" /></div>
          </> : gifts.map((gift) => <article className="profile-gifts__card" key={gift.id}>
            <div className="profile-gifts__card-art" style={{ position: 'relative' }}><GiftArtwork gift={{ ...gift, price: String(gift.price) }} /></div>
            <div className="profile-gifts__card-info"><strong>{gift.name}</strong><span>Модель&nbsp;&nbsp;{gift.model}</span></div>
            <div className="profile-gifts__card-price"><img src={tonIcon} alt="" />{gift.price.toFixed(3)}</div>
            <button className="profile-gifts__select" type="button" aria-label={`Выбрать ${gift.name}`} aria-pressed={selectedGiftIds.includes(gift.id)} onClick={() => setSelectedGiftIds((current) => current.includes(gift.id) ? current.filter((id) => id !== gift.id) : [...current, gift.id])}>
              <img src={selectedGiftIds.includes(gift.id) ? giftSelectedIcon : giftInactiveIcon} alt="" />
              <span><img src={selectedGiftIds.includes(gift.id) ? selectionCheck : selectionPlus} alt="" /></span>
            </button>
          </article>)}
          </div></div>
        </div>
      </section>

      <section className="profile-referral" aria-label="Реферальная программа">
        <p>Приглашайте друзей и получайте <em>20% комиссии</em> от их обменов!</p>
        <div className="profile-referral__stats">
          <div className="profile-referral__stat"><img src={inviteBackdrop} alt="" /><span>Приглашено</span><strong>0 чел.</strong><button type="button" onClick={() => copyText(referralLink, setReferralCopied)}>{referralCopied ? 'Скопировано' : 'Пригласить'}</button></div>
          <div className="profile-referral__stat"><img src={earnedBackdrop} alt="" /><span>Демо-награда</span><strong>{referralReward === 0 ? '0' : referralReward.toFixed(3)} TON</strong><button type="button" disabled={BigInt(walletSnapshot.referral_nano) === 0n || walletPending || !walletAvailable} onClick={claimReferral}>{walletPending && claimBusy.current ? 'Ожидание...' : 'Забрать'}</button></div>
        </div>
      </section>
      <div className="profile-referral-link"><div><img src={referralIcon} alt="" /><span>Реферальная ссылка</span></div><button type="button" aria-label="Скопировать реферальную ссылку" onClick={() => copyText(referralLink, setReferralCopied)}><img src={referralCopied ? copiedIcon : copyIcon} alt="" /></button></div>
      <details className="demo-wallet-history"><summary>История тестовых операций</summary><ul>{walletSnapshot.transactions.slice(0, 10).map((transaction) => <li key={transaction.id}><span>{({ seed: 'Начальный баланс', topup: 'Демо-пополнение', withdraw: 'Демо-вывод', referral: 'Демо-награда', loan_credit: 'Выдача займа', loan_repay: 'Погашение займа', loan_interest: 'Проценты по займу', loan_extend: 'Продление займа' })[transaction.kind]}<small>{new Date(transaction.created_at * 1000).toLocaleString('ru-RU')}</small></span><strong>{BigInt(transaction.amount_nano) > 0n ? '+' : ''}{formatNano(transaction.amount_nano)} TON</strong></li>)}</ul></details>
    </main>

    <SlideNotice show={!withdrawalBusy && gifts.some((gift) => selectedGiftIds.includes(gift.id))}><button className="profile-withdraw-selected" type="button" onClick={() => { setWithdrawalFromModal(false); setWithdrawalGifts(gifts.filter((gift) => selectedGiftIds.includes(gift.id))); }}>Вывести подарки</button></SlideNotice>
    <GiftWithdrawal gifts={withdrawalGifts} onClose={() => setWithdrawalGifts([])} onBusy={setWithdrawalBusy} onResult={withdrawalFromModal ? (success, withdrawn) => { setGiftResultText(success ? `Вы успешно вывели ${withdrawn.map((gift) => gift.name).join(', ')} стоимостью ${withdrawn.reduce((sum, gift) => sum + gift.price, 0).toFixed(3)} TON` : 'Вывод подарков не удался...'); setModal(success ? 'gift-result-success' : 'gift-result-error'); } : undefined} onSuccess={(ids) => {
      return mutate('withdraw', { ids }).then(() => {
      setSelectedGiftIds((current) => current.filter((id) => !ids.includes(id)));
      });
    }} />
    <ProfileModal kind={modal} setKind={setModal} wallet={wallet} setWallet={setWallet} gifts={gifts} withdrawalBusy={withdrawalBusy} giftResultText={giftResultText} onWithdraw={(selected) => { setWithdrawalFromModal(true); setWithdrawalGifts(selected); }} />
  </div>;
}

export default ProfilePage;
