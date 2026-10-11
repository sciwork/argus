"use client";

import { createContext, useContext } from "react";
import { type AuthState, useRequireAuth } from "@/hooks/use-require-auth";

const AuthContext = createContext<AuthState | null>(null);

/**
 * Runs the auth check exactly once and shares the result via context, so
 * <Nav> (always visible) and the current page's content (gated behind
 * "authenticated" — see <RequireAuth>) don't each fetch /dashboard/api/me
 * independently.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useRequireAuth();
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
