# Gift Media

The 30 presentation models use original public Telegram TGS documents, not
enlarged 128px thumbnails. Their 512x512 vector animations were verified locally.
Static frame-60 SVG posters contain paths/gradients, not embedded raster images.
Models are matched by collection ID and normalized model name, never owned gift
instance IDs. Unknown future models retain their existing image fallback.

| File | Purpose |
| --- | --- |
| `public/gifts/vector/posters/` | Lazy-loaded static SVG images for all normal cards |
| `public/gifts/vector/animations/` | Original gzip-compressed TGS files, requested only on selection |
| `src/services/gift-media.json`, `public/gifts/vector/manifest.json` | Same public model/media mapping; no sessions, API keys or private file references |
| `src/services/giftMedia.ts` | Canonical model lookup and high-quality poster selection |
| `src/services/giftAnimation.ts` | Bounded decompression, four-entry decoded LRU and one playback lease |
| `scripts/build-gift-vectors.mjs` | Rebuild posters from approved local TGS inputs and public metadata |

`GiftArtwork` keeps a normal image at rest. The expression-free Lottie light
player is a separate dynamic chunk, loaded on the first explicit selection.
One original animation plays once; completion, deselection, navigation offscreen,
backgrounding or reduced-motion activation destroys the player. Obsolete fetches
and stream readers are cancelled. The decoded cache holds at most four models;
player input is cloned so Lottie repeaters cannot mutate cached originals.
No constant grid-wide animation, per-frame React state or permanent SVG DOM trees
are used. Failed/unsupported animation loading leaves the static poster visible.

On clients without native gzip `DecompressionStream`, selection still works and
the SVG remains visible, but animation is skipped. Imported animation streams
are limited to 100KB compressed / 4MB decoded and must be local pure-vector models.

Page-entry staggering was removed without changing swipe navigation, footer or
modal behavior. On coarse-touch devices, editable controls use at least 16px
fonts to avoid focus-triggered mobile Safari zoom. Native pinch zoom is not
disabled. Chromium touch emulation verifies sizes/viewport stability; real iOS
keyboard behavior still deserves device verification.

Checks:

```sh
node scripts/check-gift-media.mjs
node scripts/check-gift-animation-cache.mjs
node scripts/check-input-behavior.mjs
# Start the app first. Install Chromium with npx playwright install chromium,
# or set GIFT_BROWSER_EXECUTABLE to an existing browser binary.
node scripts/check-gift-animation-browser.mjs
```

Set `GIFT_TEST_URL` to check a deployed frontend. Browser checks use an isolated
guest context; they never authorize a real payment or transfer. Pricing and the
offers/receives summary logic are intentionally unchanged in this change.
