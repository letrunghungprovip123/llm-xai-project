"use client";
import { createContext, useContext } from "react";
export type PortalTheme = "light" | "dark";
export const PortalThemeContext = createContext<{ theme: PortalTheme; toggle: () => void }>({ theme: "light", toggle: () => undefined });
export const usePortalTheme = () => useContext(PortalThemeContext);
