import { useState } from 'react';
import ExchangePage from '../ExchangePage/ExchangePage';
import ProfilePage from '../ProfilePage/ProfilePage';
import DepositPage from '../DepositPage/DepositPage';
import PageFooter, { type PageSection } from '../../components/layout/PageFooter/PageFooter';
import { useWallet } from '../../wallet/WalletProvider';
import { displayTon } from '../../wallet/wallet';

function HomePage() {
  const [activePage, setActivePage] = useState<PageSection>('exchange');
  const { wallet } = useWallet();
  const balance = displayTon(wallet.balance_nano);
  const [topUpRequest, setTopUpRequest] = useState(0);
  const openTopUp = () => setTopUpRequest((value) => value + 1);
  const navigate = (page: PageSection) => {
    if (page === activePage) return;
    setActivePage(page);
    window.scrollTo(0, 0);
  };
  return <>
    <div hidden={activePage !== 'profile'}><ProfilePage balance={balance} topUpRequest={topUpRequest} /></div>
    {activePage === 'deposit' && <DepositPage balance={balance} onTopUp={openTopUp} onNavigateProfile={() => navigate('profile')} />}
    {activePage === 'exchange' && <ExchangePage balance={balance} onTopUp={openTopUp} onNavigateProfile={() => navigate('profile')} />}
    <PageFooter active={activePage} onNavigate={navigate} />
  </>;
}

export default HomePage;
