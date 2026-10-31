import { useLayoutEffect, useRef, useState, type TouchEvent } from 'react';
import ExchangePage from '../ExchangePage/ExchangePage';
import ProfilePage from '../ProfilePage/ProfilePage';
import DepositPage from '../DepositPage/DepositPage';
import PageFooter, { type PageSection } from '../../components/layout/PageFooter/PageFooter';
import { useWallet } from '../../wallet/WalletProvider';
import { displayTon } from '../../wallet/wallet';
import './HomePage.css';

const pageOrder: PageSection[] = ['deposit', 'exchange', 'profile'];
type PageSwipe = { x: number; y: number; startedAt: number; page: PageSection };

function blocksPageSwipe(target: EventTarget | null) {
  if (!(target instanceof Element)) return true;
  if (window.getSelection()?.toString()) return true;
  if (document.body.style.overflow === 'hidden' || document.querySelector('[aria-modal="true"]')) return true;
  if (target.closest('button, a, input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="slider"], [role="tablist"], [draggable="true"]')) return true;
  for (let element: Element | null = target; element; element = element.parentElement) {
    if (element.scrollWidth > element.clientWidth + 1 && /auto|scroll/.test(getComputedStyle(element).overflowX)) return true;
  }
  return false;
}

function HomePage() {
  const [activePage, setActivePage] = useState<PageSection>('exchange');
  const swipe = useRef<PageSwipe | null>(null);
  const pageView = useRef<HTMLDivElement>(null);
  const entryDirection = useRef(0);
  const leaving = useRef(false);
  const exits = useRef<Animation[]>([]);
  const navigationRun = useRef(0);
  useLayoutEffect(() => () => {
    navigationRun.current += 1;
    exits.current.forEach(animation => animation.cancel());
  }, []);
  useLayoutEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const content = pageView.current?.querySelectorAll<HTMLElement>(
      ':scope > .exchange-page > .exchange-content, :scope > .profile-page > :is(.profile-balance, .profile-actions, .profile-content), :scope > .deposit-page > :is(.pledge-banner, .pledge-tabs, .pledge-catalog)',
    );
    const animations = Array.from(content ?? [], (element, index) => element.animate([
      { opacity: 0, transform: `translate(${entryDirection.current * 18}px, 12px)` },
      { opacity: 1, transform: 'translate(0, 0)' },
    ], { duration: 440, delay: index * 35, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'backwards' }));
    return () => animations.forEach(animation => animation.cancel());
  }, [activePage]);
  const { wallet } = useWallet();
  const balance = displayTon(wallet.balance_nano);
  const [topUpRequest, setTopUpRequest] = useState(0);
  const openTopUp = () => setTopUpRequest((value) => value + 1);
  const navigate = (page: PageSection) => {
    if (page === activePage || leaving.current) return;
    const direction = Math.sign(pageOrder.indexOf(page) - pageOrder.indexOf(activePage));
    const finish = () => {
      entryDirection.current = direction;
      setActivePage(page);
      window.scrollTo(0, 0);
    };
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { finish(); return; }
    const elements = pageView.current?.querySelectorAll<HTMLElement>(
      ':scope > .exchange-page > .exchange-content, :scope > .profile-page > :is(.profile-balance, .profile-actions, .profile-content), :scope > .deposit-page > :is(.pledge-banner, .pledge-tabs, .pledge-catalog)',
    );
    leaving.current = true;
    const run = ++navigationRun.current;
    exits.current = Array.from(elements ?? [], element => element.animate([
      { opacity: 1, transform: 'translateX(0)' },
      { opacity: 0, transform: `translateX(${-direction * 8}px)` },
    ], { duration: 120, easing: 'ease-in', fill: 'forwards' }));
    void Promise.all(exits.current.map(animation => animation.finished)).then(() => {
      if (navigationRun.current !== run) return;
      exits.current.forEach(animation => animation.cancel());
      exits.current = [];
      leaving.current = false;
      finish();
    }).catch(() => { if (navigationRun.current === run) leaving.current = false; });
  };
  const cancelSwipe = () => { swipe.current = null; };
  const onTouchStart = (event: TouchEvent<HTMLDivElement>) => {
    cancelSwipe();
    const touch = event.touches[0];
    if (event.touches.length !== 1 || blocksPageSwipe(event.target)) return;
    if (touch.clientX < 32 || touch.clientX > document.documentElement.clientWidth - 32) return;
    swipe.current = { x: touch.clientX, y: touch.clientY, startedAt: event.timeStamp, page: activePage };
  };
  const onTouchMove = (event: TouchEvent<HTMLDivElement>) => {
    if (!swipe.current) return;
    if (event.touches.length !== 1 || Math.abs(event.touches[0].clientY - swipe.current.y) > 24) cancelSwipe();
  };
  const onTouchEnd = (event: TouchEvent<HTMLDivElement>) => {
    const start = swipe.current;
    cancelSwipe();
    if (!start || start.page !== activePage || event.changedTouches.length !== 1 || event.timeStamp - start.startedAt > 650 || blocksPageSwipe(event.target)) return;
    const touch = event.changedTouches[0];
    const distance = touch.clientX - start.x;
    if (Math.abs(distance) < 72 || Math.abs(distance) < Math.abs(touch.clientY - start.y) * 2.5) return;
    if (touch.clientX < 16 || touch.clientX > document.documentElement.clientWidth - 16) return;
    const nextPage = pageOrder[pageOrder.indexOf(activePage) + (distance < 0 ? 1 : -1)];
    if (nextPage) navigate(nextPage);
  };
  // Observe completed gestures only; native scrolling and Telegram edge gestures stay untouched.
  const swipeHandlers = { onTouchStart, onTouchMove, onTouchEnd, onTouchCancel: cancelSwipe };
  return <>
    <div ref={activePage === 'profile' ? pageView : undefined} className="home-page-view" {...swipeHandlers} hidden={activePage !== 'profile'} inert={activePage !== 'profile'} aria-hidden={activePage !== 'profile'}><ProfilePage balance={balance} topUpRequest={topUpRequest} /></div>
    {activePage === 'deposit' && <div ref={pageView} className="home-page-view" {...swipeHandlers}><DepositPage balance={balance} onTopUp={openTopUp} onNavigateProfile={() => navigate('profile')} /></div>}
    <div ref={activePage === 'exchange' ? pageView : undefined} className="home-page-view" {...swipeHandlers} hidden={activePage !== 'exchange'} inert={activePage !== 'exchange'} aria-hidden={activePage !== 'exchange'}><ExchangePage balance={balance} onTopUp={openTopUp} onNavigateProfile={() => navigate('profile')} /></div>
    <PageFooter active={activePage} onNavigate={navigate} />
  </>;
}

export default HomePage;
