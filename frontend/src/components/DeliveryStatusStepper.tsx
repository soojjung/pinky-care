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
  const isDone = isSuccess || isFailed;
  const currentIndex = DELIVERY_FLOW.indexOf(current);

  return (
    <ol className="space-y-6">
      {DELIVERY_FLOW.map((status, i) => {
        const done = isDone ? !isFailed || i < DELIVERY_FLOW.length - 1 || isSuccess : i < currentIndex;
        const active = !isDone && i === currentIndex;
        const failedHere = isFailed && i === DELIVERY_FLOW.length - 1;

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
    </ol>
  );
}
