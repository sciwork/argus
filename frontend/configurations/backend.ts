// In production this app is served by the same FastAPI process as the
// backend, at the same origin — relative paths just work. In local dev,
// `next dev` (:3000) and `uvicorn` (:8000) are different origins, and the
// dev-only proxy in next.config.ts only rewrites `/dashboard/api/*` data
// calls, not full-page navigations. Auth routes (`/dashboard/login`,
// `/dashboard/logout`, `/dashboard/oauth/callback`) only exist on the
// backend, so full-page navigations to them need to target it explicitly
// during dev. `process.env.NODE_ENV` is inlined by Next.js at build time
// ("development" for `next dev`, "production" for the static export
// build), so this has zero runtime cost and no effect on production.
export const BACKEND_ORIGIN =
  process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
