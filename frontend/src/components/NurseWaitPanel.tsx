import { useState } from "react";
import { formatFailReason } from "@/types/delivery";

interface Props {
  /** YOLO가 붙인 자동 사유 (감사 로그용) */
  failReason: string | undefined;
  submitting: boolean;
  submitError: string | null;
  /**
   * "복귀 보내기" 버튼 클릭. 간호사가 입력한 사유가 있으면 함께 전달.
   * 없으면 undefined — 백엔드는 기존 YOLO 사유를 유지한다.
   */
  onSendReturn: (reason: string | undefined) => void;
  /** "돌아가서 다시 선택" — 로컬 상태만 되돌려 모달로 복귀 */
  onCancel: () => void;
}

/**
 * "대기해, 내가 갈게" 선택 후 뜨는 대기 패널.
 *
 * 간호사가 병실에 도착해 상황을 확인한 뒤 자유 텍스트로 실패 사유를 보완하고
 * ``복귀 보내기`` 를 누른다. 백엔드에는 ``choice=AFTER_ARRIVAL`` 로 전달돼서
 * 감사 로그에 "대기 후 처리" 로 기록된다.
 */
export default function NurseWaitPanel({
  failReason,
  submitting,
  submitError,
  onSendReturn,
  onCancel,
}: Props) {
  const [reason, setReason] = useState("");
  const yoloReasonText = formatFailReason(failReason);

  const handleSubmit = () => {
    const trimmed = reason.trim();
    onSendReturn(trimmed.length > 0 ? trimmed : undefined);
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="nurse-wait-title"
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <div className="mb-4 flex items-center gap-3">
          <div
            className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 text-2xl"
            aria-hidden
          >
            🕐
          </div>
          <h2 id="nurse-wait-title" className="text-xl font-semibold">
            병실 도착 후 복귀 보내기
          </h2>
        </div>

        <p className="mb-4 text-slate-700">
          로봇이 병실에서 대기 중입니다. 상황을 확인한 뒤 아래 버튼을 눌러
          로봇을 복귀시켜 주세요.
        </p>

        {yoloReasonText && (
          <p className="mb-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            <span className="font-medium">자동 감지 사유:</span> {yoloReasonText}
          </p>
        )}

        <label className="mb-4 block">
          <span className="mb-1 block text-sm font-medium text-slate-700">
            실패 사유 보완 <span className="text-slate-400">(선택)</span>
          </span>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="예: 환자 부재, 물품 잘못됨"
            className="w-full rounded-lg border border-slate-300 p-3 text-slate-800 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
            rows={3}
            disabled={submitting}
          />
        </label>

        {submitError && (
          <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {submitError}
          </p>
        )}

        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className={
              "w-full rounded-xl px-6 py-4 text-lg font-semibold text-white transition " +
              (submitting
                ? "cursor-not-allowed bg-slate-300"
                : "bg-blue-800 hover:bg-blue-900")
            }
          >
            {submitting ? "처리 중..." : "복귀 보내기"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="text-sm text-slate-500 underline hover:text-slate-700 disabled:opacity-50"
          >
            돌아가서 다시 선택
          </button>
        </div>
      </div>
    </div>
  );
}
