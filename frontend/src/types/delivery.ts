export type Room = "102" | "103" | "104";

export type Item = "약" | "기저귀" | "혈당측정키트" | "물티슈";

export type DeliveryStatus =
  | "REQUESTED"
  | "MOVING"
  | "ARRIVED"
  | "VERIFYING"
  | "AWAITING_NURSE"
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

/** 스텝퍼에 표시되는 정상 흐름 단계. AWAITING_NURSE는 실패 브랜치라 별도 UI. */
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
  AWAITING_NURSE: "확인 필요",
  SUCCESS: "배송 완료",
  FAILED: "배송 실패",
};

/** SSE 스트림이 닫히는 최종 상태. AWAITING_NURSE는 아직 대기 상태라 포함되지 않음. */
export const isTerminal = (s: DeliveryStatus): boolean =>
  s === "SUCCESS" || s === "FAILED";

// ─── 실패 사유 ─────────────────────────────────────────

/** YOLO가 자동 판정한 실패 사유 enum. 백엔드 FailReason 과 1:1. */
export const FAIL_REASON_CODES = [
  "X_CARD_DETECTED",
  "TIMEOUT_NO_CARD",
  "AMBIGUOUS_BOTH_CARDS",
] as const;
export type FailReasonCode = (typeof FAIL_REASON_CODES)[number];

export const FAIL_REASON_LABEL: Record<FailReasonCode, string> = {
  X_CARD_DETECTED: "실패 카드(X)가 감지되었습니다",
  TIMEOUT_NO_CARD: "30초 안에 카드를 인식하지 못했습니다",
  AMBIGUOUS_BOTH_CARDS: "성공과 실패 카드가 모두 감지되었습니다",
};

/**
 * 백엔드가 준 failReason 문자열을 화면 표시용 한국어 문구로 변환.
 * - YOLO enum 코드면 정해진 문구
 * - 간호사 자유 텍스트(예: "환자 부재")면 그대로 반환
 * - 값 없으면 undefined
 */
export const formatFailReason = (
  reason: string | undefined,
): string | undefined => {
  if (!reason) return undefined;
  if ((FAIL_REASON_CODES as readonly string[]).includes(reason)) {
    return FAIL_REASON_LABEL[reason as FailReasonCode];
  }
  return reason;
};

// ─── 간호사 복귀 명령 ──────────────────────────────────

/** 실패 알림 후 간호사의 선택. 감사 로그용 (백엔드 동작은 동일). */
export type NurseChoice = "IMMEDIATE" | "AFTER_ARRIVAL";

export interface NurseReturnCommand {
  /** "바로 복귀" = IMMEDIATE, "대기해, 내가 갈게" 후 도착 = AFTER_ARRIVAL */
  choice: NurseChoice;
  /** YOLO 사유 위에 덮어쓸 자유 텍스트 (선택) */
  reason?: string;
}
