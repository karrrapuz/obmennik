import type { Gift } from '../../../pages/ExchangePage/data/gifts';
import { useEffect, useRef, useState } from 'react';
import type { AnimationItem } from 'lottie-web';
import placeholder from '../../../pages/ExchangePage/assets/gift.svg';
import { getGiftPresentation } from '../../../services/giftPresentation';
import { getGiftMedia } from '../../../services/giftMedia';
import { claimGiftPlayback, loadGiftAnimation, loadGiftPlayer } from '../../../services/giftAnimation';
import './GiftArtwork.css';
export default function GiftArtwork({ gift, playKey = 0 }: { gift: Gift; playKey?: number }) {
  const { backdrop, symbol } = getGiftPresentation(gift);
  const media = getGiftMedia(gift);
  const host = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [failedPoster, setFailedPoster] = useState('');
  useEffect(() => {
    setPlaying(false);
    const node = host.current;
    if (!playKey || !media || !node || document.hidden) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (motion.matches) return;
    const bounds = node.getBoundingClientRect();
    if (bounds.height === 0 || bounds.bottom <= 0 || bounds.top >= window.innerHeight) return;
    const controller = new AbortController();
    let item: AnimationItem | undefined;
    let alive = true;
    let release = () => {};
    let timeout: number | undefined;
    let observer: IntersectionObserver | undefined;
    const visibility = () => { if (document.hidden) stop(); };
    const motionChange = () => { if (motion.matches) stop(); };
    const stop = () => {
      controller.abort();
      item?.destroy(); item = undefined;
      window.clearTimeout(timeout); observer?.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      motion.removeEventListener('change', motionChange);
      release();
      if (alive) setPlaying(false);
    };
    release = claimGiftPlayback(stop);
    timeout = window.setTimeout(stop, 15000);
    document.addEventListener('visibilitychange', visibility);
    motion.addEventListener('change', motionChange);
    observer = new IntersectionObserver(entries => { if (!entries[0]?.isIntersecting) stop(); });
    observer.observe(node);
    Promise.all([loadGiftPlayer(), loadGiftAnimation(media.animation, controller.signal)]).then(([module, data]) => {
      if (!alive || controller.signal.aborted) return;
      item = module.default.loadAnimation({ container: node, renderer: 'svg', loop: false, autoplay: false, animationData: data });
      const start = () => {
        if (!alive || controller.signal.aborted) return;
        setPlaying(true); item?.goToAndPlay(0, true);
      };
      item.addEventListener('complete', stop);
      item.addEventListener('data_failed', stop);
      if (item.isLoaded) start(); else item.addEventListener('DOMLoaded', start);
    }).catch(stop);
    return () => {
      alive = false; stop(); window.clearTimeout(timeout);
      observer?.disconnect(); document.removeEventListener('visibilitychange', visibility);
      motion.removeEventListener('change', motionChange);
    };
  }, [media, playKey]);
  const poster = failedPoster === media?.poster ? gift.image : media?.poster ?? gift.image;
  return <div className="catalog-artwork" style={{ background: backdrop ? `radial-gradient(ellipse at center, ${backdrop.centerColor}, ${backdrop.edgeColor})` : '#131313' }}>
    {symbol?.image && <div className="catalog-artwork__pattern" style={{ backgroundColor: backdrop?.patternColor ?? '#fff', maskImage: `url("${symbol.image}")` }} />}
    <img src={poster || placeholder} alt={gift.name} loading="lazy" decoding="async" data-vector={Boolean(media && failedPoster !== media.poster)} style={{ visibility: playing ? 'hidden' : undefined }} onError={(event) => { if (media && failedPoster !== media.poster) setFailedPoster(media.poster); else if (!event.currentTarget.src.endsWith(placeholder)) event.currentTarget.src = placeholder; }} />
    {playKey > 0 && media && <div className="catalog-artwork__animation" ref={host} data-playing={playing} aria-hidden="true" />}
  </div>;
}
