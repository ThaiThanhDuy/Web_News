import type { Metadata } from "next";

import { Dashboard } from "@/components/dashboard/dashboard";

export const metadata: Metadata = {
  title: "Dashboard — Tech Digest",
  robots: { index: false, follow: false },
};

export default function DashboardPage() {
  return <Dashboard />;
}
