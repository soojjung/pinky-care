import { useNavigate, useParams } from "react-router-dom";
import { useDeliveryStatus } from "@/hooks/useDeliveryStatus";
import { formatFailReason } from "@/types/delivery";

export default function DeliveryResultPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { delivery, error } = useDeliveryStatus(id);

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

  if (!delivery) return <p className="text-slate-500">로딩 중...</p>;

  const success = delivery.status === "SUCCESS";
  const failed = delivery.status === "FAILED";

  return (
    <section className="space-y-8 text-center">
      <div>
        <div
          className={
            "mx-auto flex h-24 w-24 items-center justify-center rounded-full text-5xl font-bold text-white " +
            (success ? "bg-green-500" : failed ? "bg-red-500" : "bg-slate-400")
          }
          aria-hidden
        >
          {success ? "✓" : failed ? "✕" : "…"}
        </div>
        <h2 className="mt-6 text-2xl font-semibold">
          {success ? "배송 완료" : failed ? "배송 실패" : "진행 중"}
        </h2>
        <p className="mt-3 text-2xl font-medium text-slate-800">
          {delivery.room}호 · {delivery.item}
        </p>
        {failed && delivery.failReason && (
          <p className="mt-2 text-sm text-red-600">
            사유: {formatFailReason(delivery.failReason)}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => navigate("/", { replace: true })}
        className="w-full rounded-xl bg-blue-800 px-6 py-4 text-lg font-semibold text-white transition hover:bg-blue-900"
      >
        홈으로
      </button>
    </section>
  );
}
