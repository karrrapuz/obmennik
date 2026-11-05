import { useInventory } from '../../../inventory/InventoryProvider';
import { useMemo } from 'react';
import relayerPreview from '../data/relayer-preview.json';
import type { Gift } from '../data/gifts';

export function useGiftLists() {
  const { mutate, catalog, ...snapshot } = useInventory();
  const previewCatalog = useMemo(() => [relayerPreview as Gift, ...catalog.filter(gift => gift.id !== relayerPreview.id)], [catalog]);
  return { ...snapshot, catalog: previewCatalog, exchange: (offered: number[], received: number[]) => mutate('exchange', { offered_ids: offered, received_ids: received }) };
}
