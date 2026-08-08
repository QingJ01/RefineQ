import { notFound } from "next/navigation";

import { parseLearningSection } from "@/lib/learning-routes";


export default async function LearningSectionPage({
  params,
}: {
  params: Promise<{ workspaceId: string; section: string }>;
}) {
  const { section } = await params;
  const parsedSection = parseLearningSection(section);
  if (!parsedSection) notFound();
  return null;
}
