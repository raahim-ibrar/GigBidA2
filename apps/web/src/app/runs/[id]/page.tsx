import { ScaffoldScreen } from "@/components/ScaffoldScreen";

export default function Page() {
  return <ScaffoldScreen title="Agent run viewer" description="Follow the work each agent performs on a job or conversation." checklist={["SSE node progress with reconnect", "Pending approvals survive page refresh", "Link each run to its full trace"]} />;
}
