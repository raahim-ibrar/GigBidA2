import type { Metadata } from "next";
import Link from "next/link";
import { AccountMenu } from "@/components/AccountMenu";
import "./globals.css";

export const metadata: Metadata = { title: "GigBid | Freelancer workspace", description: "AI-4016 freelancer copilot" };
const links = [["/inbox", "Job inbox"], ["/portfolio", "Portfolio"],
  ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/runs", "Agent runs"],
  ["/analytics", "Analytics"], ["/settings", "Settings"]];

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>
    <a className="skip" href="#main">Skip to content</a>
    <header><Link className="brand" href="/">G<span>igBid</span></Link><span className="badge">In development</span>
      <Link href="/onboarding">Onboarding</Link><AccountMenu /></header>
    <div className="frame"><nav aria-label="Main navigation">{links.map(([href, label]) =>
      <Link key={href} href={href}>{label}</Link>)}</nav><main id="main">{children}</main></div>
  </body></html>;
}
