type Props = Readonly<{
  label: string;
  value: number;
  step?: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
  suffix?: string;
}>;

export function Field({ label, value, onChange, step, min, max, suffix }: Props) {
  return (
    <label className="flex flex-col gap-1">
      <div className="text-xs font-medium text-zinc-600">{label}</div>
      <div className="flex items-center gap-2">
        <input
          className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-950 shadow-sm outline-none focus:border-zinc-300 focus:ring-2 focus:ring-zinc-200"
          type="number"
          value={Number.isFinite(value) ? value : 0}
          step={step}
          min={min}
          max={max}
          onChange={(e) => onChange(e.currentTarget.valueAsNumber)}
        />
        {suffix ? <div className="text-xs text-zinc-500">{suffix}</div> : null}
      </div>
    </label>
  );
}

