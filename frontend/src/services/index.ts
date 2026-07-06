import type { DeliveryService } from "./deliveryService";
import { apiDeliveryService } from "./apiDeliveryService";

export const deliveryService: DeliveryService = apiDeliveryService;
