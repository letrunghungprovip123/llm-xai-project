import Link from "next/link";
import { Button, Result } from "antd";

export default function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center bg-[var(--app-bg)] p-6">
      <Result
        status="404"
        title="Resource not found"
        subTitle="This ResearchOps route or resource is not available."
        extra={
          <Link href="/ops">
            <Button type="primary">Return to Mission Control</Button>
          </Link>
        }
      />
    </div>
  );
}
