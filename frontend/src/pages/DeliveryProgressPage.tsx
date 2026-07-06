import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import DeliveryStatusStepper from "@/components/DeliveryStatusStepper";
import { useDeliveryStatus } from "@/hooks/useDeliveryStatus";
import { isTerminal } from "@/types/delivery";

export default function DeliveryProgressPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { delivery, error } = useDeliveryStatus(id);

  useEffect(() => {
    if (!delivery || !isTerminal(delivery.status)) return;
    const t = setTimeout(() => {
      navigate(`/delivery/${delivery.id}/result`, { replace: true });
    }, 1000);
    return () => clearTimeout(t);
  }, [delivery, navigate]);

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

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">배송 진행 중</h2>
        <p className="mt-1 text-slate-600">
          {delivery.room}호 · {delivery.item}
        </p>
      </div>

      <DeliveryStatusStepper current={delivery.status} />
    </section>
  );
}
