"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getAccount, signOut, type Account } from "@/lib/api/accounts";

export function AccountMenu() {
  const [user, setUser] = useState<Account | null>(null);
  const [error, setError] = useState("");
  const router = useRouter();
  useEffect(() => {
    let active = true;
    const refresh = () => getAccount().then(value => { if (active) setUser(value); }).catch(() => { if (active) setUser(null); });
    refresh(); window.addEventListener("gigbid-account-changed", refresh);
    return () => { active = false; window.removeEventListener("gigbid-account-changed", refresh); };
  }, []);

  if (!user) return <Link href="/sign-in">Sign in</Link>;
  return <div className="account-menu"><Link href="/settings">My account</Link>
    <button className="text-button" onClick={async () => {
      try { await signOut(user.csrf_token); setUser(null); router.push("/sign-in"); }
      catch { setError("Sign-out failed. Try again."); }
    }}>Sign out</button>{error && <span role="alert">{error}</span>}</div>;
}
