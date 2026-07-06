export type Room = "101" | "102" | "103";

export type Item = "약" | "주사" | "붕대" | "생리식염수";

export type DeliveryStatus =
  | "REQUESTED"
  | "MOVING"
  | "ARRIVED"
  | "VERIFYING"
  | "SUCCESS"
  | "FAILED";

export interface DeliveryRequest {
  room: Room;
  item: Item;
}

export interface Delivery {
  id: string;
  room: Room;
  item: Item;
  status: DeliveryStatus;
  createdAt: string;
  failReason?: string;
}

export const DELIVERY_FLOW: DeliveryStatus[] = [
  "REQUESTED",
  "MOVING",
  "ARRIVED",
  "VERIFYING",
];

export const STATUS_LABEL: Record<DeliveryStatus, string> = {
  REQUESTED: "배송 요청 완료",
  MOVING: "로봇 이동 중",
  ARRIVED: "목적지 도착",
  VERIFYING: "배송 확인 중",
  SUCCESS: "배송 완료",
  FAILED: "배송 실패",
};

export const isTerminal = (s: DeliveryStatus): boolean =>
  s === "SUCCESS" || s === "FAILED";
