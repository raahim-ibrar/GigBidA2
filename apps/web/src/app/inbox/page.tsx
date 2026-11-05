import { ScaffoldScreen } from "@/components/ScaffoldScreen";

export default function Page() {
  return <ScaffoldScreen title="Job inbox" description="Review discovered opportunities and decide which jobs deserve attention." checklist={["Rank by fit with risk badges", "Show recommended action, price and Connects cost", "Filter, skip and open a job"]} />;
}
