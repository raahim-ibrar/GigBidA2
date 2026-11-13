"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/accounts";
import type { components } from "@/lib/api/schema";

type Costs = components["schemas"]["CostSummary"];

export function formatUsd(value: number | null | undefined) {
  if (value == null) return "Unknown";
  if (value > 0 && value < 0.00000001) return "<$0.00000001";
  return `$${value.toFixed(8).replace(/\.?0+$/, "") || "0"}`;
}

export function CostReport({ costs }: { costs: Costs }) {
  return <section className="card draft-panel"><h2>Inference cost estimate</h2>
    <p><strong>{formatUsd(costs.estimated_usd)}</strong> · {costs.complete ? "Recorded usage fully priced" : "Partial or unavailable estimate"}</p>
    <p className="muted">{costs.basis}</p>
    <p>{costs.calls} recorded attempts · {costs.unknown_cost_calls} unpriced attempts · {costs.unaccounted_tokens.toLocaleString()} tokens reserved or not matched to measured usage.</p>
    <p>Recorded API charges: {formatUsd(costs.actual_api_usd)}. Hosted billing is not verified against an invoice.</p>
    {!!costs.groups.length && <div className="table-scroll" tabIndex={0} role="region" aria-label="Inference cost breakdown"><table><thead><tr><th scope="col">Provider / model</th><th scope="col">Role</th><th scope="col">Attempts</th><th scope="col">Input tokens</th><th scope="col">Output tokens</th><th scope="col">Estimated USD</th></tr></thead><tbody>{costs.groups.map(row => <tr key={`${row.provider}:${row.model}:${row.role}`}><th scope="row">{row.provider}<br /><small>{row.model}</small></th><td>{row.role}</td><td>{row.calls}</td><td>{row.input_tokens.toLocaleString()}</td><td>{row.output_tokens.toLocaleString()}</td><td>{formatUsd(row.estimated_usd)}{row.unknown_cost_calls > 0 && " · partial"}</td></tr>)}</tbody></table></div>}
  </section>;
}

export function RunCostReport({ runId, revision }: { runId: string; revision: string }) {
  const [data, setData] = useState<Costs | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setData(null); setError(false);
    void apiRequest<Costs>(`/runs/${encodeURIComponent(runId)}/cost`)
      .then(value => { if (active) setData(value); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [runId, revision]);
  return data ? <CostReport costs={data} /> : error ? <p role="status">Cost report unavailable.</p> : null;
}
