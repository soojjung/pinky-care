import {
  isTerminal,
  type Delivery,
  type DeliveryRequest,
  type NurseReturnCommand,
} from "@/types/delivery";
import type { DeliveryService } from "./deliveryService";

const BASE_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

interface ApiErrorEnvelope {
  error?: { code?: string; message?: string };
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(res: Response): Promise<ApiError> {
  let code = "UNKNOWN";
  let message = res.statusText || `HTTP ${res.status}`;
  try {
    const body = (await res.json()) as ApiErrorEnvelope;
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
    }
  } catch {
    // non-JSON body — keep defaults
  }
  return new ApiError(res.status, code, message);
}

export const apiDeliveryService: DeliveryService = {
  async requestDelivery(req: DeliveryRequest): Promise<Delivery> {
    const res = await fetch(`${BASE_URL}/deliveries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) throw await toApiError(res);
    return (await res.json()) as Delivery;
  },

  async getDelivery(id: string): Promise<Delivery> {
    const res = await fetch(`${BASE_URL}/deliveries/${encodeURIComponent(id)}`);
    if (!res.ok) throw await toApiError(res);
    return (await res.json()) as Delivery;
  },

  subscribeStatus(id: string, cb: (d: Delivery) => void): () => void {
    const es = new EventSource(
      `${BASE_URL}/deliveries/${encodeURIComponent(id)}/events`,
    );

    es.addEventListener("status", (event) => {
      try {
        const delivery = JSON.parse((event as MessageEvent).data) as Delivery;
        cb(delivery);
        if (isTerminal(delivery.status)) {
          es.close();
        }
      } catch {
        // malformed payload — ignore
      }
    });

    return () => es.close();
  },

  async sendNurseReturnCommand(
    id: string,
    command: NurseReturnCommand,
  ): Promise<Delivery> {
    const res = await fetch(
      `${BASE_URL}/deliveries/${encodeURIComponent(id)}/nurse-return-command`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(command),
      },
    );
    if (!res.ok) throw await toApiError(res);
    return (await res.json()) as Delivery;
  },
};
