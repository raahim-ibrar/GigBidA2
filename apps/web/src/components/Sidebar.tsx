"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "./Icon";

const links: { href: string; label: string; icon: IconName }[] = [
  { href: "/", label: "Overview", icon: "grid" },
  { href: "/inbox", label: "Job inbox", icon: "inbox" },
  { href: "/portfolio", label: "Portfolio", icon: "folder" },
  { href: "/pipeline", label: "Pipeline", icon: "pipeline" },
  { href: "/messages", label: "Messages", icon: "message" },
  { href: "/runs", label: "Agent runs", icon: "activity" },
  { href: "/analytics", label: "Analytics", icon: "chart" },
  { href: "/settings", label: "Settings", icon: "settings" },
];
export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="sidebar">
      <Link className="brand" href="/" aria-label="GigBid home">
        <span className="brand-symbol">
          <Icon name="spark" size={21} />
        </span>
        GigBid<span className="brand-period">.</span>
      </Link>
      <div className="workspace-label">
        <span className="workspace-avatar">G</span>
        <span>
          Personal workspace<small>Freelancer copilot</small>
        </span>
      </div>
      <p className="nav-caption">WORKSPACE</p>
      <nav aria-label="Main navigation">
        {links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={
              path === link.href ||
              (link.href !== "/" && path.startsWith(link.href + "/"))
                ? "active"
                : ""
            }
            aria-current={path === link.href ? "page" : undefined}
          >
            <Icon name={link.icon} />
            <span>{link.label}</span>
            {path === link.href && <span className="nav-indicator" />}
          </Link>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="review-note">
          <Icon name="shield" size={19} />
          <strong>You have the final say.</strong>
          <p>Every proposal and reply waits for your approval.</p>
        </div>
        <span className="sidebar-footnote">
          <span className="status-dot" /> Built for thoughtful freelancing
        </span>
      </div>
    </aside>
  );
}
