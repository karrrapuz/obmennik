# Gift Inventory Lifecycle

The Voodoo Doll grant is a simulated copy for presentation mode, not ownership
of `VoodooDoll-6565` in Telegram. It is priced at a fixed 43.950 GRAM for tests.

## Current Test Grant

- The catalog template is separate from each user's `inventory_gifts` row.
- `ensure_inventory` runs under the user's database lock.
- A permanent `(user_id, catalog_id)` grant marker prevents duplicate grants.
- The marker survives withdrawal/exchange, so a removed gift is not recreated.
- Existing and new accounts receive the gift on their next inventory load.
- The browser guest inventory uses an equivalent persistent grant marker.
- Production mode must never seed these simulated gifts.

## Future GiftRelayer Adapter

Reuse the separation between catalog templates, owned instances and receipts,
not the test seeding trigger. Before enabling real custody:

1. Verify an incoming Telegram transfer, its sender, recipient and unique slug.
2. Persist a globally unique external gift identity and a globally unique
   provider event ID. The per-user test grant marker alone is insufficient.
3. Lock the affected owner and apply inventory insertion and event receipt in
   one transaction. Replayed events return the original result, never a copy.
4. Reserve outgoing gifts, reject pledged/locked assets, and request transfer.
5. Remove ownership only after the provider confirms delivery. Timeouts remain
   pending and are reconciled, not blindly resent or treated as success.
6. Reconcile the custody account with internal ownership; do not grant every
   public profile gift to every user. Public visibility is not a deposit.

Shared links hold a read-only snapshot of the explicitly shared item. A link
does not grant ownership or permission to exchange/withdraw it.
