import type {
  Delivery,
  DeliveryRequest,
  NurseReturnCommand,
} from "@/types/delivery";

export interface DeliveryService {
  requestDelivery(req: DeliveryRequest): Promise<Delivery>;
  getDelivery(id: string): Promise<Delivery>;
  subscribeStatus(id: string, cb: (d: Delivery) => void): () => void;
  /**
   * 실패 알림 후 간호사가 복귀 명령을 보낸다.
   * AWAITING_NURSE → FAILED 로 전이하며 로봇 복귀를 발동한다.
   */
  sendNurseReturnCommand(
    id: string,
    command: NurseReturnCommand,
  ): Promise<Delivery>;
}
