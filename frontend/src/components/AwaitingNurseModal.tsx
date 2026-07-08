import { formatFailReason } from "@/types/delivery";

interface Props {
  /** 백엔드가 보내온 raw failReason (enum 또는 자유 텍스트) */
  failReason: string | undefined;
  submitting: boolean;
  submitError: string | null;
  /** "바로 복귀" — 즉시 복귀 명령 발동 */
  onImmediate: () => void;
  /** "대기해, 내가 갈게" — 로컬 상태만 바꿔 대기 화면으로 */
  onWait: () => void;
}

/**
 * AWAITING_NURSE 상태 도달 시 뜨는 실패 알림 모달.
 *
 * 시나리오 v3 §3⑥ — YOLO 실패 판정 후 로봇이 병실에서 대기한다.
 * 간호사는 이 모달에서 다음 두 갈래 중 하나를 선택.
 */
export default function AwaitingNurseModal({
  failReason,
  submitting,
  submitError,
  onImmediate,
  onWait,
}: Props) {
  const reasonText = formatFailReason(failReason);

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="awaiting-nurse-title"
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-2xl"
            aria-hidden
          >
            ⚠️
          </div>
          <h2 id="awaiting-nurse-title" className="text-xl font-semibold">
            확인 필요
          </h2>
        </div>

        <p className="mb-2 text-slate-800">
          {reasonText ?? "배송 확인 중 문제가 발생했습니다."}
        </p>
        <p className="mb-6 text-sm text-slate-500">
          로봇이 병실에서 대기 중입니다. 어떻게 처리할까요?
        </p>

        {submitError && (
          <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {submitError}
          </p>
        )}

        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={onImmediate}
            disabled={submitting}
            className={
              "w-full rounded-xl px-6 py-4 text-lg font-semibold text-white transition " +
              (submitting
                ? "cursor-not-allowed bg-slate-300"
                : "bg-red-600 hover:bg-red-700")
            }
          >
            {submitting ? "처리 중..." : "바로 복귀"}
          </button>
          <button
            type="button"
            onClick={onWait}
            disabled={submitting}
            className={
              "w-full rounded-xl border-2 border-blue-800 bg-white px-6 py-4 text-lg font-semibold text-blue-800 transition " +
              (submitting
                ? "cursor-not-allowed opacity-50"
                : "hover:bg-blue-50")
            }
          >
            대기해, 내가 갈게
          </button>
        </div>
      </div>
    </div>
  );
}
