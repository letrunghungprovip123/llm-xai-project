import type { MenuProps } from "antd";
import type { ReactNode } from "react";
import {
  Activity,
  Archive,
  Boxes,
  CircleGauge,
  DatabaseZap,
  PackageCheck,
  ServerCog,
  ShieldCheck,
  UserCheck,
  Workflow,
} from "lucide-react";

export const primaryNavigationItems: MenuProps["items"] = [
  {
    key: "/ops",
    icon: <CircleGauge size={17} />,
    label: "Overview",
  },
  {
    key: "/runs",
    icon: <Workflow size={17} />,
    label: "Runs",
  },
  {
    key: "governance",
    icon: <ShieldCheck size={17} />,
    label: "Governance",
    children: [
      { key: "/quality/gates", icon: <ShieldCheck size={16} />, label: "Gates" },
      { key: "/quality/approvals", icon: <UserCheck size={16} />, label: "Approvals" },
    ],
  },
  {
    key: "/artifacts",
    icon: <Archive size={17} />,
    label: "Artifacts",
  },
  {
    key: "/delivery/releases",
    icon: <PackageCheck size={17} />,
    label: "Releases",
  },
];

export const platformNavigationItems: MenuProps["items"] = [
  {
    key: "platform",
    icon: <ServerCog size={17} />,
    label: "Platform",
    children: [
      { key: "/system", icon: <ServerCog size={16} />, label: "Health & System" },
      { key: "/registry", icon: <DatabaseZap size={16} />, label: "Registry" },
    ],
  },
];

export type PaletteDestination = {
  label: string;
  path: string;
  description: string;
  keywords: string[];
  icon: ReactNode;
};

export const paletteDestinations: PaletteDestination[] = [
  { label: "Overview", path: "/ops", description: "Mission control and current state", keywords: ["home", "mission", "attention"], icon: <CircleGauge size={17} /> },
  { label: "Runs", path: "/runs", description: "Pipeline runs and execution state", keywords: ["pipeline", "workflow", "stage"], icon: <Workflow size={17} /> },
  { label: "Governance · Gates", path: "/quality/gates", description: "Gate results and evaluations", keywords: ["quality", "gate", "evaluation", "waiver"], icon: <ShieldCheck size={17} /> },
  { label: "Governance · Approvals", path: "/quality/approvals", description: "Approval requests and decisions", keywords: ["approval", "approve", "reject", "review"], icon: <UserCheck size={17} /> },
  { label: "Artifacts", path: "/artifacts", description: "Artifact registry, files and lineage", keywords: ["artifact", "lineage", "manifest", "file"], icon: <Archive size={17} /> },
  { label: "Releases", path: "/delivery/releases", description: "Release readiness and promotion", keywords: ["release", "delivery", "promotion", "certified"], icon: <PackageCheck size={17} /> },
  { label: "Models", path: "/delivery/models", description: "Registered model versions", keywords: ["model", "mlflow", "version"], icon: <Boxes size={17} /> },
  { label: "Operations", path: "/operations", description: "Durable control operations and activity", keywords: ["operation", "activity", "command", "control"], icon: <Activity size={17} /> },
  { label: "Platform · Health & System", path: "/system", description: "Readiness, capabilities and versions", keywords: ["system", "health", "ready", "api", "version"], icon: <ServerCog size={17} /> },
  { label: "Platform · Registry", path: "/registry", description: "Stages, flows and deployments", keywords: ["registry", "stage", "flow", "deployment", "prefect"], icon: <DatabaseZap size={17} /> },
];

export function primarySelectedKey(pathname: string): string | undefined {
  if (pathname.startsWith("/quality/gates")) return "/quality/gates";
  if (pathname.startsWith("/quality/approvals")) return "/quality/approvals";
  if (pathname.startsWith("/delivery/releases") || pathname.startsWith("/delivery/models")) return "/delivery/releases";
  if (pathname.startsWith("/artifacts")) return "/artifacts";
  if (pathname.startsWith("/runs")) return "/runs";
  if (pathname.startsWith("/ops")) return "/ops";
  return undefined;
}

export function platformSelectedKey(pathname: string): string | undefined {
  if (pathname.startsWith("/system")) return "/system";
  if (pathname.startsWith("/registry")) return "/registry";
  return undefined;
}

export function primaryDefaultOpenKeys(pathname: string): string[] {
  return pathname.startsWith("/quality/") ? ["governance"] : [];
}

export function platformDefaultOpenKeys(pathname: string): string[] {
  return pathname.startsWith("/system") || pathname.startsWith("/registry") ? ["platform"] : [];
}
