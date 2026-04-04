"use client";

import React from "react";
import { AlertTriangle, ChevronDown, ChevronUp, RotateCcw, Home } from "lucide-react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  showDetails: boolean;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null, showDetails: false };
  }

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, errorInfo);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, showDetails: false });
  };

  toggleDetails = () => {
    this.setState((prev) => ({ showDetails: !prev.showDetails }));
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex items-center justify-center min-h-[400px] p-6">
          <div className="w-full max-w-lg bg-bg-card border border-border rounded-card p-8">
            {/* Icon */}
            <div className="flex items-center justify-center w-14 h-14 rounded-full bg-loss/10 mb-6 mx-auto">
              <AlertTriangle className="w-7 h-7 text-loss" />
            </div>

            {/* Message */}
            <h2 className="text-xl font-heading font-semibold text-text-primary text-center mb-2">
              Something went wrong
            </h2>
            <p className="text-sm text-text-secondary text-center mb-6">
              An unexpected error occurred. You can try again or return to the
              dashboard.
            </p>

            {/* Error details collapsible */}
            {this.state.error && (
              <div className="mb-6">
                <button
                  onClick={this.toggleDetails}
                  className="flex items-center gap-2 text-xs text-text-tertiary hover:text-text-secondary transition-colors w-full"
                >
                  {this.state.showDetails ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                  <span>Error details</span>
                </button>
                {this.state.showDetails && (
                  <pre className="mt-3 p-4 bg-bg-primary border border-border rounded-chip text-xs text-text-secondary font-mono overflow-auto max-h-40 leading-relaxed">
                    {this.state.error.message}
                    {this.state.error.stack &&
                      "\n\n" + this.state.error.stack}
                  </pre>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-3">
              <button
                onClick={this.handleReset}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-white text-black text-sm font-medium rounded-button hover:bg-white/90 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
                Try Again
              </button>
              <a
                href="/"
                className="flex items-center justify-center gap-2 px-4 py-2.5 bg-bg-elevated border border-border text-text-secondary text-sm font-medium rounded-button hover:text-text-primary hover:border-accent transition-colors"
              >
                <Home className="w-4 h-4" />
                Go Home
              </a>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
