import { useState } from "react";
import { useNavigate } from "react-router-dom";
import RoomSelector from "@/components/RoomSelector";
import ItemSelector from "@/components/ItemSelector";
import { deliveryService } from "@/services";
import type { Item, Room } from "@/types/delivery";

export default function MainPage() {
  const navigate = useNavigate();
  const [room, setRoom] = useState<Room | null>(null);
  const [item, setItem] = useState<Item | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = room !== null && item !== null && !submitting;

  const handleStart = async () => {
    if (!room || !item) return;
    const payload = { room, item };
    console.log(payload);

    setSubmitting(true);
    try {
      const delivery = await deliveryService.requestDelivery(payload);
      navigate(`/delivery/${delivery.id}`);
    } catch (err) {
      console.error("배송 요청 실패", err);
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-8">
      <div>
        <h2 className="text-2xl font-semibold">배송 요청</h2>
        <p className="mt-1 text-sm text-slate-600">
          병실과 배송할 물품을 선택해주세요.
        </p>
      </div>

      <RoomSelector value={room} onChange={setRoom} />
      <ItemSelector value={item} onChange={setItem} />

      <button
        type="button"
        onClick={handleStart}
        disabled={!canSubmit}
        className={
          "!mt-16 w-full rounded-xl px-6 py-5 text-lg font-semibold text-white transition " +
          (canSubmit
            ? "bg-blue-800 hover:bg-blue-900"
            : "cursor-not-allowed bg-slate-300")
        }
      >
        {submitting ? "요청 중..." : "배송 시작"}
      </button>
    </section>
  );
}
