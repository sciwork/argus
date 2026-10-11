import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  basePath: "/dashboard",
  trailingSlash: true,
  // next/image's default loader needs a server; serve images as-is instead.
  images: {
    unoptimized: true,
  },
  // `rewrites()` has no effect on `output: "export"` production builds
  // (static export can't proxy at request time) — it only applies to
  // `next dev`, which is exactly where it's needed: `next dev` and
  // `uvicorn` run as separate processes on different ports locally, so
  // without this the browser would see a cross-origin request.
  //
  // `source` is deliberately "/api/:path*/", not "/dashboard/api/:path*":
  //   - `basePath: "/dashboard"` above is auto-prepended to internal
  //     `rewrites()` sources, so writing "/dashboard" again here would
  //     match "/dashboard/dashboard/api/*" and never fire.
  //   - the trailing slash is required because `trailingSlash: true`
  //     redirects "/dashboard/api/me" -> "/dashboard/api/me/" *before*
  //     rewrites are matched; without it, that redirect round-trip lands
  //     on a route with no match and 404s instead of proxying.
  // Verified against a local backend: GET/DELETE and query strings all
  // proxy correctly (via the extra, transparent 308 redirect that
  // `trailingSlash: true` already adds for every route, not just this one).
  async rewrites() {
    return [
      {
        source: "/api/:path*/",
        destination: "http://localhost:8000/dashboard/api/:path*",
      },
    ];
  },
};

export default nextConfig;
