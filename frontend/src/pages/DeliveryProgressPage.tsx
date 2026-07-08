import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AwaitingNurseModal from "@/components/AwaitingNurseModal";
import DeliveryStatusStepper from "@/components/DeliveryStatusStepper";
import NurseWaitPanel from "@/components/NurseWaitPanel";
import { useDeliveryStatus } from "@/hooks/useDeliveryStatus";
import { deliveryService } from "@/services";
import { isTerminal, type NurseChoice } from "@/types/delivery";

export default function DeliveryProgressPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { delivery, error } = useDeliveryStatus(id);
  const [waitMode, setWaitMode] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!delivery || !isTerminal(delivery.status)) return;
    const t = setTimeout(() => {
      navigate(`/delivery/${delivery.id}/result`, { replace: true });
    }, 1000);
    return () => clearTimeout(t);
  }, [delivery, navigate]);

  const handleNurseCommand = async (
    choice: NurseChoice,
    reason?: string,
  ): Promise<void> => {
    if (!delivery) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      await deliveryService.sendNurseReturnCommand(delivery.id, {
        choice,
        reason,
      });
      // 성공 시 SSE 로 FAILED 이벤트 수신 → 위 useEffect 가 결과 페이지로 이동
    } catch (e) {
      setSubmitting(false);
      setSubmitError(e instanceof Error ? e.message : String(e));
    }
  };

  if (error) {
    return (
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">배송 정보를 찾을 수 없습니다.</h2>
        <button
          type="button"
          onClick={() => navigate("/", { replace: true })}
          className="rounded-lg bg-blue-800 px-4 py-2 text-white"
        >
          홈으로
        </button>
      </section>
    );
  }

  if (!delivery) {
    return <p className="text-slate-500">로딩 중...</p>;
  }

  const isAwaitingNurse = delivery.status === "AWAITING_NURSE";
  const showModal = isAwaitingNurse && !waitMode;
  const showWaitPanel = isAwaitingNurse && waitMode;

  return (
    <>
      <section className="space-y-6">
        <div>
          <h2 className="text-2xl font-semibold">배송 진행 중</h2>
          <p className="mt-1 text-slate-600">
            {delivery.room}호 · {delivery.item}
          </p>
        </div>

        <DeliveryStatusStepper current={delivery.status} />
      </section>

      {showModal && (
        <AwaitingNurseModal
          failReason={delivery.failReason}
          submitting={submitting}
          submitError={submitError}
          onImmediate={() => handleNurseCommand("IMMEDIATE")}
          onWait={() => {
            setWaitMode(true);
            setSubmitError(null);
          }}
        />
      )}

      {showWaitPanel && (
        <NurseWaitPanel
          failReason={delivery.failReason}
          submitting={submitting}
          submitError={submitError}
          onSendReturn={(reason) => handleNurseCommand("AFTER_ARRIVAL", reason)}
          onCancel={() => {
            setWaitMode(false);
            setSubmitError(null);
          }}
        />
      )}
    </>
  );
}
