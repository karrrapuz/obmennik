import { useInventory } from '../../../inventory/InventoryProvider';

export function useGiftLists() {
  const { mutate, ...snapshot } = useInventory();
  return { ...snapshot, exchange: (offered: number[], received: number[]) => mutate('exchange', { offered_ids: offered, received_ids: received }) };
}
