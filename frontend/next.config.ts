import type { NextConfig } from "next";

// Two modes, because rewrites and `output: "export"` are mutually exclusive
// (see node_modules/next/dist/docs/01-app/02-guides/static-exports.md):
//
//   next dev   → a Node dev server on :3000 that proxies /api to the Python
//                service, so the UI can be iterated on with hot reload.
//   next build → a static export in `out/`, which FastAPI serves itself.
//                One process, one port, no Node at runtime: `drscreen web`
//                is the whole app. The UI is entirely client-rendered
//                against the JSON API, so it needs no server of its own.
//
// Either way the UI and API share an origin, so the httpOnly session cookie
// works with no CORS configuration.
const isDev = process.env.NODE_ENV === "development";
const API_ORIGIN = process.env.DRS_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = isDev
  ? {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
      },
    }
  : {
      output: "export",
      // Emits out/dashboard/index.html rather than out/dashboard.html, which
      // is what Starlette's StaticFiles(html=True) resolves /dashboard to.
      trailingSlash: true,
      images: { unoptimized: true },
    };

export default nextConfig;
