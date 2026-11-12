"use client";
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiRequest } from '@/lib/api/accounts';
import type { components } from '@/lib/api/schema';

export function CheckpointReplay({ runId, csrf }: { runId: string; csrf: string }) {
  const router = useRouter();
  const [items, setItems] = useState<components['schemas']['CheckpointView'][]>([]);
  const [checkpoint, setCheckpoint] = useState('');
  const [node, setNode] = useState<components['schemas']['ReplayRun']['node']>('writer');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true); setError('');
    try { const rows = await apiRequest<components['schemas']['CheckpointView'][]>(`/runs/${encodeURIComponent(runId)}/checkpoints`);
      setItems(rows); setCheckpoint(rows[0]?.checkpoint_id ?? ''); if (!rows.length) setError('No saved checkpoints yet.');
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function replay() {
    setBusy(true); setError('');
    try { const run = await apiRequest<components['schemas']['RunView']>(`/runs/${encodeURIComponent(runId)}/replays`, {
      method: 'POST', headers: { 'X-CSRF-Token': csrf }, body: JSON.stringify({ checkpoint_id: checkpoint, node, idempotency_key: crypto.randomUUID() }),
    }); router.push(`/runs/${run.id}`); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  return <section className="card"><h2>Replay a saved checkpoint</h2>
    <p className="muted">Create a separate run from saved work. The original stays intact, and sending always needs a new approval. Analysis stages rerun together; later stages repeat verification.</p>
    <button className="secondary-button" disabled={busy} onClick={load}>Load checkpoint history</button>
    {error && <p className="error" role="alert">{error}</p>}
    {!!items.length && <><label htmlFor="replay-checkpoint">Saved checkpoint</label><select id="replay-checkpoint" value={checkpoint} onChange={e => setCheckpoint(e.target.value)}>
      {items.map(item => <option key={item.checkpoint_id} value={item.checkpoint_id}>Step {item.step} · {item.next_nodes.join(', ') || 'finished'} · {item.created_at}</option>)}</select>
      <label htmlFor="replay-node">Start again from</label><select id="replay-node" value={node} onChange={e => setNode(e.target.value as typeof node)}>
        {['scout','analyst','risk','matcher','decision','pricing','writer','regenerate','verifier','critic','compliance','preview','approval','execute'].map(name => <option key={name}>{name}</option>)}
      </select><button disabled={busy || !checkpoint} onClick={replay}>{busy ? 'Saving replay…' : 'Create replay run'}</button></>}
  </section>;
}
