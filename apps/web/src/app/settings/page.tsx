import { ProfileForm } from "@/components/ProfileForm";
import { MemorySettings } from "@/components/MemorySettings";
import { CalendarSettings } from "@/components/CalendarSettings";
import { SearchScheduleSettings } from "@/components/SearchScheduleSettings";
import { MarketplacePanel } from "@/components/MarketplacePanel";

export default function Page() {
  return (
    <>
      <p className="eyebrow">GigBid / Workspace</p>
      <h1>Settings</h1>
      <div className="settings-stack">
        <ProfileForm />
        <MarketplacePanel />
        <SearchScheduleSettings />
        <CalendarSettings />
        <MemorySettings />
        <p className="notice">Live Upwork connections remain unconfigured. Simulator actions require approval.</p>
      </div>
    </>
  );
}
