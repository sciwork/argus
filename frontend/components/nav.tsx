"use client";

import Link from "next/link";
import { BACKEND_ORIGIN } from "@/configurations/backend";
import { useAuth } from "@/contexts/auth-context";

export function Nav() {
  const auth = useAuth();

  return (
    <nav className="flex flex-col gap-2 border-b border-border px-6 py-4 text-sm tablet:flex-row tablet:items-center tablet:gap-6">
      <div className="flex items-center gap-6">
        <Link href="/" className="font-heading text-base font-semibold">
          Argus
        </Link>
        <Link
          href="/webhook-logs"
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          Webhook Logs
        </Link>
      </div>
      <div className="flex min-w-0 items-center gap-2 text-muted-foreground tablet:ml-auto">
        {auth.status === "authenticated" && (
          <>
            <span className="truncate">{auth.user.email}</span>
            <span className="text-border">·</span>
          </>
        )}
        <a
          href={`${BACKEND_ORIGIN}/dashboard/logout`}
          className="shrink-0 transition-colors hover:text-foreground"
        >
          Logout
        </a>
      </div>
    </nav>
  );
}
