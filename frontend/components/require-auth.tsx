"use client";

import { useAuth } from "@/contexts/auth-context";

/**
 * Gates its children behind the shared auth state (see AuthProvider) —
 * renders nothing while loading or unauthenticated (a redirect to login is
 * already in flight), an error message on failure, and the children once
 * authenticated. Centralizes what each page previously checked for itself.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const auth = useAuth();

  if (auth.status === "loading") {
    return null;
  }
  if (auth.status === "error") {
    return (
      <p className="text-base text-destructive">
        Failed to load: {auth.message}
      </p>
    );
  }
  if (auth.status !== "authenticated") {
    return null;
  }

  return <>{children}</>;
}
