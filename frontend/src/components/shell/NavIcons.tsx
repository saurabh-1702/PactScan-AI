import {
  CheckSquare,
  FileEdit,
  LayoutDashboard,
  MessageSquare,
  Radar,
  ScanSearch,
} from "lucide-react";
import type { NavIcon } from "@/lib/permissions";

const ICONS: Record<NavIcon, React.ElementType> = {
  dashboard: LayoutDashboard,
  detect: ScanSearch,
  ask: MessageSquare,
  drafts: FileEdit,
  approvals: CheckSquare,
  horizon: Radar,
};

export function NavGlyph({ icon, className }: { icon: NavIcon; className?: string }) {
  const Icon = ICONS[icon];
  return <Icon className={className} aria-hidden />;
}
