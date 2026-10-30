import { useAnimatedBalance } from '../../../hooks/useAnimatedBalance';
import { displayName, useUser } from '../../../auth/AuthProvider';
import UserAvatar from '../UserAvatar';
import tonIcon from '../../../assets/ton.svg';
import plusIcon from '../../../assets/plus.svg';
import './PageHeader.css';

type PageHeaderProps = {
  balance: number;
  onNavigateProfile: () => void;
  onTopUp: () => void;
};

export default function PageHeader({ balance, onNavigateProfile, onTopUp }: PageHeaderProps) {
  const user = useUser();
  const name = displayName(user);
  const displayedBalance = useAnimatedBalance(balance);
  return <header className="exchange-header">
    <button className="exchange-user" type="button" aria-label="Открыть профиль" onClick={onNavigateProfile}>
      <UserAvatar user={user} /><span title={name}>{name}</span>
    </button>
    <div className="exchange-balance-group" aria-label={`Тестовый баланс ${balance.toFixed(2)} TON`}>
      <div className="exchange-balance">
        <small className="exchange-balance__demo-label">Тестовый баланс</small>
        <span className="exchange-ton-icon" aria-hidden="true"><img src={tonIcon} alt="" /></span>
        <span className="exchange-balance__amount">{displayedBalance.toFixed(2)}</span>
        <button className="exchange-balance__add" type="button" aria-label="Пополнить тестовый баланс" onClick={onTopUp}><img src={plusIcon} alt="" /></button>
      </div>
    </div>
  </header>;
}
