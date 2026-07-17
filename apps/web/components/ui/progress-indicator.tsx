interface ProgressIndicatorProps { value: number; label?: string; }

export function ProgressIndicator({ value, label }: ProgressIndicatorProps) {
  return (
    <div className="w-full">
      {label && <div className="mb-1.5 flex justify-between text-[11px] text-muted-text"><span>{label}</span><span>{value}%</span></div>}
      <progress className="h-1.5 w-full overflow-hidden rounded-full accent-primary" value={value} max="100">{value}%</progress>
    </div>
  );
}

