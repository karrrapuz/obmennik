import { useEffect, useState } from 'react';
import { giftRepository, type GiftLists } from '../services/giftRepository';

export function useGiftLists() {
  const [lists, setLists] = useState<GiftLists>({ catalog: [], inventory: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    giftRepository.load(controller.signal).then((result) => {
      if (!controller.signal.aborted) setLists(result);
    }).catch(() => {
      if (!controller.signal.aborted) setError(true);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [revision]);

  const exchange = (offered: number[], received: number[]) => setLists((current) => ({
    catalog: current.catalog.filter((gift) => !received.includes(gift.id)),
    inventory: [...current.inventory.filter((gift) => !offered.includes(gift.id)), ...current.catalog.filter((gift) => received.includes(gift.id))],
  }));
  return { ...lists, loading, error, exchange, reload: () => setRevision((value) => value + 1) };
}
