"use client";

/**
 * AuthGuard — wraps authenticated routes.
 * Auth is currently disabled for local development.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
