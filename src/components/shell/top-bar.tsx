"use client";

import { Avatar, Badge, Button, Dropdown, Tooltip } from "antd";
import { Activity, Menu as MenuIcon, Moon, Search, Sun, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCapabilities, useOperations, useReadiness } from "@/lib/query/researchops-hooks";
import { usePortalTheme } from "@/lib/theme/theme-context";

export function TopBar({
  onOpenNavigation,
  onOpenPalette,
}: {
  onOpenNavigation: () => void;
  onOpenPalette: () => void;
}) {
  const router = useRouter();
  const { theme, toggle } = usePortalTheme();
  const readiness = useReadiness();
  const capabilities = useCapabilities();
  const activeOps = useOperations({ limit: 1, status: "RUNNING" });

  const apiReady = readiness.data?.ready === true;
  const apiOffline = readiness.isError;
  const apiChecking = readiness.isLoading || readiness.isFetching;
  const readinessLabel = apiReady ? "Healthy" : apiOffline ? "Offline" : apiChecking ? "Checking" : "Degraded";
  const readinessStatus: "success" | "error" | "processing" | "warning" = apiReady ? "success" : apiOffline ? "error" : apiChecking ? "processing" : "warning";
  const hasActiveOperations = Boolean(activeOps.data?.items.length);

  const readinessTooltip = readiness.error instanceof Error
    ? readiness.error.message
    : apiReady
      ? "FastAPI and critical dependencies are ready"
      : "Control plane is degraded or still checking dependencies";

  return (
    <header className="sticky top-0 z-30 flex h-[var(--shell-header-height)] items-center gap-2 border-b border-[var(--color-border)] bg-[var(--header-bg)] px-3 backdrop-blur-xl sm:px-5">
      <Button
        type="text"
        icon={<MenuIcon size={18} />}
        className="lg:hidden"
        onClick={onOpenNavigation}
        aria-label="Open navigation"
      />

      <button
        type="button"
        className="hidden h-9 w-full max-w-[400px] items-center gap-2 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-surface-subtle)] px-3 text-left text-[13px] text-[var(--color-text-muted)] transition hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-secondary)] sm:flex"
        onClick={onOpenPalette}
      >
        <Search size={15} />
        <span>Search or jump…</span>
        <span className="ml-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-1.5 py-0.5 font-mono text-[11px]">⌘K</span>
      </button>

      <Button
        type="text"
        icon={<Search size={17} />}
        className="sm:hidden"
        onClick={onOpenPalette}
        aria-label="Search or jump"
      />

      <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
        <Tooltip title={readinessTooltip}>
          <button
            type="button"
            onClick={() => router.push("/system")}
            className="hidden h-9 items-center gap-2 rounded-[var(--radius-sm)] px-2.5 text-[12px] font-medium text-[var(--color-text-secondary)] transition hover:bg-[var(--color-surface-subtle)] md:flex"
          >
            <Badge status={readinessStatus} />
            {readinessLabel}
          </button>
        </Tooltip>

        <Tooltip title="Control operation activity">
          <Button type="text" onClick={() => router.push("/operations?status=RUNNING")} aria-label="Open activity">
            <Badge dot={hasActiveOperations} offset={[1, 0]}>
              <span className="flex items-center gap-2">
                <Activity size={17} />
                <span className="hidden xl:inline">Activity</span>
              </span>
            </Badge>
          </Button>
        </Tooltip>

        <Tooltip title={theme === "dark" ? "Use light theme" : "Use dark theme"}>
          <Button
            type="text"
            icon={theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            onClick={toggle}
            aria-label="Toggle theme"
          />
        </Tooltip>

        <Dropdown
          menu={{
            items: [
              { key: "auth", label: `Authentication: ${capabilities.data?.auth_mode || "unknown"}`, disabled: true },
              { key: "identity", label: "Identity and permissions are enforced by FastAPI", disabled: true },
            ],
          }}
          placement="bottomRight"
        >
          <button
            type="button"
            className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]"
            aria-label="Identity information"
          >
            <Avatar size={34} icon={<UserRound size={16} />} />
          </button>
        </Dropdown>
      </div>
    </header>
  );
}
