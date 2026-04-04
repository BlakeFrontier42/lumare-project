"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { useAppStore } from "@/store";
import {
  LayoutDashboard,
  Search,
  Globe,
  ArrowLeftRight,
  Users,
  Shield,
  Store,
  AlertTriangle,
  Calculator,
  Settings,
  ChevronLeft,
  ChevronRight,
  CandlestickChart,
  Layers,
  Grid3X3,
  List,
  Filter,
  Newspaper,
  BookOpen,
  Calendar,
  Bell,
  LayoutGrid,
  Activity,
  Database,
  Briefcase,
  GitBranch,
  Bot,
  Receipt,
  Home,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

const primaryNav: NavItem[] = [
  { label: "Home", href: "/", icon: LayoutDashboard },
  { label: "Intel", href: "/intel", icon: Search },
  { label: "Macro", href: "/macro", icon: Globe },
  { label: "Trade", href: "/trade", icon: ArrowLeftRight },
  { label: "Charts", href: "/charts", icon: LayoutGrid },
  { label: "Futures", href: "/futures", icon: CandlestickChart },
  { label: "Options", href: "/options", icon: Layers },
  { label: "Tape", href: "/tape", icon: Activity },
];

const secondaryNav: NavItem[] = [
  { label: "Heatmap", href: "/heatmap", icon: Grid3X3 },
  { label: "Screener", href: "/screener", icon: Filter },
  { label: "Watchlist", href: "/watchlist", icon: List },
  { label: "News", href: "/news", icon: Newspaper },
  { label: "Flow", href: "/flow", icon: Database },
];

const tertiaryNav: NavItem[] = [
  { label: "Portfolio", href: "/portfolio", icon: Briefcase },
  { label: "Correlations", href: "/correlations", icon: GitBranch },
  { label: "Bot", href: "/bot", icon: Bot },
  { label: "Taxes", href: "/taxes", icon: Receipt },
  { label: "Real Estate", href: "/realestate", icon: Home },
  { label: "Copy", href: "/copy", icon: Users },
  { label: "Alpha", href: "/alpha", icon: Shield },
  { label: "Marketplace", href: "/marketplace", icon: Store },
  { label: "Journal", href: "/journal", icon: BookOpen },
  { label: "Calendar", href: "/calendar", icon: Calendar },
  { label: "Alerts", href: "/alerts", icon: Bell },
  { label: "Notifications", href: "/notifications", icon: Bell },
  { label: "Risk", href: "/risk", icon: AlertTriangle },
  { label: "Plan", href: "/plan", icon: Calculator },
];

const bottomNav: NavItem[] = [
  { label: "Settings", href: "/settings", icon: Settings },
];

function NavLink({
  item,
  expanded,
  active,
}: {
  item: NavItem;
  expanded: boolean;
  active: boolean;
}) {
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      className={clsx(
        "flex items-center gap-3 px-3 py-2 rounded-button transition-colors duration-150",
        "hover:bg-bg-elevated",
        active
          ? "bg-bg-elevated text-text-primary"
          : "text-text-secondary hover:text-text-primary"
      )}
      title={!expanded ? item.label : undefined}
    >
      <Icon size={18} strokeWidth={1.5} className="shrink-0" />
      {expanded && (
        <span className="text-sm font-body truncate">{item.label}</span>
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const expanded = useAppStore((s) => s.sidebarExpanded);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);

  return (
    <aside
      className={clsx(
        "hidden lg:flex flex-col h-screen sticky top-0 border-r border-border bg-bg-primary transition-all duration-200",
        expanded ? "w-56" : "w-16"
      )}
    >
      {/* Logo */}
      <div className="flex items-center h-14 px-4 border-b border-border">
        {expanded ? (
          <span className="font-heading text-lg font-semibold tracking-tight text-text-primary">
            LUMARE
          </span>
        ) : (
          <span className="font-heading text-lg font-bold text-text-primary mx-auto">
            L
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto scrollbar-thin">
        {expanded && (
          <p className="px-3 py-1 text-[10px] font-mono text-text-tertiary uppercase tracking-wider">
            Trading
          </p>
        )}
        {primaryNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            expanded={expanded}
            active={pathname === item.href}
          />
        ))}

        <div className="my-2 border-t border-border" />

        {expanded && (
          <p className="px-3 py-1 text-[10px] font-mono text-text-tertiary uppercase tracking-wider">
            Research
          </p>
        )}
        {secondaryNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            expanded={expanded}
            active={pathname === item.href}
          />
        ))}

        <div className="my-2 border-t border-border" />

        {expanded && (
          <p className="px-3 py-1 text-[10px] font-mono text-text-tertiary uppercase tracking-wider">
            Tools
          </p>
        )}
        {tertiaryNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            expanded={expanded}
            active={pathname === item.href}
          />
        ))}
      </nav>

      {/* Bottom section */}
      <div className="px-2 py-3 border-t border-border space-y-0.5">
        {bottomNav.map((item) => (
          <NavLink
            key={item.href}
            item={item}
            expanded={expanded}
            active={pathname === item.href}
          />
        ))}

        {/* Toggle button */}
        <button
          onClick={toggleSidebar}
          className="flex items-center gap-3 px-3 py-2 w-full rounded-button text-text-tertiary hover:text-text-secondary hover:bg-bg-elevated transition-colors duration-150"
        >
          {expanded ? (
            <ChevronLeft size={18} strokeWidth={1.5} />
          ) : (
            <ChevronRight size={18} strokeWidth={1.5} />
          )}
          {expanded && <span className="text-sm">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
