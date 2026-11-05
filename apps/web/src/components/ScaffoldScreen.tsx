export function ScaffoldScreen({ title, description, checklist }: { title: string; description: string; checklist: string[] }) {
  return <><p className="eyebrow">GigBid / Build workspace</p><h1>{title}</h1><p className="muted">{description}</p>
    <p className="notice" role="status">This is a route shell. Its product behavior is not implemented yet.</p>
    <section className="card"><h2>Implementation checklist</h2><ul>{checklist.map(item => <li key={item}>{item}</li>)}</ul></section>
  </>;
}
