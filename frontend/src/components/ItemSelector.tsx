import type { Item } from "@/types/delivery";
import { ITEMS } from "@/constants/options";

interface Props {
  value: Item | null;
  onChange: (item: Item) => void;
}

export default function ItemSelector({ value, onChange }: Props) {
  return (
    <div>
      <p className="mb-2 text-sm font-medium text-slate-700">배송 물품 선택</p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {ITEMS.map((item) => {
          const selected = value === item;
          return (
            <button
              key={item}
              type="button"
              onClick={() => onChange(item)}
              className={
                "rounded-xl border px-4 py-6 text-lg font-semibold transition " +
                (selected
                  ? "border-blue-600 bg-blue-600 text-white shadow"
                  : "border-slate-300 bg-white text-slate-800 hover:border-blue-400")
              }
              aria-pressed={selected}
            >
              {item}
            </button>
          );
        })}
      </div>
    </div>
  );
}
