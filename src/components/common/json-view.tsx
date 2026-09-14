export function JsonView({ value, maxHeight = 420 }: { value: unknown; maxHeight?: number }) {
  return (
    <pre className="overflow-auto rounded-xl border border-[var(--panel-border)] bg-[var(--code-bg)] p-4 font-mono text-xs leading-5" style={{ maxHeight }}>
      {JSON.stringify(value ?? null, null, 2)}
    </pre>
  );
}
