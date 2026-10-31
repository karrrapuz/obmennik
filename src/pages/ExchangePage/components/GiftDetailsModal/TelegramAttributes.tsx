import { useState } from 'react';
import type { TelegramCollection } from '../../../../services/telegramCatalog';

const rows = [{ id: 'models', label: 'Модели' }, { id: 'symbols', label: 'Символы' }, { id: 'backdrops', label: 'Фоны' }] as const;
export default function TelegramAttributes({ collection, selected, onChange }: { collection: TelegramCollection; selected: Record<string, string[]>; onChange: (value: Record<string, string[]>) => void }) {
  const [active, setActive] = useState<string | null>(null);
  const [queries, setQueries] = useState<Record<string, string>>({});
  const [limits, setLimits] = useState<Record<string, number>>({});
  return <section className="telegram-attributes" aria-label="Атрибуты коллекции">
    {rows.map(row => {
      const items = collection.attributes[row.id];
      const options = active === row.id ? items.filter(item => item.name.toLocaleLowerCase().includes((queries[row.id] ?? '').toLocaleLowerCase())) : [];
      const limit = limits[row.id] ?? 40;
      return <div key={row.id}>
        <button className="telegram-attributes__heading" type="button" aria-expanded={active === row.id} onClick={() => setActive(active === row.id ? null : row.id)}>{row.label} <span>{items.length}</span></button>
        {active === row.id && <div className="telegram-attributes__options">
          <input type="search" aria-label={`${row.label}: поиск вариантов`} placeholder="Поиск" value={queries[row.id] ?? ''} onChange={event => { setQueries(current => ({ ...current, [row.id]: event.target.value })); setLimits(current => ({ ...current, [row.id]: 40 })); }} />
          {options.slice(0, limit).map(item => <button type="button" key={item.id} aria-pressed={selected[row.id]?.includes(item.name) ?? false} onClick={() => onChange({ ...selected, [row.id]: selected[row.id]?.includes(item.name) ? [] : [item.name] })}>
            {'image' in item ? item.image && <img src={item.image} alt="" loading="lazy" /> : <span className="telegram-attributes__swatch" style={{ background: item.centerColor }} />}
            <span>{item.name}<small>{item.rarity}{'crafted' in item && item.crafted ? ' · Crafted' : ''}</small></span>
          </button>)}
          {!options.length && <p>Ничего не найдено</p>}
          {options.length > limit && <button className="catalog-load-more" type="button" onClick={() => setLimits(current => ({ ...current, [row.id]: limit + 40 }))}>Показать ещё ({options.length - limit})</button>}
        </div>}
      </div>;
    })}
  </section>;
}
