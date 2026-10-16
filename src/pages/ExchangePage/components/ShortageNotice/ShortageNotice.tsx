import './ShortageNotice.css';

type ShortageNoticeProps = {
  amount: number;
  className?: string;
  label: string;
  visible: boolean;
  glass?: boolean;
};

function ShortageNotice({ amount, className = '', label, visible, glass = true }: ShortageNoticeProps) {
  return (
    <output
      className={`shortage-notice ${className}`}
      data-visible={visible}
      data-glass={glass}
      aria-hidden={!visible}
      aria-live="polite"
    >
      <span className="shortage-notice__content">
        <span>{label}</span>
        <span className="shortage-notice__amount">
          <span>{amount.toFixed(3)}</span>
          <span className="shortage-notice__ton" aria-hidden="true" />
        </span>
      </span>
    </output>
  );
}

export default ShortageNotice;
