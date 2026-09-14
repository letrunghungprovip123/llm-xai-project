import { theme as antdTheme, type ThemeConfig } from "antd";
import type { PortalTheme } from "./theme-context";

const palettes = {
  light: {
    canvas: "#f7f8fa",
    surface: "#ffffff",
    subtle: "#f3f4f6",
    border: "#e4e7ec",
    text: "#101828",
    secondary: "#475467",
    brand: "#4f46e5",
    brandSoft: "#eef2ff",
    success: "#15803d",
    warning: "#b45309",
    danger: "#b42318",
    info: "#2563eb",
  },
  dark: {
    canvas: "#0b0d12",
    surface: "#111318",
    subtle: "#171a21",
    border: "#272b35",
    text: "#f5f7fa",
    secondary: "#d0d5dd",
    brand: "#818cf8",
    brandSoft: "rgba(129, 140, 248, 0.12)",
    success: "#4ade80",
    warning: "#fbbf24",
    danger: "#f87171",
    info: "#60a5fa",
  },
} as const;

export function buildAntdTheme(mode: PortalTheme): ThemeConfig {
  const palette = palettes[mode];

  return {
    algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: palette.brand,
      colorSuccess: palette.success,
      colorWarning: palette.warning,
      colorError: palette.danger,
      colorInfo: palette.info,
      colorBgLayout: palette.canvas,
      colorBgContainer: palette.surface,
      colorBgElevated: palette.surface,
      colorBorder: palette.border,
      colorText: palette.text,
      colorTextSecondary: palette.secondary,
      borderRadius: 8,
      borderRadiusLG: 12,
      controlHeight: 36,
      fontFamily: "var(--font-geist-sans)",
      fontSize: 14,
    },
    components: {
      Button: {
        controlHeight: 36,
        fontWeight: 500,
      },
      Menu: {
        itemBorderRadius: 8,
        itemHeight: 40,
        itemHoverBg: palette.subtle,
        itemHoverColor: palette.text,
        itemSelectedBg: palette.brandSoft,
        itemSelectedColor: palette.brand,
        subMenuItemBg: "transparent",
      },
      Table: {
        headerBg: "transparent",
        headerColor: palette.secondary,
        borderColor: palette.border,
        rowHoverBg: palette.subtle,
      },
    },
  };
}
