import type { CSSProperties } from 'react';
import './AmountDigits.css';

export default function AmountDigits({ text }: { text: string }) {
  return <span className="amount-digits" style={{ '--amount-digits': text.length } as CSSProperties}>{text}</span>;
}
