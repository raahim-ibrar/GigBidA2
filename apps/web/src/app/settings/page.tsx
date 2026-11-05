import { ProfileForm } from "@/components/ProfileForm";
import { MemorySettings } from "@/components/MemorySettings";

export default function Page() {
  return <><p className="eyebrow">GigBid / Workspace</p><h1>Settings</h1><ProfileForm />
    <MemorySettings /><p className="notice">Connected marketplaces and autonomy controls are still in development.</p></>;
}
