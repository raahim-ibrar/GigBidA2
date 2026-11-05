import { ScaffoldScreen } from "@/components/ScaffoldScreen";

export default function Page() {
  return <ScaffoldScreen title="Messages" description="Review client replies and approve suggested responses." checklist={["Client threads and intent labels", "Suggested reply and interview slots", "Human approval before any message is sent"]} />;
}
