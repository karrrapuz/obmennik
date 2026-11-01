# Presentation Catalog

The current presentation uses 30 simulated gift templates with fixed TON-shaped
prices: the original 20 samples plus 10 extra templates from already imported
public model/symbol/background assets. These are example transaction tariffs,
not live offers for the displayed rare models. Their ledger remains DEMO_TON.
No real payment, Telegram custody or external gift transfer is enabled.

The frontend defaults to presentation mode. Set `VITE_SHOWCASE_MODE=false` at
build time and `SHOWCASE_MODE=false` on the API to restore full catalog browsing.
Set `SHOWCASE_MODE=true` on the API for the 30-card presentation. Settings are
strict booleans, not arbitrary truthy strings. Existing user balances, owned
gifts, loans, imported collections and source data are not deleted.

Unknown-price imported inventory previews are hidden only in the presentation
UI; they remain in server snapshots/database. Seasonal seeding is paused in
presentation mode. Switching the mode off makes those previews visible again.
The ten new sample templates retain IDs 21-30 and remain resolvable for existing
owners after the mode is disabled. Do not reuse those IDs for unrelated gifts.

The public profile/exchange/payment screens use neutral product copy. Internal
asset names, integration status and administrator diagnostics still distinguish
simulation from real funds. Do not present this build as a functioning custody
or payment service; see `INTEGRATION_HANDOFF.md` before live activation.

Verification: `node scripts/check-showcase.mjs` checks 30 exact template IDs,
frontend/backend extra-template equality, positive prices, local media and a
reversible view. `backend/tests/test_showcase.py` covers server quotes/execution,
disabled real transfers and retained ownership across mode changes.
