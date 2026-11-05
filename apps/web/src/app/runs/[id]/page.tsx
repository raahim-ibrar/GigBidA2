import { RunWorkspace } from "@/components/RunWorkspace";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><p className="eyebrow">Trace</p><h1>Agent run viewer</h1><RunWorkspace id={id} trace /></>;
}
