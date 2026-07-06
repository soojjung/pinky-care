import type { Room } from "@/types/delivery";
import { ROOMS } from "@/constants/options";

interface Props {
  value: Room | null;
  onChange: (room: Room) => void;
}

export default function RoomSelector({ value, onChange }: Props) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-slate-700">병실 선택</p>
      <div className="grid grid-cols-3 gap-3">
        {ROOMS.map((room) => {
          const selected = value === room;
          return (
            <button
              key={room}
              type="button"
              onClick={() => onChange(room)}
              className={
                "rounded-xl border px-4 py-6 text-lg font-semibold transition " +
                (selected
                  ? "border-blue-600 bg-blue-600 text-white shadow"
                  : "border-slate-300 bg-white text-slate-800 hover:border-blue-400")
              }
              aria-pressed={selected}
            >
              {room}호
            </button>
          );
        })}
      </div>
    </div>
  );
}
