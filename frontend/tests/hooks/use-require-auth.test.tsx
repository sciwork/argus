import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as authApi from "@/apis/auth";
import { useRequireAuth } from "@/hooks/use-require-auth";

describe("useRequireAuth", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    // @ts-expect-error -- jsdom's location isn't reassignable by default; tests override it directly
    delete window.location;
    // @ts-expect-error -- window.location's setter type is narrower than Location in this TS/lib config
    window.location = { href: "" } as Location;
  });

  it("returns the authenticated user when the session is valid", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue({
      email: "chester@example.com",
    });

    const { result } = renderHook(() => useRequireAuth());

    await waitFor(() =>
      expect(result.current).toEqual({
        status: "authenticated",
        user: { email: "chester@example.com" },
      }),
    );
  });

  it("navigates to /dashboard/login when there is no session", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockResolvedValue(null);
    // @ts-expect-error -- window.location's setter type is narrower than Location in this TS/lib config
    window.location = { href: "" } as Location;

    renderHook(() => useRequireAuth());

    // In production this is a bare "/dashboard/login" (same-origin); in dev
    // it's prefixed with the backend's own origin (see
    // configurations/backend.ts) since next dev/uvicorn are different
    // origins — assert on the path, not the exact origin prefix, so this
    // test doesn't depend on which environment it happens to run under.
    await waitFor(() =>
      expect(window.location.href).toMatch(/\/dashboard\/login$/),
    );
  });

  it("returns an error state when getCurrentUser rejects", async () => {
    vi.spyOn(authApi, "getCurrentUser").mockRejectedValue(
      new Error("network down"),
    );

    const { result } = renderHook(() => useRequireAuth());

    await waitFor(() =>
      expect(result.current).toEqual({
        status: "error",
        message: "network down",
      }),
    );
  });
});
