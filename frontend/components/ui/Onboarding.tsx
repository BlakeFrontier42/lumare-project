"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  ArrowLeft,
  X,
  LayoutDashboard,
  CandlestickChart,
  Brain,
  Bot,
  Briefcase,
  Settings,
  CheckCircle2,
  Sparkles,
  Search,
  Globe,
  Filter,
  ArrowLeftRight,
} from "lucide-react";
import { setUserPreference } from "@/lib/api";

// ── Constants ──────────────────────────────────────────────────────────────

const STORAGE_KEY = "lumare_onboarding_complete";

interface OnboardingStep {
  id: string;
  title: string;
  subtitle: string;
  description: string;
  icon: React.ElementType;
  highlight?: string; // CSS selector for spotlight target
  quickLinks?: { label: string; href: string; icon: React.ElementType }[];
}

const STEPS: OnboardingStep[] = [
  {
    id: "welcome",
    title: "Welcome to Lumare",
    subtitle: "Capital Intelligence Platform",
    description:
      "Institutional-grade portfolio intelligence, analysis, and execution — all in one place. Let us show you around.",
    icon: Sparkles,
  },
  {
    id: "dashboard",
    title: "Your Command Center",
    subtitle: "Sidebar Navigation",
    description:
      "The sidebar organizes everything into four sections: Trading for live markets and execution, Research for screening and analysis, Tools for portfolio management and automation, and Wealth for taxes, real estate, and planning.",
    icon: LayoutDashboard,
    highlight: "aside",
  },
  {
    id: "trade",
    title: "Trade with Precision",
    subtitle: "Charts, Signals & Paper Trading",
    description:
      "Full TradingView charting with multi-timeframe analysis, AI-generated signal scores with entry/stop/target levels, and paper trading to validate strategies before going live.",
    icon: CandlestickChart,
  },
  {
    id: "assistant",
    title: "AI at Your Fingertips",
    subtitle: "Command Bar & Voice",
    description:
      "Press Cmd+K (or Ctrl+K) to open the Lumare AI assistant. Ask about any ticker, run backtests, check risk, or get macro analysis. Voice commands are supported — just click the mic.",
    icon: Brain,
  },
  {
    id: "bot",
    title: "Autonomous Execution",
    subtitle: "Trading Bot",
    description:
      "Configure the autonomous trading bot with your risk parameters, strategy rules, and position sizing. It monitors signals 24/7 and executes when conditions align with your playbook.",
    icon: Bot,
  },
  {
    id: "portfolio",
    title: "Unified Wealth View",
    subtitle: "Portfolio Management",
    description:
      "Track your entire net worth across crypto, equities, real estate, and alternative assets. See correlations, tax implications, and performance attribution in a single dashboard.",
    icon: Briefcase,
  },
  {
    id: "complete",
    title: "You're All Set",
    subtitle: "Start Exploring",
    description:
      "You're ready to go. Jump into any section below, or explore at your own pace. You can always re-run this tour from Settings.",
    icon: CheckCircle2,
    quickLinks: [
      { label: "Trade", href: "/trade", icon: ArrowLeftRight },
      { label: "Bot", href: "/bot", icon: Bot },
      { label: "Portfolio", href: "/portfolio", icon: Briefcase },
      { label: "Settings", href: "/settings", icon: Settings },
    ],
  },
];

// ── Animations ─────────────────────────────────────────────────────────────

const backdropStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 9998,
  backgroundColor: "rgba(0, 0, 0, 0.75)",
  backdropFilter: "blur(4px)",
  transition: "opacity 300ms ease",
};

const cardBaseStyle: React.CSSProperties = {
  position: "fixed",
  zIndex: 9999,
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
  width: "100%",
  maxWidth: 520,
  borderRadius: 16,
  border: "1px solid #1a1a1a",
  backgroundColor: "#0a0a0a",
  boxShadow: "0 32px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.03)",
  overflow: "hidden",
};

// ── Spotlight overlay ──────────────────────────────────────────────────────

function SpotlightOverlay({ selector }: { selector: string }) {
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    const el = document.querySelector(selector);
    if (el) {
      setRect(el.getBoundingClientRect());
    }
    const handleResize = () => {
      const el2 = document.querySelector(selector);
      if (el2) setRect(el2.getBoundingClientRect());
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [selector]);

  if (!rect) return null;

  const pad = 6;
  const x = rect.left - pad;
  const y = rect.top - pad;
  const w = rect.width + pad * 2;
  const h = rect.height + pad * 2;
  const r = 12;

  return (
    <svg
      style={{ position: "fixed", inset: 0, zIndex: 9998, pointerEvents: "none" }}
      width="100%"
      height="100%"
    >
      <defs>
        <mask id="spotlight-mask">
          <rect width="100%" height="100%" fill="white" />
          <rect x={x} y={y} width={w} height={h} rx={r} ry={r} fill="black" />
        </mask>
      </defs>
      <rect
        width="100%"
        height="100%"
        fill="rgba(0,0,0,0.75)"
        mask="url(#spotlight-mask)"
        style={{ backdropFilter: "blur(4px)" }}
      />
      {/* Glow ring around spotlight */}
      <rect
        x={x - 1}
        y={y - 1}
        width={w + 2}
        height={h + 2}
        rx={r + 1}
        ry={r + 1}
        fill="none"
        stroke="#3b82f6"
        strokeWidth={2}
        opacity={0.5}
      />
    </svg>
  );
}

// ── StepDots ───────────────────────────────────────────────────────────────

function StepDots({
  total,
  current,
  onDotClick,
}: {
  total: number;
  current: number;
  onDotClick: (i: number) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      {Array.from({ length: total }).map((_, i) => (
        <button
          key={i}
          onClick={() => onDotClick(i)}
          aria-label={`Go to step ${i + 1}`}
          style={{
            width: i === current ? 24 : 8,
            height: 8,
            borderRadius: 4,
            border: "none",
            cursor: "pointer",
            backgroundColor: i === current ? "#3b82f6" : "#333",
            transition: "all 300ms ease",
          }}
        />
      ))}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export function Onboarding() {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [animDir, setAnimDir] = useState<"next" | "prev">("next");
  const [animating, setAnimating] = useState(false);

  // Check if onboarding should show
  useEffect(() => {
    if (typeof window === "undefined") return;
    const done = localStorage.getItem(STORAGE_KEY);
    if (!done) {
      // Small delay so the main UI renders first
      const timer = setTimeout(() => setVisible(true), 600);
      return () => clearTimeout(timer);
    }
  }, []);

  const completeOnboarding = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "true");
    setVisible(false);
    // Fire-and-forget backend preference save
    setUserPreference("onboarding_complete", true).catch(() => {});
  }, []);

  const animateToStep = useCallback(
    (target: number) => {
      if (animating || target === step) return;
      setAnimDir(target > step ? "next" : "prev");
      setAnimating(true);
      setTimeout(() => {
        setStep(target);
        setTimeout(() => setAnimating(false), 50);
      }, 200);
    },
    [animating, step]
  );

  const goNext = useCallback(() => {
    if (step < STEPS.length - 1) {
      animateToStep(step + 1);
    } else {
      completeOnboarding();
    }
  }, [step, animateToStep, completeOnboarding]);

  const goBack = useCallback(() => {
    if (step > 0) animateToStep(step - 1);
  }, [step, animateToStep]);

  const handleSkip = useCallback(() => {
    completeOnboarding();
  }, [completeOnboarding]);

  const handleQuickLink = useCallback(
    (href: string) => {
      completeOnboarding();
      router.push(href);
    },
    [completeOnboarding, router]
  );

  // Keyboard navigation
  useEffect(() => {
    if (!visible) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "Enter") goNext();
      if (e.key === "ArrowLeft") goBack();
      if (e.key === "Escape") handleSkip();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [visible, goNext, goBack, handleSkip]);

  if (!visible) return null;

  const current = STEPS[step];
  const Icon = current.icon;
  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;

  const contentTransform = animating
    ? animDir === "next"
      ? "translateX(-24px)"
      : "translateX(24px)"
    : "translateX(0)";
  const contentOpacity = animating ? 0 : 1;

  return (
    <>
      {/* Backdrop — use spotlight for highlight steps, plain backdrop otherwise */}
      {current.highlight ? (
        <SpotlightOverlay selector={current.highlight} />
      ) : (
        <div style={backdropStyle} onClick={handleSkip} />
      )}

      {/* Card */}
      <div style={cardBaseStyle}>
        {/* Top accent bar */}
        <div
          style={{
            height: 3,
            background: `linear-gradient(90deg, #3b82f6 ${((step + 1) / STEPS.length) * 100}%, #1a1a1a ${((step + 1) / STEPS.length) * 100}%)`,
            transition: "background 400ms ease",
          }}
        />

        {/* Skip button */}
        {!isLast && (
          <button
            onClick={handleSkip}
            style={{
              position: "absolute",
              top: 16,
              right: 16,
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#555",
              padding: 4,
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "color 200ms",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#888")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#555")}
            aria-label="Skip onboarding"
          >
            <X size={18} />
          </button>
        )}

        {/* Content */}
        <div
          style={{
            padding: "40px 36px 24px",
            transition: "opacity 200ms ease, transform 200ms ease",
            opacity: contentOpacity,
            transform: contentTransform,
          }}
        >
          {/* Icon */}
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              backgroundColor: "rgba(59, 130, 246, 0.1)",
              border: "1px solid rgba(59, 130, 246, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 24,
            }}
          >
            <Icon size={28} color="#3b82f6" strokeWidth={1.5} />
          </div>

          {/* Title */}
          <h2
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: "#fff",
              margin: 0,
              lineHeight: 1.2,
              fontFamily: "var(--font-space-grotesk), sans-serif",
            }}
          >
            {current.title}
          </h2>

          {/* Subtitle */}
          <p
            style={{
              fontSize: 13,
              color: "#3b82f6",
              margin: "6px 0 0",
              fontWeight: 600,
              letterSpacing: "0.02em",
              textTransform: "uppercase",
              fontFamily: "var(--font-space-mono), monospace",
            }}
          >
            {current.subtitle}
          </p>

          {/* Description */}
          <p
            style={{
              fontSize: 14,
              color: "#888",
              margin: "16px 0 0",
              lineHeight: 1.7,
            }}
          >
            {current.description}
          </p>

          {/* Quick links on completion step */}
          {current.quickLinks && (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 10,
                marginTop: 24,
              }}
            >
              {current.quickLinks.map((link) => {
                const LinkIcon = link.icon;
                return (
                  <button
                    key={link.href}
                    onClick={() => handleQuickLink(link.href)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "12px 16px",
                      borderRadius: 10,
                      border: "1px solid #1a1a1a",
                      backgroundColor: "#111",
                      color: "#ccc",
                      cursor: "pointer",
                      fontSize: 13,
                      fontWeight: 500,
                      transition: "all 200ms ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "#3b82f6";
                      e.currentTarget.style.color = "#fff";
                      e.currentTarget.style.backgroundColor = "#0f1629";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "#1a1a1a";
                      e.currentTarget.style.color = "#ccc";
                      e.currentTarget.style.backgroundColor = "#111";
                    }}
                  >
                    <LinkIcon size={16} strokeWidth={1.5} />
                    {link.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 36px 28px",
          }}
        >
          {/* Dots */}
          <StepDots
            total={STEPS.length}
            current={step}
            onDotClick={animateToStep}
          />

          {/* Buttons */}
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {!isFirst && (
              <button
                onClick={goBack}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "8px 14px",
                  borderRadius: 8,
                  border: "1px solid #1a1a1a",
                  backgroundColor: "transparent",
                  color: "#888",
                  cursor: "pointer",
                  fontSize: 13,
                  fontWeight: 500,
                  transition: "all 200ms",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "#333";
                  e.currentTarget.style.color = "#ccc";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "#1a1a1a";
                  e.currentTarget.style.color = "#888";
                }}
              >
                <ArrowLeft size={14} />
                Back
              </button>
            )}

            <button
              onClick={goNext}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 20px",
                borderRadius: 8,
                border: "none",
                backgroundColor: "#3b82f6",
                color: "#fff",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                transition: "all 200ms",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor = "#2563eb";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = "#3b82f6";
              }}
            >
              {isFirst
                ? "Get Started"
                : isLast
                  ? "Finish"
                  : "Next"}
              {!isLast && <ArrowRight size={14} />}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
