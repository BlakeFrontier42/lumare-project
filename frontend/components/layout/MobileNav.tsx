"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import {
  LayoutDashboard,
  Search,
  Globe,
  ArrowLeftRight,
  User,
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
  { label: "Profile", href: "/profile", icon: User },
];

export function MobileNav() {
  const pathname = usePathname();

  return (
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
      </div>
    </nav>
  );
}
