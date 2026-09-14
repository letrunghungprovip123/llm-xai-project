"use client";

import { useEffect, useState } from "react";
import { App as AntdApp, ConfigProvider } from "antd";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "@/lib/query/query-client";
import { buildAntdTheme } from "@/lib/theme/antd-theme";
import { PortalThemeContext, type PortalTheme } from "@/lib/theme/theme-context";

const THEME_STORAGE_KEY = "researchops-theme";

export function AppProviders({ children }: Readonly<{ children: React.ReactNode }>) {
  const [queryClient] = useState(createQueryClient);
  const [theme, setTheme] = useState<PortalTheme>(() => {
    if (typeof window === "undefined") return "light";
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as PortalTheme | null;
    return stored || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const toggle = () => {
    setTheme((value) => {
      const next = value === "dark" ? "light" : "dark";
      localStorage.setItem(THEME_STORAGE_KEY, next);
      return next;
    });
  };

  return (
    <QueryClientProvider client={queryClient}>
      <PortalThemeContext.Provider value={{ theme, toggle }}>
        <ConfigProvider theme={buildAntdTheme(theme)}>
          <AntdApp>{children}</AntdApp>
        </ConfigProvider>
      </PortalThemeContext.Provider>
    </QueryClientProvider>
  );
}
