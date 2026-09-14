"use client";

import { Button, Menu, Tooltip } from "antd";
import { ChevronLeft, ChevronRight, ExternalLink, GitBranch } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import {
  platformDefaultOpenKeys,
  platformNavigationItems,
  platformSelectedKey,
  primaryDefaultOpenKeys,
  primaryNavigationItems,
  primarySelectedKey,
} from "./portal-navigation";

export function SideNav({
  collapsed,
  onCollapse,
  onNavigate,
  showCollapse = true,
}: {
  collapsed: boolean;
  onCollapse?: () => void;
  onNavigate?: () => void;
  showCollapse?: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const researchUrl = process.env.NEXT_PUBLIC_RESEARCH_DASHBOARD_URL || "http://127.0.0.1:8051";

  const navigate = (path: string) => {
    router.push(path);
    onNavigate?.();
  };

  const openResearchDashboard = () => {
    window.open(researchUrl, "_blank", "noopener,noreferrer");
    onNavigate?.();
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--sidebar-bg)]">
      <div className="flex h-[var(--shell-header-height)] shrink-0 items-center gap-3 border-b border-[var(--color-border)] px-3.5">
        <div className="grid size-9 shrink-0 place-items-center rounded-[10px] bg-[var(--color-brand-soft)] text-[var(--color-brand)]">
          <GitBranch size={18} />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold tracking-[-0.01em] text-[var(--color-text)]">LLM–XAI</p>
            <p className="truncate text-[11px] font-medium text-[var(--color-text-muted)]">ResearchOps</p>
          </div>
        )}
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-3" aria-label="ResearchOps navigation">
        <Menu
          key={`primary-${pathname}`}
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={primarySelectedKey(pathname) ? [primarySelectedKey(pathname)!] : []}
          defaultOpenKeys={collapsed ? [] : primaryDefaultOpenKeys(pathname)}
          items={primaryNavigationItems}
          onClick={({ key }) => navigate(String(key))}
          className="ops-nav-menu border-0! bg-transparent!"
        />
      </nav>

      <div className="shrink-0 border-t border-[var(--color-border)] px-2 py-2.5">
        <Tooltip title={collapsed ? "Open Research Dashboard" : undefined} placement="right">
          <Button
            type="text"
            block
            icon={<ExternalLink size={17} />}
            onClick={openResearchDashboard}
            className={collapsed ? "justify-center!" : "justify-start!"}
          >
            {collapsed ? null : "Research Dashboard"}
          </Button>
        </Tooltip>

        <Menu
          key={`platform-${pathname}`}
          mode="inline"
          inlineCollapsed={collapsed}
          selectedKeys={platformSelectedKey(pathname) ? [platformSelectedKey(pathname)!] : []}
          defaultOpenKeys={collapsed ? [] : platformDefaultOpenKeys(pathname)}
          items={platformNavigationItems}
          onClick={({ key }) => navigate(String(key))}
          className="ops-nav-menu mt-1 border-0! bg-transparent!"
        />

        {showCollapse && (
          <Button
            type="text"
            block
            icon={collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
            onClick={onCollapse}
            className={collapsed ? "mt-1 justify-center!" : "mt-1 justify-start!"}
            aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {collapsed ? null : "Collapse"}
          </Button>
        )}
      </div>
    </div>
  );
}
