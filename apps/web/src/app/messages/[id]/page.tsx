import { ConversationDetail } from "@/components/ConversationDetail";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><h1>Client conversation</h1><ConversationDetail id={id} /></>;
}
