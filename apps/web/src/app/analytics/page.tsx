import { ScaffoldScreen } from "@/components/ScaffoldScreen";

export default function Page() {
  return <ScaffoldScreen title="Analytics" description="Measure whether proposals lead to useful outcomes." checklist={["Reply and hire rates by category", "Connects spend versus outcomes", "Real cost, latency and rejection reasons"]} />;
}
