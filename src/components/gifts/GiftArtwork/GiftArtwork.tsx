import type { Gift } from '../../../pages/ExchangePage/data/gifts';
import { useEffect, useRef, useState } from 'react';
import type { AnimationItem } from 'lottie-web';
import placeholder from '../../../pages/ExchangePage/assets/gift.svg';
import { getGiftPresentation } from '../../../services/giftPresentation';
import { getGiftMedia } from '../../../services/giftMedia';
import { claimGiftPlayback, loadGiftAnimation, loadGiftPlayer } from '../../../services/giftAnimation';
import './GiftArtwork.css';
export type GiftArtworkProps = { gift: Gift; autoPlay?: boolean; playKey?: number };

export default function GiftArtwork({ gift, autoPlay = false, playKey = 0 }: GiftArtworkProps) {
  const { backdrop, symbol } = getGiftPresentation(gift);
  const media = getGiftMedia(gift);
  const host = useRef<HTMLDivElement>(null);
  const artwork = useRef<HTMLDivElement>(null);
  const [hoverKey, setHoverKey] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [failedPoster, setFailedPoster] = useState('');
  useEffect(() => {
    const parent = artwork.current?.closest<HTMLElement>('.gift-card, .profile-gifts__card, .pledge-card, .exchange-modal__gift, .gift-details__preview, .pledge-preview') ?? artwork.current?.parentElement;
    if (!parent || !media) return;
    const enter = (event: PointerEvent) => {
      if (event.pointerType !== 'touch' && window.matchMedia('(hover: hover) and (pointer: fine)').matches
          && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) setHoverKey(key => key + 1);
    };
    parent.addEventListener('pointerenter', enter);
    return () => parent.removeEventListener('pointerenter', enter);
  }, [media]);
  useEffect(() => {
    setPlaying(false);
    const node = host.current;
    if ((!playKey && !autoPlay && !hoverKey) || !media || !node || document.hidden) return;
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (motion.matches && !playKey && !autoPlay) return;
    const bounds = node.getBoundingClientRect();
    let intersecting = bounds.height > 0 && bounds.bottom > 0 && bounds.top < window.innerHeight;
    const controller = new AbortController();
    let item: AnimationItem | undefined;
    let alive = true;
    let release = () => {};
    let timeout: number | undefined;
    let observer: IntersectionObserver | undefined;
    let started = false;
    let loadStarted = false;
    let start = () => {};
    const visibility = () => { if (document.hidden) stop(); };
    const motionChange = () => { if (motion.matches && !playKey && !autoPlay) stop(); };
    const stop = () => {
      controller.abort();
      item?.destroy(); item = undefined;
      window.clearTimeout(timeout); observer?.disconnect();
      document.removeEventListener('visibilitychange', visibility);
      motion.removeEventListener('change', motionChange);
      release();
      if (alive) setPlaying(false);
    };
    document.addEventListener('visibilitychange', visibility);
    motion.addEventListener('change', motionChange);
    observer = new IntersectionObserver(entries => {
      intersecting = Boolean(entries[0]?.isIntersecting);
      if (intersecting) { load(); start(); } else if (loadStarted) stop();
    });
    observer.observe(node);
    const load = () => {
      if (!intersecting || loadStarted || controller.signal.aborted) return;
      loadStarted = true;
      release = claimGiftPlayback(stop);
      timeout = window.setTimeout(stop, 15000);
      Promise.all([loadGiftPlayer(), loadGiftAnimation(media.animation, controller.signal)]).then(([module, data]) => {
      if (!alive || controller.signal.aborted) return;
      item = module.default.loadAnimation({ container: node, renderer: 'svg', loop: false, autoplay: false, animationData: data });
      start = () => {
        if (!alive || controller.signal.aborted || !intersecting || started || !item?.isLoaded) return;
        started = true;
        setPlaying(true); item?.goToAndPlay(0, true);
      };
      item.addEventListener('complete', () => {
        // Keep the actual final frame, not the unrelated static poster pose.
        window.clearTimeout(timeout);
        release();
      });
      item.addEventListener('data_failed', stop);
      if (item.isLoaded) start(); else item.addEventListener('DOMLoaded', start);
      }).catch(stop);
    };
    load();
    return () => {
      alive = false; stop(); window.clearTimeout(timeout);
      observer?.disconnect(); document.removeEventListener('visibilitychange', visibility);
      motion.removeEventListener('change', motionChange);
    };
  }, [media, playKey, autoPlay, hoverKey]);
  const poster = failedPoster === media?.poster ? gift.image : media?.poster ?? gift.image;
  return <div ref={artwork} className="catalog-artwork" style={{ background: backdrop ? `radial-gradient(ellipse at center, ${backdrop.centerColor}, ${backdrop.edgeColor})` : '#131313' }}>
    {symbol?.image && <div className="catalog-artwork__pattern" style={{ backgroundColor: backdrop?.patternColor ?? '#fff', maskImage: `url("${symbol.image}")` }} />}
    <img src={poster || placeholder} alt={gift.name} loading="lazy" decoding="async" data-vector={Boolean(media && failedPoster !== media.poster)} style={{ visibility: playing ? 'hidden' : undefined }} onError={(event) => { if (media && failedPoster !== media.poster) setFailedPoster(media.poster); else if (!event.currentTarget.src.endsWith(placeholder)) event.currentTarget.src = placeholder; }} />
    {media && <div className="catalog-artwork__animation" ref={host} data-playing={playing} aria-hidden="true" />}
  </div>;
}
