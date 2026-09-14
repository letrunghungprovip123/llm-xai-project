"use client";

import { useCallback, useState } from "react";
import { Drawer } from "antd";
import { CommandPalette } from "./command-palette";
import { SideNav } from "./side-nav";
import { TopBar } from "./top-bar";

export function OpsShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const handlePaletteOpenChange = useCallback((open: boolean) => setPaletteOpen(open), []);
  const sidebarWidth = collapsed ? "var(--shell-sidebar-collapsed-width)" : "var(--shell-sidebar-width)";

  return (
    <div className="min-h-dvh bg-[var(--color-canvas)] text-[var(--color-text)]">
      <aside
        className="fixed inset-y-0 left-0 z-40 hidden border-r border-[var(--color-border)] transition-[width] duration-200 lg:block"
        style={{ width: sidebarWidth }}
      >
        <SideNav collapsed={collapsed} onCollapse={() => setCollapsed((value) => !value)} />
      </aside>

      <Drawer
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        placement="left"
        width={280}
        closable={false}
        styles={{ body: { padding: 0 } }}
      >
        <SideNav collapsed={false} showCollapse={false} onNavigate={() => setMobileOpen(false)} />
      </Drawer>

      <div
        className="min-h-dvh transition-[padding] duration-200 lg:pl-[var(--sidebar-current)]"
        style={{ "--sidebar-current": sidebarWidth } as React.CSSProperties}
      >
        <TopBar
          onOpenNavigation={() => setMobileOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
        />

        <main className="mx-auto w-full max-w-[var(--content-max-width)] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>

      <CommandPalette open={paletteOpen} onOpenChange={handlePaletteOpenChange} />
    </div>
  );
}
