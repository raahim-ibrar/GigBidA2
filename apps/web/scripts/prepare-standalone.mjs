import { cp, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

if (process.env.VERCEL !== "1") {
  const dist = process.env.GIGBID_TEST_DIST ?? ".next";
  const standalone = `${dist}/standalone`;
  await mkdir(`${standalone}/${dist}`, { recursive: true });
  await cp(`${dist}/static`, `${standalone}/${dist}/static`, { recursive: true });
  if (existsSync("public")) {
    await cp("public", `${standalone}/public`, { recursive: true });
  }
}
