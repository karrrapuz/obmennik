let initialized = false;

export function initializeVisibleViewport() {
  if (initialized || !window.visualViewport) return;
  initialized = true;
  const viewport = window.visualViewport;
  let frame = 0;
  const update = () => {
    frame = 0;
    // Pinch zoom remains native; only track the unzoomed keyboard/viewport area.
    if (Math.abs(viewport.scale - 1) > 0.01 || viewport.height <= 0) return;
    document.documentElement.style.setProperty('--visible-height', `${viewport.height}px`);
    document.documentElement.style.setProperty('--visible-top', `${viewport.offsetTop}px`);
  };
  const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
  viewport.addEventListener('resize', schedule);
  viewport.addEventListener('scroll', schedule);
  window.addEventListener('resize', schedule);
  update();
}
