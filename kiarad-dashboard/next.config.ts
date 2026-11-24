import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  experimental: {
    // Low-RAM host: keep the webpack build's peak memory bounded and single-threaded.
    webpackMemoryOptimizations: true,
    cpus: 1,
    workerThreads: false,
    proxyClientMaxBodySize: "12mb",
  },
  allowedDevOrigins: ["127.0.0.1", "kianoushsurf.taile287ae.ts.net", "kiarad.taile287ae.ts.net"],
  async rewrites() {
    const apiOrigin = (process.env.KIARAD_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

    return {
      beforeFiles: [
        { source: "/newdash_online.html", destination: "/management" },
        // Uploaded catalog files are served only by the authenticated backend.
        { source: "/uploads/:path*", destination: `${apiOrigin}/files/:path*` },
        {
          source: "/api/compensation/:path*",
          destination: `${apiOrigin}/api/compensation/:path*`,
        },
        {
          source: "/api/:path*",
          destination: `${apiOrigin}/:path*`,
        },
      ],
    };
  },
  async headers() {
    return [
      {
        // Pages and API calls must always revalidate: a year-long HTML cache
        // left users on a dead old build after every deployment.
        source: "/:path*",
        headers: [{ key: "Cache-Control", value: "no-store, must-revalidate" }],
      },
      {
        // The backend authenticates the request and revalidates the file ETag.
        source: "/api/files/:path*",
        headers: [{ key: "Cache-Control", value: "private, no-cache" }],
      },
      {
        // Immutable build assets are the exception; their names are content-hashed.
        source: "/_next/static/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
    ];
  },
};

export default nextConfig;
