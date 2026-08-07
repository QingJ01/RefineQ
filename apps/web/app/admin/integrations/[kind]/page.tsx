import { notFound } from "next/navigation";

import { AdminRoute } from "@/components/admin-route";
import { parseIntegrationKind } from "@/lib/admin-routes";


export default async function AdminIntegrationPage({
  params,
}: {
  params: Promise<{ kind: string }>;
}) {
  const { kind } = await params;
  const activeKind = parseIntegrationKind(kind);
  if (!activeKind) notFound();
  return <AdminRoute activeKind={activeKind} />;
}
