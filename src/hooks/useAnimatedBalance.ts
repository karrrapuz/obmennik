import { useEffect, useRef, useState } from 'react';

export function useAnimatedBalance(value: number) {
  const [displayed, setDisplayed] = useState(value);
  const current = useRef(value);
  useEffect(() => {
    const from = current.current;
    const started = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min((now - started) / 500, 1);
      current.current = from + (value - from) * (1 - (1 - progress) ** 3);
      setDisplayed(current.current);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return displayed;
}
