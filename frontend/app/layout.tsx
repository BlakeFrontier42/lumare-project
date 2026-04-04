import type { Metadata } from "next";
import { Inter, Space_Grotesk, Space_Mono } from "next/font/google";
import { Sidebar } from "@/components/layout/Sidebar";
import { MobileNav } from "@/components/layout/MobileNav";
import { CommandBar } from "@/components/ui/CommandBar";
import { NotificationToast } from "@/components/ui/NotificationToast";
import { Onboarding } from "@/components/ui/Onboarding";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { AuthGuard } from "@/components/auth/AuthGuard";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

const spaceMono = Space_Mono({
  subsets: ["latin"],
  weight: ["400", "700"],
  variable: "--font-space-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Lumare | Capital Intelligence Platform",
  description:
    "Institutional-grade portfolio intelligence, analysis, and execution.",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${spaceGrotesk.variable} ${spaceMono.variable}`}
    >
      <body className="bg-bg-primary text-text-primary font-body antialiased">
        <AuthGuard>
          {/* Desktop layout: sidebar + main */}
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 min-w-0 pb-20 lg:pb-0">
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </main>
          </div>

          {/* Mobile bottom nav */}
          <MobileNav />

          {/* AI Command Bar — Cmd+K */}
          <CommandBar />

          {/* Real-time trade notifications */}
          <NotificationToast />

          {/* First-time user onboarding walkthrough */}
          <Onboarding />
        </AuthGuard>
      </body>
    </html>
  );
}
