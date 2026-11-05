import { JobDetail } from "@/components/JobDetail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><p className="eyebrow">Opportunity</p><h1>Job detail</h1><JobDetail id={id} /></>;
}
