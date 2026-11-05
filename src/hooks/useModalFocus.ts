import { useEffect, type RefObject } from 'react';
import '../styles/modal-focus.css';

const panels: HTMLElement[] = [];

export function useModalFocus(ref: RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    const panel = ref.current;
    if (!active || !panel) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const nestedNativeDialog = () => Boolean(document.querySelector('dialog[open]'));
    panels.push(panel);
    const isTop = () => panels.at(-1) === panel && !nestedNativeDialog();
    panel.focus({ preventScroll: true });
    const keydown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !isTop()) return;
      const controls = [...panel.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])')]
        .filter(node => !node.closest('[inert], [hidden]') && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');
      const first = controls[0];
      const last = controls.at(-1);
      const current = document.activeElement;
      if (!first || !last) { event.preventDefault(); panel.focus({ preventScroll: true }); return; }
      if (current === panel || !panel.contains(current)) {
        event.preventDefault(); (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && current === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault(); first.focus();
      }
    };
    const focusin = (event: FocusEvent) => {
      if (isTop() && event.target instanceof Node && !panel.contains(event.target)) panel.focus({ preventScroll: true });
    };
    document.addEventListener('keydown', keydown);
    document.addEventListener('focusin', focusin);
    return () => {
      document.removeEventListener('keydown', keydown);
      document.removeEventListener('focusin', focusin);
      const index = panels.lastIndexOf(panel);
      if (index >= 0) panels.splice(index, 1);
      if (previous?.isConnected && !previous.closest('[inert], [hidden]')) previous.focus({ preventScroll: true });
    };
  }, [active, ref]);
}
