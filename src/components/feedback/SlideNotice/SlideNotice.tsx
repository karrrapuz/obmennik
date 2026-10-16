import { cloneElement, useEffect, useRef, useState, type ReactElement } from 'react';
import './SlideNotice.css';

export default function SlideNotice({ show, children }: { show: boolean; children: ReactElement<any> }) {
  const [mounted, setMounted] = useState(show);
  const [visible, setVisible] = useState(false);
  const lastChild = useRef(children);
  if (show) lastChild.current = children;
  useEffect(() => {
    let first = 0;
    let second = 0;
    let timer = 0;
    if (show) {
      setMounted(true);
      first = requestAnimationFrame(() => { second = requestAnimationFrame(() => setVisible(true)); });
    } else {
      setVisible(false);
      timer = window.setTimeout(() => setMounted(false), 380);
    }
    return () => { cancelAnimationFrame(first); cancelAnimationFrame(second); clearTimeout(timer); };
  }, [show]);
  if (!mounted) return null;
  const child = show ? children : lastChild.current;
  return cloneElement(child, { className: `${child.props.className ?? ''} slide-notice`, 'data-shown': show && visible, inert: !show });
}
