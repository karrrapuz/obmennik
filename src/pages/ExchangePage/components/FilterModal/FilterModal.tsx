import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import priceIcon from './assets/sell.svg';
import collectionIcon from './assets/collection.svg';
import modelsIcon from './assets/models.svg';
import backdropsIcon from './assets/fons.svg';
import symbolsIcon from './assets/simvols.svg';
import chevronIcon from './assets/zasrit.svg';
import closeIcon from './assets/Union.svg';
import checkIcon from './assets/galochka.svg';
import plusIcon from './assets/plus.svg';
import tonModalIcon from './assets/ton_modal.svg';
import searchIcon from './assets/poisk_modal.svg';
import './FilterModal.css';
import type { Gift } from '../../data/gifts';
import { telegramFilterOptions, type TelegramManifest } from '../../../../services/telegramCatalog';

type FilterModalProps = {
  open: boolean;
  onClose: () => void;
  onApply: (filters: AppliedFilters) => void;
  resetVersion: number;
  catalog: Gift[];
  manifest: TelegramManifest | null;
};

export type AppliedFilters = {
  fromPrice: string;
  toPrice: string;
  selected: Record<string, string[]>;
};

const filterRows = [
  { id: 'price', label: 'Цена', icon: priceIcon },
  { id: 'collection', label: 'Коллекция', icon: collectionIcon },
  { id: 'models', label: 'Модели', icon: modelsIcon },
  { id: 'backdrops', label: 'Фоны', icon: backdropsIcon },
  { id: 'symbols', label: 'Символы', icon: symbolsIcon },
] as const;

function FilterModal({ open, onClose, onApply, resetVersion, catalog, manifest }: FilterModalProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [queries, setQueries] = useState<Record<string, string>>({});
  const [fromPrice, setFromPrice] = useState('');
  const [toPrice, setToPrice] = useState('');
  const [limits, setLimits] = useState<Record<string, number>>({});
  const filterOptions = useMemo(() => telegramFilterOptions(catalog, manifest, selected.collection ?? []), [catalog, manifest, selected.collection]);
  const selectedCount = Object.values(selected).reduce((total, values) => total + values.length, 0)
    + Number(Boolean(fromPrice || toPrice));

  const resetFilters = () => {
    setSelected({});
    setQueries({});
    setFromPrice('');
    setToPrice('');
    setLimits({});
  };

  useEffect(() => {
    if (resetVersion > 0) resetFilters();
  }, [resetVersion]);

  const applyFilters = () => {
    onApply({ fromPrice, toPrice, selected });
    onClose();
  };

  const toggleOption = (id: string, name: string) => {
    setSelected((current) => {
      const values = current[id] ?? [];
      const next = { ...current, [id]: values.includes(name) ? values.filter((value) => value !== name) : [...values, name] };
      return id === 'collection' ? { ...next, models: [], symbols: [], backdrops: [] } : next;
    });
  };

  useEffect(() => {
    if (open) {
      const frame = requestAnimationFrame(() => {
        setMounted(true);
        requestAnimationFrame(() => setVisible(true));
      });
      return () => cancelAnimationFrame(frame);
    }
    const frame = requestAnimationFrame(() => setVisible(false));
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!mounted) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [mounted, onClose]);

  if (!mounted) return null;

  return createPortal(
    <div
      className="filter-modal-layer"
      data-visible={visible}
      onTransitionEnd={(event) => {
        if (event.target === event.currentTarget && !open) setMounted(false);
      }}
    >
      <button className="filter-modal-scrim" type="button" aria-label="Закрыть фильтры" onClick={onClose} />
      <section className="filter-modal" role="dialog" aria-modal="true" aria-label="Фильтры">
        <div className="filter-modal__handle" aria-hidden="true" />
        <header className="filter-modal__header">
          <h2>Фильтры</h2>
          <button className="filter-modal__close" type="button" aria-label="Закрыть фильтры" onClick={onClose}><img src={closeIcon} alt="" /></button>
        </header>
        <div className="filter-modal__content">
          {filterRows.map((row) => {
            const isExpanded = expanded === row.id;
            const count = row.id === 'price' ? Number(Boolean(fromPrice || toPrice)) : (selected[row.id]?.length ?? 0);
            const options = (filterOptions[row.id] ?? []).filter((option) =>
              option.name.toLocaleLowerCase().includes((queries[row.id] ?? '').toLocaleLowerCase()),
            );
            return (
              <div className="filter-modal__section" data-expanded={isExpanded} key={row.id}>
                <button className="filter-modal__row" type="button" aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : row.id)}>
                  <span className="filter-modal__icon" aria-hidden="true">
                    <span className={row.id === 'price' ? 'filter-modal__ton' : 'filter-modal__symbol'}><img src={row.icon} alt="" /></span>
                  </span>
                  <span className="filter-modal__label">{row.label}</span>
                  {count > 0 && <span className="filter-modal__count"><img src={checkIcon} alt="" />{count}</span>}
                  <img className="filter-modal__chevron" src={chevronIcon} alt="" aria-hidden="true" />
                </button>
                <div className="filter-modal__details" inert={!isExpanded}>
                  <div className="filter-modal__details-inner">{isExpanded && <>
                    {row.id === 'price' ? (
                      <div className="filter-modal__price-range">
                        <label>От<input type="number" min="0" inputMode="decimal" placeholder="0.00" value={fromPrice} onChange={(event) => setFromPrice(event.target.value)} /></label>
                        <label>До<input type="number" min="0" inputMode="decimal" placeholder="0.00" value={toPrice} onChange={(event) => setToPrice(event.target.value)} /></label>
                      </div>
                    ) : (
                      <>
                        <label className="filter-modal__search"><img src={searchIcon} alt="" aria-hidden="true" /><input aria-label={`${row.label}: поиск`} type="search" placeholder="Поиск" value={queries[row.id] ?? ''} onChange={(event) => { setQueries((current) => ({ ...current, [row.id]: event.target.value })); setLimits(current => ({ ...current, [row.id]: 60 })); }} /></label>
                        <div className="filter-modal__options">
                          {options.slice(0, limits[row.id] ?? 60).map((option) => {
                            const value = option.value ?? option.name;
                            const checked = selected[row.id]?.includes(value) ?? false;
                            return <button className="filter-modal__option" data-described={Boolean(option.description)} type="button" aria-pressed={checked} key={value} onClick={() => toggleOption(row.id, value)}>
                              <span className="filter-modal__option-check" aria-hidden="true"><span><img src={checked ? checkIcon : plusIcon} alt="" /></span></span>
                              <span className="filter-modal__option-image" aria-hidden="true" style={option.color ? { background: option.color } : undefined}>{option.image && <img src={option.image} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />}</span>
                              <span className="filter-modal__option-title"><span className="filter-modal__option-name">{option.name}</span>{option.description && <small className="filter-modal__option-description">{option.description}</small>}{option.rarity && <em>{option.rarity}</em>}</span>
                              {option.price && <span className="filter-modal__option-price">{option.price}<img src={tonModalIcon} alt="TON" /></span>}
                            </button>;
                          })}
                          {options.length > (limits[row.id] ?? 60) && <button type="button" className="catalog-load-more" onClick={() => setLimits(current => ({ ...current, [row.id]: (current[row.id] ?? 60) + 60 }))}>Показать ещё ({options.length - (limits[row.id] ?? 60)})</button>}
                          {!options.length && <p role="status">Ничего не найдено</p>}
                        </div>
                      </>
                    )}
                  </>}</div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="filter-modal__actions" data-active={selectedCount > 0}>
          <button type="button" onClick={resetFilters}>Сбросить</button>
          <button type="button" onClick={applyFilters}>Поиск</button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

export default FilterModal;
