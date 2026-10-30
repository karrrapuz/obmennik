import PageHeader from '../../components/layout/PageHeader/PageHeader';
import { useEffect, useRef, useState } from 'react';
import FilterModal, { type AppliedFilters } from './components/FilterModal/FilterModal';
import SortModal, { type SortOption } from './components/SortModal/SortModal';
import ExchangeModal from './components/ExchangeModal/ExchangeModal';
import GiftDetailsModal from './components/GiftDetailsModal/GiftDetailsModal';
import ShortageNotice from './components/ShortageNotice/ShortageNotice';
import { type Gift, matchesGiftAttributes } from './data/gifts';
import GiftArtwork from '../../components/gifts/GiftArtwork/GiftArtwork';
import { useGiftLists } from './hooks/useGiftLists';
import { ExchangeDraft } from './services/ExchangeDraft';
import './styles/page.css';
import './styles/exchange-summary.css';
import './styles/catalog.css';
import './styles/section-switcher.css';
import '../../styles/press-feedback.css';
import filterIcon from './assets/filter.svg';
import filterSortIcon from './assets/filter2.svg';
import filterActiveIcon from './assets/filter-active.svg';
import sorterActiveIcon from './assets/sorter-active.svg';
import giftIcon from './assets/gift.svg';
import activeGiftIcon from './assets/obmen_gift_active.svg';
import giftAddonIcon from './assets/gift-addon.svg';
import selectedGiftIcon from './assets/galochka.svg';
import searchIcon from './assets/lupa_poisk.svg';
import plusIcon from '../../assets/plus.svg';
import tonIcon from '../../assets/ton.svg';
import subtractObmenIcon from './assets/Subtract_obmen.svg';


function ExchangePage({ onNavigateProfile, onTopUp, balance }: { onNavigateProfile: () => void; onTopUp: () => void; balance: number }) {
  const { catalog: gifts, inventory: inventoryGifts, loading, error, reload, exchange } = useGiftLists();
  const [activeSection, setActiveSection] = useState<'inventory' | 'exchange'>('exchange');
  const [receivedIds, setReceivedIds] = useState<number[]>([]);
  const [offeredIds, setOfferedIds] = useState<number[]>([]);
  const selectedGiftIds = activeSection === 'inventory' ? offeredIds : receivedIds;
  const [giftDetails, setGiftDetails] = useState<{ gift: Gift; source: 'inventory' | 'exchange' } | null>(null);
  const [giftDetailsOpen, setGiftDetailsOpen] = useState(false);
  const toggleGift = (id: number, source = activeSection) => (source === 'inventory' ? setOfferedIds : setReceivedIds)((current) => new ExchangeDraft(current).toggle(id).ids);
  const [exchangeOpen, setExchangeOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filterCount, setFilterCount] = useState(0);
  const [appliedFilters, setAppliedFilters] = useState<AppliedFilters | null>(null);
  const [filterResetVersion, setFilterResetVersion] = useState(0);
  const [sortOpen, setSortOpen] = useState(false);
  const [sortOptions, setSortOptions] = useState<SortOption[]>([]);
  useEffect(() => {
    setOfferedIds((current) => current.filter((id) => inventoryGifts.some((gift) => gift.id === id)));
    setReceivedIds((current) => current.filter((id) => gifts.some((gift) => gift.id === id)));
  }, [inventoryGifts, gifts]);

  const clearFilters = () => {
    setAppliedFilters(null);
    setFilterCount(0);
    setFilterResetVersion((value) => value + 1);
  };

  const applyFilters = (filters: AppliedFilters) => {
    setAppliedFilters(filters);
    setFilterCount(Object.values(filters.selected).reduce((total, values) => total + values.length, 0)
      + Number(Boolean(filters.fromPrice || filters.toPrice)));
  };

  const visibleGifts = (activeSection === 'inventory' ? inventoryGifts : gifts)
    .filter((gift) => {
      if (!gift.name.toLowerCase().includes(searchQuery.trim().toLowerCase())) return false;
      if (!appliedFilters) return true;
      const price = Number(gift.price);
      if (appliedFilters.fromPrice && price < Number(appliedFilters.fromPrice)) return false;
      if (appliedFilters.toPrice && price > Number(appliedFilters.toPrice)) return false;
      return matchesGiftAttributes(gift, appliedFilters.selected);
    })
    .sort((first, second) => {
      for (const option of sortOptions) {
        let difference = 0;
        if (option === 'newest' || option === 'id-desc') difference = second.id - first.id;
        if (option === 'id-asc') difference = first.id - second.id;
        if (option === 'price-asc') difference = Number(first.price) - Number(second.price);
        if (option === 'price-desc') difference = Number(second.price) - Number(first.price);
        if (difference !== 0) return difference;
      }
      return 0;
    });

  const selectedGifts = new ExchangeDraft(receivedIds).selectFrom(gifts);
  const offeredGifts = new ExchangeDraft(offeredIds).selectFrom(inventoryGifts);
  const offeredAmount = offeredGifts.reduce((total, gift) => total + Number(gift.price), 0);
  const receivedAmount = selectedGifts.reduce((total, gift) => total + Number(gift.price), 0);
  const [exchangeAnimation, setExchangeAnimation] = useState({ amount: 0, offered: 0, activation: 0, offerActivation: 0 });
  const animationValue = useRef(exchangeAnimation);
  const displayedReceivedAmount = exchangeAnimation.amount;
  const hasSelectedGifts = offeredGifts.length + selectedGifts.length > 0;
  const formatAmount = (amount: number) => amount.toFixed(3);

  useEffect(() => {
    const start = animationValue.current;
    const targetActivation = Number(hasSelectedGifts);
    const targetOfferActivation = Number(offeredGifts.length > 0);
    const startedAt = performance.now();
    const duration = 420;
    let animationFrame = 0;

    const updateAmount = (now: number) => {
      const progress = Math.min((now - startedAt) / duration, 1);
      const easedProgress = 1 - Math.pow(1 - progress, 3);
      const next = {
        amount: start.amount + (receivedAmount - start.amount) * easedProgress,
        offered: start.offered + (offeredAmount - start.offered) * easedProgress,
        activation: start.activation + (targetActivation - start.activation) * easedProgress,
        offerActivation: start.offerActivation + (targetOfferActivation - start.offerActivation) * easedProgress,
      };
      animationValue.current = next;
      setExchangeAnimation(next);
      if (progress < 1) animationFrame = requestAnimationFrame(updateAmount);
    };

    animationFrame = requestAnimationFrame(updateAmount);
    return () => cancelAnimationFrame(animationFrame);
  }, [receivedAmount, offeredAmount, hasSelectedGifts, offeredGifts.length]);

  const exchangeIsAnimating = hasSelectedGifts || exchangeAnimation.activation > 0;
  const displayedShortage = Math.max(displayedReceivedAmount - exchangeAnimation.offered, 0);

  return (
    <div className="exchange-page">
      <PageHeader balance={balance} onNavigateProfile={onNavigateProfile} onTopUp={onTopUp} />

      <main className="exchange-content">
        <section className="exchange-summary" data-active={exchangeIsAnimating} data-underfunded={offeredAmount < receivedAmount} aria-label="Сумма обмена">
          <img className="exchange-summary__subtract" src={subtractObmenIcon} alt="" aria-hidden="true" />
          <span className="exchange-summary__reflection" style={{ opacity: exchangeAnimation.activation }} aria-hidden="true" />
          <div className="exchange-summary__offer">
            <span className="exchange-summary__label">Предлагаете</span>
            <strong className="exchange-summary__value exchange-summary__value--offer">
              <span className="exchange-summary__offer-stage">
                <span className="exchange-summary__offer-state exchange-summary__offer-state--amount" style={{ opacity: exchangeAnimation.offerActivation }}>
                  <img src={tonIcon} alt="" />
                  <span>{formatAmount(exchangeAnimation.offered)}</span>
                </span>
                <span className="exchange-summary__offer-state exchange-summary__offer-state--minimum" style={{ opacity: 1 - exchangeAnimation.offerActivation }}>
                  <img src={tonIcon} alt="" />
                  <span className="exchange-summary__offer-text"><span>0.00</span><span>мин. 10</span></span>
                  <img className="exchange-summary__muted-mark" src={tonIcon} alt="" />
                </span>
              </span>
            </strong>
          </div>
          <div className="exchange-summary__total">
            <span className="exchange-summary__label">Получаете</span>
            <strong className="exchange-summary__value exchange-summary__value--total">
              <img src={tonIcon} alt="" />
              <span>{selectedGifts.length > 0 || displayedReceivedAmount > 0 ? formatAmount(displayedReceivedAmount) : '0.00'}</span>
            </strong>
          </div>
          <button
            className="exchange-summary__active"
            type="button"
            aria-label="Открыть обмен"
            disabled={!hasSelectedGifts}
            onClick={() => setExchangeOpen(true)}
          >
            <span className="exchange-summary__fill" style={{ opacity: exchangeAnimation.activation }} aria-hidden="true" />
            <img src={giftIcon} style={{ opacity: 1 - exchangeAnimation.activation }} alt="" />
            <img src={activeGiftIcon} style={{ opacity: exchangeAnimation.activation }} alt="" />
            {hasSelectedGifts && <span className="exchange-summary__count">{offeredGifts.length + selectedGifts.length}</span>}
          </button>
        </section>
        <section className="exchange-catalog" id="catalog" aria-label="Каталог подарков">
          <p className="demo-inventory-caption">Тестовые подарки</p>
          <div className="exchange-toolbar">
            <label className="exchange-search"><img src={searchIcon} alt="" /><input aria-label="Поиск подарков" placeholder="Поиск" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /></label>
            <button className="exchange-icon-button" type="button" aria-label="Фильтры" onClick={() => setFiltersOpen(true)}><img src={filterCount > 0 ? filterActiveIcon : filterIcon} alt="" />{filterCount > 0 && <span className="exchange-icon-button__count">{filterCount}</span>}</button>
            <button className="exchange-icon-button" type="button" aria-label="Сортировка" onClick={() => setSortOpen(true)}><img src={sortOptions.length > 0 ? sorterActiveIcon : filterSortIcon} alt="" />{sortOptions.length > 0 && <span className="exchange-icon-button__count">{sortOptions.length}</span>}</button>
          </div>
          {(filterCount > 0 || sortOptions.length > 0) && <div className="exchange-clear-actions">
            {filterCount > 0 && <button type="button" onClick={clearFilters}>Очистить фильтр</button>}
            {sortOptions.length > 0 && <button className="exchange-clear-actions__sort" type="button" onClick={() => setSortOptions([])}>Очистить сортировку</button>}
          </div>}
          {loading ? <p className="exchange-catalog__status" role="status">Загрузка подарков…</p> : error ? (
            <div className="exchange-catalog__status" role="alert">
              <p>Не удалось загрузить подарки</p>
              <button type="button" onClick={() => void reload().catch(() => {})}>Повторить</button>
            </div>
          ) : activeSection === 'inventory' && inventoryGifts.length === 0 ? (
            <div className="exchange-empty exchange-empty--inventory">
              <strong>В вашем инвентаре пусто!</strong>
              <p>Отправьте подарок нам что бы это исправить!</p>
              <span className="exchange-empty__action">GiftRelayer</span>
            </div>
          ) : visibleGifts.length === 0 ? (
            <div className="exchange-empty exchange-empty--results">
              <strong>По вашему запросу ничего не найдено</strong>
              <button type="button" onClick={() => { clearFilters(); setSearchQuery(''); }}>Сбросить</button>
            </div>
          ) : <div className="gift-grid">
            {visibleGifts.map((gift) => (
              <article className="gift-card" key={gift.id}>
                <button className="gift-card__details" type="button" aria-label={`Открыть ${gift.name}`} onClick={() => {
                  setGiftDetails({ gift, source: activeSection });
                  setGiftDetailsOpen(true);
                }} />
                <div className="gift-card__visual">
                  <GiftArtwork gift={gift} />
                  <div className="gift-card__meta">
                    <div><strong>{gift.name}</strong><span>{gift.modelName ?? 'Модель'}&nbsp;&nbsp;{gift.model}</span></div>
                  </div>
                    <button className="gift-card__select" type="button" aria-label={`Выбрать ${gift.name}`} aria-pressed={selectedGiftIds.includes(gift.id)} onClick={() => toggleGift(gift.id)}>
                      <img src={selectedGiftIds.includes(gift.id) ? giftAddonIcon : giftIcon} alt="" />
                      <span className="gift-card__status"><img src={selectedGiftIds.includes(gift.id) ? selectedGiftIcon : plusIcon} alt="" /></span>
                    </button>
                </div>
                <div className="gift-card__price"><img src={tonIcon} alt="" />{gift.price}</div>
              </article>
            ))}
          </div>}
        </section>
      </main>

      <ShortageNotice
        className="exchange-shortage"
        label="Добавьте ещё:"
        amount={displayedShortage}
        visible={displayedShortage > 0.0005}
      />

      <div className="exchange-section-switcher" data-active={activeSection} role="tablist" aria-label="Раздел каталога">
        <span className="exchange-section-switcher__indicator" aria-hidden="true" />
        <button type="button" role="tab" aria-selected={activeSection === 'inventory'} onClick={() => setActiveSection('inventory')}>Инвентарь</button>
        <button type="button" role="tab" aria-selected={activeSection === 'exchange'} onClick={() => setActiveSection('exchange')}>Обмен</button>
      </div>
      <FilterModal open={filtersOpen} onClose={() => setFiltersOpen(false)} onApply={applyFilters} resetVersion={filterResetVersion} />
      <SortModal open={sortOpen} value={sortOptions} onApply={setSortOptions} onClose={() => setSortOpen(false)} />
      <ExchangeModal open={exchangeOpen} gifts={selectedGifts} offeredGifts={offeredGifts} offeredAmount={exchangeAnimation.offered} receivedAmount={displayedReceivedAmount} onRemove={(id, side) => (side === 'offer' ? setOfferedIds : setReceivedIds)((current) => current.filter((giftId) => giftId !== id))} onClear={(side) => (side === 'offer' ? setOfferedIds : setReceivedIds)([])} onSuccess={async () => { await exchange(offeredGifts.map((gift) => gift.id), selectedGifts.map((gift) => gift.id)); setOfferedIds([]); setReceivedIds([]); }} onClose={() => setExchangeOpen(false)} />
      <GiftDetailsModal gift={giftDetails?.gift ?? null} source={giftDetails?.source ?? 'exchange'} open={giftDetailsOpen} selected={giftDetails ? (giftDetails.source === 'inventory' ? offeredIds : receivedIds).includes(giftDetails.gift.id) : false} onClose={() => setGiftDetailsOpen(false)} onSelect={() => {
        if (!giftDetails) return;
        toggleGift(giftDetails.gift.id, giftDetails.source);
        setGiftDetailsOpen(false);
      }} />
    </div>
  );
}

export default ExchangePage;
