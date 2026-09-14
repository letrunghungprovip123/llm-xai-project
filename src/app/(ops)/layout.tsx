import { OpsShell } from "@/components/shell/ops-shell";

export default function OperationsLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <OpsShell>{children}</OpsShell>;
}
