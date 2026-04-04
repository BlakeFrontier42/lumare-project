"use client";

import { useEffect } from "react";

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    // Hide sidebar and mobile nav on login page
    const sidebar = document.querySelector("aside");
    const mobileNav = document.querySelector("nav.fixed");
    const main = document.querySelector("main");
    if (sidebar) (sidebar as HTMLElement).style.display = "none";
    if (mobileNav) (mobileNav as HTMLElement).style.display = "none";
    if (main) (main as HTMLElement).style.paddingBottom = "0";
    return () => {
      if (sidebar) (sidebar as HTMLElement).style.display = "";
      if (mobileNav) (mobileNav as HTMLElement).style.display = "";
      if (main) (main as HTMLElement).style.paddingBottom = "";
    };
  }, []);

  return <>{children}</>;
}
