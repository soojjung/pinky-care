import {
  DELIVERY_FLOW,
  STATUS_LABEL,
  type DeliveryStatus,
} from "@/types/delivery";

interface Props {
  current: DeliveryStatus;
}

export default function DeliveryStatusStepper({ current }: Props) {
  const isFailed = current === "FAILED";
  const isSuccess = current === "SUCCESS";
  const isAwaitingNurse = current === "AWAITING_NURSE";
  const isDone = isSuccess || isFailed;
  const currentIndex = DELIVERY_FLOW.indexOf(current);

  return (
    <ol className="space-y-6">
      {DELIVERY_FLOW.map((status, i) => {
        const failedHere = isFailed && i === DELIVERY_FLOW.length - 1;
        // AWAITING_NURSE와 SUCCESS는 정상 흐름 전체가 지나간 상태로 취급
        const done =
          isSuccess ||
          isAwaitingNurse ||
          (isFailed && !failedHere) ||
          (!isDone && !isAwaitingNurse && i < currentIndex);
        const active = !isDone && !isAwaitingNurse && i === currentIndex;

        return (
          <li key={status} className="flex items-center gap-4">
            <span
              className={
                "flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold " +
                (failedHere
                  ? "bg-red-500 text-white"
                  : done
                    ? "bg-blue-800 text-white"
                    : active
                      ? "bg-blue-100 text-blue-900 ring-2 ring-blue-700"
                      : "bg-slate-200 text-slate-500")
              }
              aria-hidden
            >
              {failedHere ? "!" : done ? "✓" : i + 1}
            </span>
            <span
              className={
                "text-xl " +
                (active
                  ? "animate-pulse font-semibold text-slate-900"
                  : done
                    ? "text-slate-700"
                    : "text-slate-400")
              }
            >
              {STATUS_LABEL[status]}
              {active && <span className="ml-2 text-blue-800">●</span>}
            </span>
          </li>
        );
      })}
      {isAwaitingNurse && (
        <li className="flex items-center gap-4 border-t border-red-100 pt-4">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-red-100 text-lg text-red-700"
            aria-hidden
          >
            ⚠
          </span>
          <span className="animate-pulse text-xl font-semibold text-red-700">
            확인 필요
          </span>
        </li>
      )}
    </ol>
  );
}
