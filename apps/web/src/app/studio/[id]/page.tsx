import { RunWorkspace } from "@/components/RunWorkspace";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><p className="eyebrow">Human review</p><h1>Proposal studio</h1><RunWorkspace id={id} /></>;
}
