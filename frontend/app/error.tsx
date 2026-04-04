"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw, LayoutDashboard } from "lucide-react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[Lumare] Application error:", error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-screen p-6 bg-bg-primary">
      <div className="w-full max-w-md text-center">
        {/* Icon */}
        <div className="flex items-center justify-center w-16 h-16 rounded-full bg-loss/10 mb-6 mx-auto">
          <AlertTriangle className="w-8 h-8 text-loss" />
        </div>

        {/* Heading */}
        <h1 className="text-2xl font-heading font-semibold text-text-primary mb-2">
          Something went wrong
        </h1>
        <p className="text-sm text-text-secondary mb-8 max-w-sm mx-auto">
          An unexpected error occurred while loading this page. Our team has
          been notified.
        </p>

        {/* Error digest */}
        {error.digest && (
          <p className="text-xs text-text-tertiary font-mono mb-6">
            Error ID: {error.digest}
          </p>
        )}

        {/* Actions */}
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="flex items-center gap-2 px-5 py-2.5 bg-white text-black text-sm font-medium rounded-button hover:bg-white/90 transition-colors"
          >
            <RotateCcw className="w-4 h-4" />
            Try Again
          </button>
          <a
            href="/"
            className="flex items-center gap-2 px-5 py-2.5 bg-bg-card border border-border text-text-secondary text-sm font-medium rounded-button hover:text-text-primary hover:border-accent transition-colors"
          >
            <LayoutDashboard className="w-4 h-4" />
            Go to Dashboard
          </a>
        </div>
      </div>
    </div>
  );
}
