import type { CSSProperties } from 'react';
import exchange from '../../../pages/ExchangePage/assets/footer_obmen.svg?raw';
import profile from '../../../pages/ExchangePage/assets/footer_profile.svg?raw';
import deposit from '../../../pages/ExchangePage/assets/footer_zalog.svg?raw';
import './PageFooter.css';

export type PageSection = 'deposit' | 'exchange' | 'profile';

const items = [
  { id: 'deposit', label: 'Залог', icon: deposit },
  { id: 'exchange', label: 'Обмен', icon: exchange },
  { id: 'profile', label: 'Профиль', icon: profile },
] as const;

// Прозрачность задаётся состоянием кнопки, а не исходным SVG.
const masks = items.map((item) => `url("data:image/svg+xml,${encodeURIComponent(item.icon.replaceAll('fill-opacity="0.2"', 'fill-opacity="1"'))}")`);

export default function PageFooter({ active, onNavigate }: {
  active: PageSection;
  onNavigate: (page: PageSection) => void;
}) {
  return <nav className="page-footer" aria-label="Разделы">
    {items.map((item, index) => <button
      key={item.id}
      className={`page-footer__item page-footer__item--${item.id}`}
      type="button"
      aria-current={active === item.id ? 'page' : undefined}
      onClick={() => onNavigate(item.id)}
    >
      <i className="page-footer__light" aria-hidden="true" />
      <i className="page-footer__icon" style={{ '--icon': masks[index] } as CSSProperties} aria-hidden="true" />
      <span>{item.label}</span>
    </button>)}
  </nav>;
}
