import type { Delivery, DeliveryRequest } from "@/types/delivery";

export interface DeliveryService {
  requestDelivery(req: DeliveryRequest): Promise<Delivery>;
  getDelivery(id: string): Promise<Delivery>;
  subscribeStatus(id: string, cb: (d: Delivery) => void): () => void;
}
