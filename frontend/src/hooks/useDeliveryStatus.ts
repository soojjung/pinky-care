import { useEffect, useState } from "react";
import { deliveryService } from "@/services";
import type { Delivery } from "@/types/delivery";

interface Result {
  delivery: Delivery | null;
  error: Error | null;
}

export function useDeliveryStatus(id: string | undefined): Result {
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let unsubscribe: (() => void) | undefined;

    setDelivery(null);
    setError(null);

    deliveryService
      .getDelivery(id)
      .then((d) => {
        if (cancelled) return;
        setDelivery(d);
        unsubscribe = deliveryService.subscribeStatus(id, (next) => {
          if (!cancelled) setDelivery(next);
        });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e : new Error(String(e)));
        }
      });

    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [id]);

  return { delivery, error };
}
