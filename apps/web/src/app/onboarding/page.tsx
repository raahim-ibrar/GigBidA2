import { ProfileForm } from "@/components/ProfileForm";
import Link from "next/link";

export default function Page() {
  return <><p className="eyebrow">GigBid / Get started</p><h1>Set up your profile</h1>
    <p className="muted">Choose your rate floor, Connects budget and saved searches.</p><ProfileForm onboarding />
    <p>Next, <Link href="/portfolio">upload your portfolio evidence</Link> so GigBid can support its recommendations.</p></>;
}
