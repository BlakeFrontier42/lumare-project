"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Search,
  Globe,
  ArrowLeftRight,
  MoreHorizontal,
  Briefcase,
  GitBranch,
  LayoutGrid,
  List,
  BookOpen,
  Bell,
  Calendar,
  Settings,
  X,
  Bot,
  Receipt,
  Home,
} from "lucide-react";

interface TabItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

const tabs: TabItem[] = [
  { label: "Home", href: "/", icon: LayoutDashboard },
  { label: "Intel", href: "/intel", icon: Search },
  { label: "Macro", href: "/macro", icon: Globe },
  { label: "Trade", href: "/trade", icon: ArrowLeftRight },
];

const moreLinks: TabItem[] = [
  { label: "Portfolio", href: "/portfolio", icon: Briefcase },
  { label: "Correlations", href: "/correlations", icon: GitBranch },
  { label: "Bot", href: "/bot", icon: Bot },
  { label: "Charts", href: "/charts", icon: LayoutGrid },
  { label: "Watchlist", href: "/watchlist", icon: List },
  { label: "Taxes", href: "/taxes", icon: Receipt },
  { label: "Real Estate", href: "/realestate", icon: Home },
  { label: "Journal", href: "/journal", icon: BookOpen },
  { label: "Alerts", href: "/alerts", icon: Bell },
  { label: "Calendar", href: "/calendar", icon: Calendar },
  { label: "Settings", href: "/settings", icon: Settings },
];

export function MobileNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  const close = useCallback(() => setOpen(false), []);

  // Close sheet on route change
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Prevent body scroll when sheet is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Check if current path matches any "more" link
  const moreActive = moreLinks.some((link) => pathname === link.href);

  return (
    <>
      {/* Slide-up sheet */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-[60]">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
            onClick={close}
          />

          {/* Sheet */}
          <div className="absolute bottom-0 left-0 right-0 bg-bg-primary border-t border-border rounded-t-2xl animate-sheet-up">
            {/* Handle + close */}
            <div className="flex items-center justify-between px-5 pt-3 pb-2">
              <span className="text-xs font-mono text-text-tertiary uppercase tracking-wider">
                More
              </span>
              <button
                onClick={close}
                className="p-1.5 rounded-button text-text-tertiary hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <X size={18} strokeWidth={1.5} />
              </button>
            </div>

            {/* Drag handle */}
            <div className="flex justify-center -mt-1 mb-2">
              <div className="w-10 h-1 rounded-full bg-border" />
            </div>

            {/* Links grid */}
            <div className="grid grid-cols-4 gap-1 px-4 pb-8">
              {moreLinks.map((link) => {
                const Icon = link.icon;
                const active = pathname === link.href;
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    onClick={close}
                    className={clsx(
                      "flex flex-col items-center gap-1.5 py-3 px-1 rounded-lg transition-colors",
                      active
                        ? "bg-bg-elevated text-text-primary"
                        : "text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
                    )}
                  >
                    <Icon size={22} strokeWidth={1.5} />
                    <span className="text-[11px] font-body">{link.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Bottom navigation bar */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-bg-primary border-t border-border">
        <div className="flex items-center justify-around h-16 px-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const active = pathname === tab.href;

            return (
              <Link
                key={tab.href}
                href={tab.href}
                className={clsx(
                  "flex flex-col items-center gap-1 px-3 py-1.5 rounded-button transition-colors",
                  active
                    ? "text-text-primary"
                    : "text-text-tertiary hover:text-text-secondary"
                )}
              >
                <Icon size={20} strokeWidth={1.5} />
                <span className="text-[10px] font-body">{tab.label}</span>
              </Link>
            );
          })}

          {/* More button */}
          <button
            onClick={() => setOpen((prev) => !prev)}
            className={clsx(
              "flex flex-col items-center gap-1 px-3 py-1.5 rounded-button transition-colors",
              open || moreActive
                ? "text-text-primary"
                : "text-text-tertiary hover:text-text-secondary"
            )}
          >
            <MoreHorizontal size={20} strokeWidth={1.5} />
            <span className="text-[10px] font-body">More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
