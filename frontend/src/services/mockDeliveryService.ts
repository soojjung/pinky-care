import {
  type Delivery,
  type DeliveryRequest,
  type NurseReturnCommand,
} from "@/types/delivery";
import type { DeliveryService } from "./deliveryService";

const STEP_MS = 1500;
const SUCCESS_RATE = 0.8;

const store = new Map<string, Delivery>();
const subscribers = new Map<string, Set<(d: Delivery) => void>>();

const genId = () =>
  `d_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

const notify = (delivery: Delivery) => {
  store.set(delivery.id, delivery);
  subscribers.get(delivery.id)?.forEach((cb) => cb(delivery));
};

/**
 * ``requestDelivery`` 직후 자동으로 실행되는 배송 상태 머신 시뮬레이션.
 *
 * REQUESTED → MOVING → ARRIVED → VERIFYING → (SUCCESS or AWAITING_NURSE)
 *
 * SUCCESS 는 자동으로 도달하지만, 실패는 시나리오 v3 대로 AWAITING_NURSE 로만
 * 넘어간 뒤 ``sendNurseReturnCommand`` 를 기다린다.
 */
const startFlow = (id: string) => {
  const advance = (patch: Partial<Delivery>, ms: number) =>
    setTimeout(() => {
      const current = store.get(id);
      if (!current) return;
      notify({ ...current, ...patch });
    }, ms);

  advance({ status: "MOVING" }, STEP_MS);
  advance({ status: "ARRIVED" }, STEP_MS * 2);
  advance({ status: "VERIFYING" }, STEP_MS * 3);

  setTimeout(() => {
    const current = store.get(id);
    if (!current) return;
    const success = Math.random() < SUCCESS_RATE;
    if (success) {
      notify({ ...current, status: "SUCCESS", failReason: undefined });
    } else {
      // 실패는 자동 종료 안 함. 간호사 결정 대기.
      notify({
        ...current,
        status: "AWAITING_NURSE",
        failReason: "X_CARD_DETECTED",
      });
    }
  }, STEP_MS * 4);
};

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
    // 화면 마운트 · 훅 구독까지 100ms 정도 여유
    setTimeout(() => startFlow(delivery.id), 100);
    return delivery;
  },

  async getDelivery(id: string): Promise<Delivery> {
    const d = store.get(id);
    if (!d) throw new Error(`Delivery not found: ${id}`);
    return d;
  },

  subscribeStatus(id: string, cb: (d: Delivery) => void): () => void {
    let subs = subscribers.get(id);
    if (!subs) {
      subs = new Set();
      subscribers.set(id, subs);
    }
    subs.add(cb);
    return () => {
      subs?.delete(cb);
      if (subs?.size === 0) subscribers.delete(id);
    };
  },

  async sendNurseReturnCommand(
    id: string,
    command: NurseReturnCommand,
  ): Promise<Delivery> {
    const current = store.get(id);
    if (!current) throw new Error(`Delivery not found: ${id}`);
    if (current.status !== "AWAITING_NURSE") {
      throw new Error(
        `Cannot transition from ${current.status} — expected AWAITING_NURSE`,
      );
    }

    // "대기해, 내가 갈게" → 도착까지 짧은 지연 시뮬레이션
    const delay = command.choice === "AFTER_ARRIVAL" ? 400 : 100;
    await new Promise((resolve) => setTimeout(resolve, delay));

    const failed: Delivery = {
      ...current,
      status: "FAILED",
      failReason: command.reason || current.failReason,
    };
    notify(failed);
    return failed;
  },
};
