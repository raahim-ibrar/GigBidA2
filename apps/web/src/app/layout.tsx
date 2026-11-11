import type { Metadata } from "next";
import Link from "next/link";
import { AccountMenu } from "@/components/AccountMenu";
import { MarketplaceBanner } from "@/components/MarketplacePanel";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "GigBid | Freelancer workspace",
  description: "AI-4016 freelancer copilot",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        <div className="frame">
          <Sidebar />
          <div className="content-shell">
            <header className="topbar">
              <span className="topbar-context">
                Workspace <span>/</span> GigBid
              </span>
              <div className="topbar-actions">
                <Link className="setup-link" href="/onboarding">
                  Quick setup
                </Link>
                <AccountMenu />
              </div>
            </header>
            <main id="main">
              <MarketplaceBanner />
              {children}
            </main>
            <footer className="app-footer">
              <span>GigBid · Your experience. Your voice.</span>
              <span>Human approval, always.</span>
            </footer>
          </div>
        </div>
      </body>
    </html>
  );
}
