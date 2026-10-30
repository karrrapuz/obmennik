import PageHeader from '../../components/layout/PageHeader/PageHeader';
import { useState, useSyncExternalStore } from 'react';
import SlideNotice from '../../components/feedback/SlideNotice/SlideNotice';
import LockKeyhole from './assets/block-zalog-gift.svg';
import type { Gift } from '../ExchangePage/data/gifts';
import supportedPepe from './assets/gifts_emoji_by_gifts_changes_bot_AgADpWAAAh80YUo.png';
import supportedLocket from './assets/gifts_emoji_by_gifts_changes_bot_AgADjXUAAtmUcEo.png';
import supportedPeach from './assets/gifts_emoji_by_gifts_changes_bot_AgADNGAAAnlKWUo.png';
import supportedCap from './assets/gifts_emoji_by_gifts_changes_bot_AgADaFwAAk7xGUo.png';
import giftBlur from './assets/gift-blur.svg';
import giftExpandIcon from '../ProfilePage/assets/gift-expand.svg';
import giftExpandActiveIcon from './assets/gift-expand-active.svg';
import ton from '../../assets/ton.svg';
import '../../styles/press-feedback.css';
import bannerExchange from './assets/banner-exchange.svg';
import PledgeModal from './components/PledgeModal';
import GiftArtwork from '../../components/gifts/GiftArtwork/GiftArtwork';
import PledgePayment from './components/PledgePayment';
import pledgeIcon from './assets/zalog-gift-icon.svg';
import timeIcon from './assets/zalog-gift-time.svg';
import check from '../ExchangePage/assets/galochka.svg';
import { pledgeStore } from './services/pledgeStore';
import './DepositPage.css';

export default function DepositPage({ onNavigateProfile, onTopUp, balance }: { onNavigateProfile: () => void; onTopUp: () => void; balance: number }) {
  const state = useSyncExternalStore(pledgeStore.subscribe, pledgeStore.getSnapshot);
  const [tab, setTab] = useState<'inventory' | 'pledges'>('inventory');
  const [gift, setGift] = useState<Gift | null>(null);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [paymentIds, setPaymentIds] = useState<number[] | null>(null);
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState(false);
  const items = tab === 'inventory' ? state.inventory : state.pledges.map((item) => item.gift);
  return <main className="deposit-page" aria-label="Залог">
    <PageHeader balance={balance} onNavigateProfile={onNavigateProfile} onTopUp={onTopUp} />
    <section className="pledge-banner">
      <div className="pledge-banner__art" aria-hidden="true">
        <div className="pledge-banner__gift"><span /></div>
        <i className="pledge-banner__ton pledge-banner__ton--back"><img src={ton} alt="" /></i>
        <i className="pledge-banner__ton pledge-banner__ton--front"><img src={ton} alt="" /></i>
        <i className="pledge-banner__ton pledge-banner__ton--bottom"><img src={ton} alt="" /></i>
        <span className="pledge-banner__exchange"><img src={bannerExchange} alt="" /></span>
      </div>
      <h1>Нужны тоны?</h1><p>Возьми их у нас под залог своих подарков!</p>
    </section>
    <div className="pledge-tabs" role="tablist" aria-label="Подарки" data-active={tab}><span aria-hidden="true" /><button role="tab" aria-selected={tab === 'inventory'} onClick={() => setTab('inventory')}>Инвентарь</button><button role="tab" aria-selected={tab === 'pledges'} onClick={() => setTab('pledges')}>Залог{state.pledges.length > 0 && <small className="pledge-tab-count">{state.pledges.length}</small>}</button></div>
    <section className="pledge-catalog" role="tabpanel" aria-label={tab === 'inventory' ? 'Инвентарь' : 'Залоги'}>
      <p className="demo-inventory-caption">Тестовые подарки · Демо-займы</p>
      {tab === 'pledges' && <div className="pledge-search"><input aria-label="Поиск залогов" placeholder="Поиск" value={search} onChange={(event) => setSearch(event.target.value)} /><button aria-label={collapsed ? 'Раскрыть подарки' : 'Свернуть подарки'} aria-expanded={!collapsed} disabled={!items.length} onClick={() => setCollapsed(!collapsed)}><img src={!items.length ? giftExpandIcon : giftExpandActiveIcon} alt="" /></button></div>}
      <div className="pledge-collapse" data-collapsed={tab === 'pledges' && collapsed} inert={tab === 'pledges' && collapsed}><div>
      {items.length ? <div className="pledge-grid">{items.filter((item) => tab === 'inventory' || `${item.name} ${item.model}`.toLowerCase().includes(search.toLowerCase())).map((item) => {
        const loan = state.pledges.find((p) => p.gift.id === item.id);
        return <article className="pledge-card" data-loan={tab === 'pledges'} data-selected={selected.includes(item.id)} key={item.id}>
          <button className="pledge-card__open" disabled={tab === 'inventory' && item.pledgeSupported === false} aria-label={item.pledgeSupported === false ? `${item.name}: не поддерживается для залога` : `Открыть ${item.name}`} onClick={() => { setGift(item); setOpen(true); }}><div className="pledge-card__art"><GiftArtwork gift={item} />{tab === 'inventory' && item.pledgeSupported === false && <div className="pledge-card__locked"><img src={LockKeyhole} alt="" /><span>Не поддерживается</span></div>}<div className="pledge-card__caption"><strong>{item.name}</strong><small>{item.modelName ?? 'Модель'}&nbsp;&nbsp;{item.model}</small></div></div></button>
          {tab === 'inventory' ? <span className="pledge-card__price"><img src={ton} alt="" />{item.price}</span> : <>
            <button className="pledge-card__loan-icon" aria-label={`Информация о залоге ${item.name}`} onClick={() => { setGift(item); setOpen(true); }}><img src={pledgeIcon} alt="" /></button>
            <button className="pledge-card__select" aria-label={`Выбрать ${item.name}`} aria-pressed={selected.includes(item.id)} disabled={loan?.status !== 'active'} onClick={() => setSelected((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])}>{selected.includes(item.id) && <b><img src={check} alt="" /></b>}</button>
            <div className="pledge-card__due"><span><img src={timeIcon} alt="" /></span><div><small>{loan?.status === 'processing' ? 'Обработка...' : 'Дата выкупа до'}</small><strong>{loan && new Date(loan.dueAt).toLocaleDateString('ru-RU')} ({loan && new Date(loan.dueAt).toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit'})})</strong></div></div>
          </>}
        </article>;
      })}</div> : tab === 'inventory' ? <div className="pledge-empty pledge-empty--inventory"><strong>В вашем инвентаре пусто!</strong><p>Отправьте подарок нам что бы это исправить!</p><button onClick={onNavigateProfile}>GiftRelayer</button></div> : <div className="pledge-empty-loans"><img className="pledge-empty-loans__cards" src={giftBlur} alt="" /><p>У вас нет подарков в залоге</p></div>}
      </div></div>
      {tab === 'pledges' && <section className="pledge-supported"><h2>Поддерживаемые подарки</h2>{[['Plush Pepes','1800',supportedPepe],['Heart Lockets','1200',supportedLocket],['Durov’s Caps','454.45',supportedCap],['Precious Peaches','234.50',supportedPeach]].map(([name,amount,icon]) => <button key={name} onClick={() => setTab('inventory')}><span className="pledge-supported__icon"><img src={icon} alt="" /></span><span className="pledge-supported__text"><strong>{name}</strong><small>Получите: <span>{amount} TON</span> / 14 дней</small></span></button>)}</section>}
    </section>
    <SlideNotice show={tab === 'pledges' && selected.some((id) => state.pledges.some((p) => p.gift.id === id && p.status === 'active'))}><button className="pledge-extend-button" onClick={() => setPaymentIds(selected.filter((id) => state.pledges.some((p) => p.gift.id === id && p.status === 'active')))}>Продлить</button></SlideNotice>
    {paymentIds && <PledgePayment ids={paymentIds} onClose={() => { setPaymentIds(null); setSelected([]); }} onTopUp={onNavigateProfile} />}
    <PledgeModal gift={gift} open={open} onClose={() => setOpen(false)} pledge={state.pledges.find((item) => item.gift.id === gift?.id)} onCreated={() => setTab('pledges')} />
  </main>;
}
