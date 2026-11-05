import { ScaffoldScreen } from "@/components/ScaffoldScreen";

export default function Page() {
  return <ScaffoldScreen title="Proposal studio" description="Review an evidence-grounded proposal before approving it." checklist={["Editable draft with claim evidence on hover", "Inline Critic and Compliance feedback", "Dry-run cost preview and durable approve/edit/reject actions"]} />;
}
