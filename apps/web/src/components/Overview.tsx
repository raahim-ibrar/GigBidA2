"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, getAccount } from "@/lib/api/accounts";
import { listJobs, listRuns, type Job, type Run } from "@/lib/api/proposals";
import { Icon } from "./Icon";

export function Overview() {
  const [data, setData] = useState<{ jobs: Job[]; runs: Run[] } | null>(null);
  const [anonymous, setAnonymous] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getAccount()
      .then(() => Promise.all([listJobs(), listRuns()]))
      .then(([jobs, runs]) => {
        if (active) setData({ jobs, runs });
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) setAnonymous(true);
        else
          setError(
            "Workspace activity is unavailable. Try refreshing in a moment.",
          );
      });
    return () => {
      active = false;
    };
  }, []);
  const pending = data?.runs.filter(
    (run) => run.status === "awaiting_approval",
  ).length;
  const completed = data?.runs.filter((run) =>
    ["drafted", "submitted", "sent"].includes(run.status),
  ).length;
  const recent = data?.runs.slice(0, 4) ?? [];
  return (
    <div className="overview">
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR WORK, IN FOCUS</p>
          <h1>
            Workspace overview<span className="title-dot">.</span>
          </h1>
          <p className="muted">
            A little less busywork. A lot more opportunity.
          </p>
        </div>
        <Link className="button-link" href="/inbox">
          <Icon name="plus" size={17} /> Find your next job
        </Link>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <section className="overview-hero">
        <div className="hero-copy">
          <span className="hero-tag">
            <Icon name="spark" size={14} /> YOUR FREELANCE CO-PILOT
          </span>
          <h2>
            Good work deserves
            <br />
            <span>a stronger introduction.</span>
          </h2>
          <p>
            Turn your experience into thoughtful proposals.
            <br className="desktop-break" /> Backed by your portfolio. Approved
            by you.
          </p>
          <div className="hero-actions">
            <Link href="/inbox" className="button-link">
              Explore opportunities <Icon name="arrow" size={17} />
            </Link>
            <Link href="/portfolio" className="quiet-link">
              Build your portfolio <Icon name="arrow" size={16} />
            </Link>
          </div>
        </div>
        <div className="flow-preview" aria-label="Proposal workflow">
          <div className="flow-top">
            <span className="flow-orbit">
              <Icon name="spark" size={18} />
            </span>
            <span>
              From opportunity to introduction
              <small>A considered approach, every time.</small>
            </span>
          </div>
          {[
            {
              title: "Find the fit",
              detail: "Match requirements to your experience",
              icon: "inbox" as const,
            },
            {
              title: "Make it yours",
              detail: "A draft grounded in your actual work",
              icon: "folder" as const,
            },
            {
              title: "You take it from here",
              detail: "Review, refine, then approve",
              icon: "check" as const,
            },
          ].map((step, i) => (
            <div className="flow-step" key={step.title}>
              <span className={`step-icon step-${i}`}>
                <Icon name={step.icon} size={17} />
              </span>
              <div>
                <strong>{step.title}</strong>
                <small>{step.detail}</small>
              </div>
              <span className="step-number">0{i + 1}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="overview-metrics">
        {[
          {
            label: "Saved opportunities",
            value: data?.jobs.length,
            icon: "inbox" as const,
            detail: "Your next projects start here",
            href: "/inbox",
          },
          {
            label: "Waiting for your review",
            value: pending,
            icon: "shield" as const,
            detail: "Your judgment makes the difference",
            href: "/runs",
          },
          {
            label: "Approved drafts & sends",
            value: completed,
            icon: "check" as const,
            detail: "Work you’ve given the green light",
            href: "/pipeline",
          },
        ].map((metric) => (
          <Link className="metric-tile" href={metric.href} key={metric.label}>
            <div className="metric-label">
              <span>{metric.label}</span>
              <Icon name={metric.icon} size={18} />
            </div>
            <strong className="metric-number">
              {metric.value ?? (anonymous ? "—" : "…")}
            </strong>
            <span className="metric-detail">
              {metric.detail}
              <Icon name="arrow" size={14} />
            </span>
          </Link>
        ))}
      </div>
      <div className="overview-bottom">
        <section className="card activity-card">
          <div className="section-heading">
            <h2>Recent activity</h2>
            <Link href="/runs" className="quiet-link">
              View all <Icon name="arrow" size={15} />
            </Link>
          </div>
          {recent.length ? (
            <div>
              {recent.map((run) => (
                <Link
                  className="activity-row"
                  href={`/runs/${run.id}`}
                  key={run.id}
                >
                  <span className="activity-icon">
                    <Icon
                      name={run.kind === "conversation" ? "message" : "folder"}
                      size={18}
                    />
                  </span>
                  <span>
                    <strong>
                      {run.snapshot.conversation_title ??
                        run.snapshot.job?.title ??
                        "Job analysis"}
                    </strong>
                    <small>
                      {new Date(run.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </small>
                  </span>
                  <span
                    className={`status-pill ${run.status === "awaiting_approval" ? "purple" : ""}`}
                  >
                    {run.status.replaceAll("_", " ")}
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <span className="empty-state-icon">
                <Icon name="activity" size={25} />
              </span>
              <h3>A fresh start.</h3>
              <p>
                {anonymous
                  ? "Sign in to see your jobs, drafts and conversations here."
                  : "Your proposals and conversations will appear here as you work."}
              </p>
              <Link href={anonymous ? "/sign-in" : "/inbox"}>
                {anonymous ? "Sign in to your workspace" : "Start with a job"}{" "}
                <Icon name="arrow" size={15} />
              </Link>
            </div>
          )}
        </section>
        <section className="card portfolio-prompt">
          <span className="feature-icon">
            <Icon name="folder" size={22} />
          </span>
          <p className="eyebrow">THE FOUNDATION</p>
          <h2>
            Your best pitch?
            <br />
            The work you’ve done.
          </h2>
          <p className="muted">
            Add case studies, project notes or your CV. Give every experience
            claim a source you can stand behind.
          </p>
          <Link href="/portfolio" className="quiet-link">
            Open your portfolio <Icon name="arrow" size={16} />
          </Link>
          <div className="file-types">
            <span>PDF</span>
            <span>Markdown</span>
            <span>Text</span>
          </div>
        </section>
      </div>
    </div>
  );
}
