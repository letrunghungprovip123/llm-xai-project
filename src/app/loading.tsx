export default function RootLoading() {
  return (
    <div className="grid min-h-dvh place-items-center bg-[var(--app-bg)] px-6">
      <div className="flex items-center gap-3 text-sm text-[var(--muted)]">
        <span className="size-2 animate-pulse rounded-full bg-[var(--brand)]" />
        Loading ResearchOps Mission Control…
      </div>
    </div>
  );
}
