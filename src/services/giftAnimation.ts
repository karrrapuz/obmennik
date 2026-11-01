type AnimationData = Record<string, unknown>;
const cache = new Map<string, AnimationData>();
const MAX_CACHED = 4;
const activePlayback = new Map<symbol, () => void>();
export const MAX_GIFT_PLAYBACK = 4;
let player: Promise<typeof import('lottie-web/build/player/lottie_light')> | undefined;

async function boundedBytes(stream: ReadableStream<Uint8Array>, limit: number, signal: AbortSignal) {
  signal.throwIfAborted();
  const reader = stream.getReader();
  const abort = () => { void reader.cancel(signal.reason).catch(() => {}); };
  signal.addEventListener('abort', abort, { once: true });
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      length += value.byteLength;
      if (length > limit) throw new Error('Animation exceeds size limit');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
  finally { signal.removeEventListener('abort', abort); reader.releaseLock(); }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength; }
  return result;
}

async function decodeAnimation(compressed: Uint8Array<ArrayBuffer>, signal: AbortSignal) {
  if (typeof DecompressionStream !== 'undefined') {
    return boundedBytes(new Blob([compressed.buffer]).stream().pipeThrough(new DecompressionStream('gzip')), 4_000_000, signal);
  }
  const { Gunzip } = await import('fflate');
  const chunks: Uint8Array[] = [];
  let length = 0;
  const decoder = new Gunzip(chunk => {
    length += chunk.length;
    if (length > 4_000_000) throw new Error('Animation exceeds size limit');
    chunks.push(chunk);
  });
  for (let offset = 0; offset < compressed.length; offset += 1024) {
    signal.throwIfAborted();
    decoder.push(compressed.subarray(offset, offset + 1024), offset + 1024 >= compressed.length);
  }
  const result = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.length; }
  return result;
}

export async function loadGiftAnimation(url: string, signal: AbortSignal) {
  signal.throwIfAborted();
  const existing = cache.get(url);
  if (existing) {
    cache.delete(url); cache.set(url, existing);
    return structuredClone(existing);
  }
  if (!url.startsWith('/gifts/vector/animations/') || !/^[\w/.-]+$/.test(url) || url.includes('..')) throw new Error('Invalid animation URL');
  const response = await fetch(url, { signal, credentials: 'omit', redirect: 'error' });
  if (!response.ok || !response.body) throw new Error('Animation unavailable');
  const compressed = await boundedBytes(response.body, 100000, signal);
  const decoded = await decodeAnimation(compressed, signal);
  signal.throwIfAborted();
  const data = JSON.parse(new TextDecoder().decode(decoded)) as AnimationData;
  if (data.w !== 512 || data.h !== 512 || !Array.isArray(data.layers)
      || typeof data.fr !== 'number' || !Number.isFinite(data.fr) || data.fr <= 0 || data.fr > 60
      || typeof data.op !== 'number' || typeof data.ip !== 'number' || !Number.isFinite(data.op) || !Number.isFinite(data.ip)
      || data.op <= data.ip || data.op - data.ip > 360
      || !Array.isArray(data.assets) || data.assets.some(asset => !asset || typeof asset !== 'object' || 'p' in asset)) {
    throw new Error('Invalid vector animation');
  }
  cache.set(url, data);
  while (cache.size > MAX_CACHED) cache.delete(cache.keys().next().value!);
  return structuredClone(data);
}

export function loadGiftPlayer() {
  player ??= import('lottie-web/build/player/lottie_light').catch(error => { player = undefined; throw error; });
  return player;
}

export function claimGiftPlayback(stop: () => void) {
  while (activePlayback.size >= MAX_GIFT_PLAYBACK) {
    const [key, oldest] = activePlayback.entries().next().value!;
    activePlayback.delete(key);
    oldest();
  }
  const key = Symbol();
  activePlayback.set(key, stop);
  return () => { activePlayback.delete(key); };
}
