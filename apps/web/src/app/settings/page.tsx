import { ProfileForm } from "@/components/ProfileForm";
import { MemorySettings } from "@/components/MemorySettings";
import { CalendarSettings } from "@/components/CalendarSettings";
import { SearchScheduleSettings } from "@/components/SearchScheduleSettings";

export default function Page() {
  return <><p className="eyebrow">GigBid / Workspace</p><h1>Settings</h1><ProfileForm />
    <SearchScheduleSettings /><CalendarSettings /><MemorySettings /><p className="notice">Connected marketplaces and autonomy controls are still in development.</p></>;
}
