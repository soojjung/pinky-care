import {
  isTerminal,
  type Delivery,
  type DeliveryRequest,
  type DeliveryStatus,
} from "@/types/delivery";
import type { DeliveryService } from "./deliveryService";

const store = new Map<string, Delivery>();

const STEP_MS = 1500;
const SUCCESS_RATE = 0.8;

const genId = () =>
  `d_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

export const mockDeliveryService: DeliveryService = {
  async requestDelivery(req: DeliveryRequest): Promise<Delivery> {
    const delivery: Delivery = {
      id: genId(),
      room: req.room,
      item: req.item,
      status: "REQUESTED",
      createdAt: new Date().toISOString(),
    };
    store.set(delivery.id, delivery);
    return delivery;
  },

  async getDelivery(id: string): Promise<Delivery> {
    const d = store.get(id);
    if (!d) throw new Error(`Delivery not found: ${id}`);
    return d;
  },

  subscribeStatus(id: string, cb: (d: Delivery) => void): () => void {
    const initial = store.get(id);
    if (!initial || isTerminal(initial.status)) {
      return () => {};
    }
    const flow: DeliveryStatus[] = ["MOVING", "ARRIVED", "VERIFYING"];
    let cancelled = false;
    const timers: ReturnType<typeof setTimeout>[] = [];

    const emit = (status: DeliveryStatus, failReason?: string) => {
      const current = store.get(id);
      if (!current || cancelled) return;
      const updated: Delivery = { ...current, status, failReason };
      store.set(id, updated);
      cb(updated);
    };

    flow.forEach((status, i) => {
      timers.push(
        setTimeout(() => emit(status), STEP_MS * (i + 1)),
      );
    });

    timers.push(
      setTimeout(
        () => {
          const success = Math.random() < SUCCESS_RATE;
          emit(
            success ? "SUCCESS" : "FAILED",
            success ? undefined : "물품 인식 실패",
          );
        },
        STEP_MS * (flow.length + 1),
      ),
    );

    return () => {
      cancelled = true;
      timers.forEach(clearTimeout);
    };
  },
};
