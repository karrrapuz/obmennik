import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import checkIcon from '../FilterModal/assets/galochka.svg';
import closeIcon from '../FilterModal/assets/Union.svg';
import './SortModal.css';

export const sortOptions = [
  { id: 'newest', label: 'Сначала новые' },
  { id: 'price-asc', label: 'Цена: По возрастанию' },
  { id: 'price-desc', label: 'Цена: По убыванию' },
  { id: 'rarity-asc', label: 'Редкость модели: По возрастанию' },
  { id: 'rarity-desc', label: 'Редкость модели: По убыванию' },
] as const;

export type SortOption = (typeof sortOptions)[number]['id'];

const sortGroup = (option: SortOption) => option.split('-')[0];

type SortModalProps = {
  open: boolean;
  value: SortOption[];
  onApply: (value: SortOption[]) => void;
  onClose: () => void;
};

function SortModal({ open, value, onApply, onClose }: SortModalProps) {
  const [mounted, setMounted] = useState(open);
  const [visible, setVisible] = useState(false);
  const [draft, setDraft] = useState<SortOption[]>(value);

  const toggleOption = (option: SortOption) => {
    setDraft((current) => current.includes(option)
      ? current.filter((value) => value !== option)
      : [...current.filter((value) => sortGroup(value) !== sortGroup(option)), option]);
  };

  useEffect(() => {
    if (open) {
      setMounted(true);
      setDraft([...value]);
      const frame = requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
      return () => cancelAnimationFrame(frame);
    }
    setVisible(false);
  }, [open, value]);

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
    <div className="sort-modal-layer" data-visible={visible} onTransitionEnd={(event) => {
      if (event.target === event.currentTarget && !open) setMounted(false);
    }}>
      <button className="sort-modal-scrim" type="button" aria-label="Закрыть сортировку" onClick={onClose} />
      <section className="sort-modal" role="dialog" aria-modal="true" aria-label="Сортировка">
        <div className="sort-modal__handle" aria-hidden="true" />
        <header className="sort-modal__header">
          <h2>Сортировка</h2>
          <button className="sort-modal__close" type="button" aria-label="Закрыть сортировку" onClick={onClose}><img src={closeIcon} alt="" /></button>
        </header>
        <div className="sort-modal__options">
          {sortOptions.map((option) => <button className="sort-modal__option" type="button" aria-pressed={draft.includes(option.id)} key={option.id} onClick={() => toggleOption(option.id)}>
            <span className="sort-modal__icon"><span>{draft.includes(option.id) && <img src={checkIcon} alt="" />}</span></span>
            <span>{option.label}</span>
          </button>)}
        </div>
        <div className="sort-modal__actions">
          <button type="button" onClick={() => { setDraft([]); onApply([]); onClose(); }}>Сбросить</button>
          <button type="button" data-active={draft.length > 0} onClick={() => { onApply(draft); onClose(); }} disabled={draft.length === 0}>Поиск</button>
        </div>
      </section>
    </div>,
    document.body,
  );
}

export default SortModal;
