import { useEffect, useState } from 'react';
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
import { gifts, getFilterOptions } from '../../data/gifts';

type FilterModalProps = {
  open: boolean;
  onClose: () => void;
  onApply: (filters: AppliedFilters) => void;
  resetVersion: number;
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

const filterOptions = getFilterOptions(gifts);

function FilterModal({ open, onClose, onApply, resetVersion }: FilterModalProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string[]>>({});
  const [queries, setQueries] = useState<Record<string, string>>({});
  const [fromPrice, setFromPrice] = useState('');
  const [toPrice, setToPrice] = useState('');
  const selectedCount = Object.values(selected).reduce((total, values) => total + values.length, 0)
    + Number(Boolean(fromPrice || toPrice));

  const resetFilters = () => {
    setSelected({});
    setQueries({});
    setFromPrice('');
    setToPrice('');
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
      return { ...current, [id]: values.includes(name) ? values.filter((value) => value !== name) : [...values, name] };
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
                  <div className="filter-modal__details-inner">
                    {row.id === 'price' ? (
                      <div className="filter-modal__price-range">
                        <label>От<input type="number" min="0" inputMode="decimal" placeholder="0.00" value={fromPrice} onChange={(event) => setFromPrice(event.target.value)} /></label>
                        <label>До<input type="number" min="0" inputMode="decimal" placeholder="0.00" value={toPrice} onChange={(event) => setToPrice(event.target.value)} /></label>
                      </div>
                    ) : (
                      <>
                        <label className="filter-modal__search"><img src={searchIcon} alt="" aria-hidden="true" /><input type="search" placeholder="Поиск" value={queries[row.id] ?? ''} onChange={(event) => setQueries((current) => ({ ...current, [row.id]: event.target.value }))} /></label>
                        <div className="filter-modal__options">
                          {options.map((option) => {
                            const checked = selected[row.id]?.includes(option.name) ?? false;
                            return <button className="filter-modal__option" type="button" aria-pressed={checked} key={option.name} onClick={() => toggleOption(row.id, option.name)}>
                              <span className="filter-modal__option-check" aria-hidden="true"><span><img src={checked ? checkIcon : plusIcon} alt="" /></span></span>
                              <span className="filter-modal__option-image" aria-hidden="true" style={option.color ? { background: option.color } : undefined}>{option.image && <img src={option.image} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />}</span>
                              <span className="filter-modal__option-title"><span className="filter-modal__option-name">{option.name}</span>{option.rarity && <em>{option.rarity}</em>}</span>
                              {option.price && <span className="filter-modal__option-price">{option.price}<img src={tonModalIcon} alt="TON" /></span>}
                            </button>;
                          })}
                        </div>
                      </>
                    )}
                  </div>
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
