import type { NextConfig } from "next";

const isVercel = process.env.VERCEL === "1";
const api = (process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
if (isVercel) {
  const target = new URL(api);
  if (
    !process.env.API_INTERNAL_URL || target.protocol !== "https:" ||
    ["localhost", "127.0.0.1", "::1", "[::1]"].includes(target.hostname) ||
    target.username || target.password || target.search || target.hash || target.pathname !== "/"
  ) {
    throw new Error("Set API_INTERNAL_URL to the deployed HTTPS backend origin before deploying to Vercel.");
  }
}

const config: NextConfig = {
  output: isVercel ? undefined : "standalone",
  poweredByHeader: false,
  allowedDevOrigins: ["127.0.0.1"],
  distDir: process.env.GIGBID_TEST_DIST ?? ".next",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
};
export default config;
