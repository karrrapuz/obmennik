import { useEffect, useMemo, useRef, useState } from 'react';
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
  const panel = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
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
      if (id !== 'collection') return next;
      const available = telegramFilterOptions(catalog, manifest, next.collection ?? []);
      for (const key of ['models', 'symbols', 'backdrops']) next[key] = (current[key] ?? []).filter(value => available[key].some(option => (option.value ?? option.name) === value || option.name === value));
      return next;
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

  useEffect(() => {
    if (!mounted) return;
    const viewport = window.visualViewport;
    const updateViewport = () => {
      const height = viewport?.height ?? window.innerHeight;
      const inset = Math.max(0, window.innerHeight - height - (viewport?.offsetTop ?? 0));
      panel.current?.style.setProperty('--filter-viewport-height', `${height}px`);
      panel.current?.style.setProperty('--filter-keyboard-inset', `${inset}px`);
    };
    updateViewport();
    viewport?.addEventListener('resize', updateViewport);
    viewport?.addEventListener('scroll', updateViewport);
    window.addEventListener('resize', updateViewport);
    return () => {
      viewport?.removeEventListener('resize', updateViewport);
      viewport?.removeEventListener('scroll', updateViewport);
      window.removeEventListener('resize', updateViewport);
    };
  }, [mounted]);

  useEffect(() => {
    if (!visible || !expanded) return;
    const area = content.current;
    const section = area?.querySelector<HTMLElement>('[data-expanded="true"]');
    if (!area || !section) return;
    const start = area.scrollTop;
    const startedAt = performance.now();
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 220 : 420;
    let frame = 0;
    let stopped = false;
    const stop = () => { stopped = true; cancelAnimationFrame(frame); };
    const reveal = (now: number) => {
      if (stopped) return;
      const progress = duration ? Math.min((now - startedAt) / duration, 1) : 1;
      const eased = 1 - Math.pow(1 - progress, 3);
      // Follow the changing accordion geometry in the same animation, without a delayed second scroll.
      const target = section.getBoundingClientRect().top - area.getBoundingClientRect().top + area.scrollTop;
      area.scrollTop = start + (target - start) * eased;
      if (progress < 1) frame = requestAnimationFrame(reveal);
    };
    area.addEventListener('touchstart', stop, { passive: true });
    area.addEventListener('wheel', stop, { passive: true });
    area.addEventListener('pointerdown', stop, { passive: true });
    frame = requestAnimationFrame(reveal);
    return () => {
      stop();
      area.removeEventListener('touchstart', stop);
      area.removeEventListener('wheel', stop);
      area.removeEventListener('pointerdown', stop);
    };
  }, [expanded, visible]);

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
      <section ref={panel} className="filter-modal" role="dialog" aria-modal="true" aria-label="Фильтры">
        <div className="filter-modal__handle" aria-hidden="true" />
        <header className="filter-modal__header">
          <h2>Фильтры</h2>
          <button className="filter-modal__close" type="button" aria-label="Закрыть фильтры" onClick={onClose}><img src={closeIcon} alt="" /></button>
        </header>
        <div ref={content} className="filter-modal__content">
          {filterRows.map((row) => {
            const isExpanded = expanded === row.id;
            const count = row.id === 'price' ? Number(Boolean(fromPrice || toPrice)) : (selected[row.id]?.length ?? 0);
            const options = (filterOptions[row.id] ?? []).filter((option) =>
              `${option.name} ${option.description ?? ''}`.toLocaleLowerCase().includes((queries[row.id] ?? '').toLocaleLowerCase()),
            );
            const shown = row.id === 'collection' || row.id === 'backdrops' ? options.length : limits[row.id] ?? 60;
            return (
              <div className="filter-modal__section" data-expanded={isExpanded} key={row.id}>
                <button className="filter-modal__row" type="button" aria-label={row.label} aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : row.id)}>
                  <span className="filter-modal__icon" aria-hidden="true">
                    <span className={row.id === 'price' ? 'filter-modal__ton' : 'filter-modal__symbol'}><img src={row.icon} alt="" /></span>
                  </span>
                  <span className="filter-modal__heading"><span className="filter-modal__label">{row.label}</span>
                    {row.id !== 'price' && <span className="filter-modal__available-count" aria-hidden="true">{filterOptions[row.id]?.length ?? 0}</span>}
                  </span>
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
                        <div className="filter-modal__search"><img src={searchIcon} alt="" aria-hidden="true" /><input aria-label={`${row.label}: поиск`} type="search" placeholder="Поиск" value={queries[row.id] ?? ''} onChange={(event) => { setQueries((current) => ({ ...current, [row.id]: event.target.value })); setLimits(current => ({ ...current, [row.id]: 60 })); }} />
                          {Boolean(queries[row.id]) && <button className="filter-modal__search-clear" type="button" aria-label={`${row.label}: очистить поиск`} title="Очистить поиск" onMouseDown={event => event.preventDefault()} onClick={event => {
                            event.preventDefault();
                            setQueries(current => ({ ...current, [row.id]: '' }));
                            setLimits(current => ({ ...current, [row.id]: 60 }));
                            event.currentTarget.parentElement?.querySelector('input')?.focus();
                          }}><span aria-hidden="true" /></button>}
                        </div>
                        <div className="filter-modal__options" onScroll={event => {
                          const list = event.currentTarget;
                          if (shown < options.length && list.scrollHeight - list.scrollTop - list.clientHeight < 100) setLimits(current => ({ ...current, [row.id]: Math.min(shown + 60, options.length) }));
                        }}>
                          {options.slice(0, shown).map((option) => {
                            const value = option.value ?? option.name;
                            const checked = selected[row.id]?.includes(value) ?? false;
                            return <button className="filter-modal__option" data-described={Boolean(option.description)} type="button" aria-pressed={checked} key={value} onClick={() => toggleOption(row.id, value)}>
                              <span className="filter-modal__option-check" aria-hidden="true"><span><img src={checked ? checkIcon : plusIcon} alt="" /></span></span>
                              <span className="filter-modal__option-image" aria-hidden="true" style={option.color ? { background: option.color } : undefined}>{option.image && <img src={option.image} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />}</span>
                              <span className="filter-modal__option-title"><span className="filter-modal__option-name">{option.name}</span>{option.description && <small className="filter-modal__option-description">{option.description}</small>}{option.rarity && <em>{option.rarity}</em>}</span>
                              {option.price && <span className="filter-modal__option-price">{option.price}<img src={tonModalIcon} alt="TON" /></span>}
                            </button>;
                          })}
                          {options.length > shown && <button type="button" className="catalog-load-more" onClick={() => setLimits(current => ({ ...current, [row.id]: shown + 60 }))}>Показать ещё ({options.length - shown})</button>}
                          {!options.length && <p className="filter-modal__empty" role="status">Пусто</p>}
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
