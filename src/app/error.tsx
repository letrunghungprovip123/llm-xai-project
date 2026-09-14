"use client";

import { Button, Result } from "antd";

export default function RootError({
  error,
  reset,
}: Readonly<{
  error: Error & { digest?: string };
  reset: () => void;
}>) {
  return (
    <div className="grid min-h-dvh place-items-center bg-[var(--app-bg)] p-6">
      <Result
        status="error"
        title="ResearchOps portal failed to render"
        subTitle={error.digest ? `Error digest: ${error.digest}` : error.message}
        extra={<Button onClick={reset}>Retry</Button>}
      />
    </div>
  );
}
