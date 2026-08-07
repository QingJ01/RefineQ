import { notFound } from "next/navigation";

import { LearningRoute } from "@/components/learning-route";
import { parseLearningSection } from "@/lib/learning-routes";


export default async function LearningSectionPage({
  params,
}: {
  params: Promise<{ workspaceId: string; section: string }>;
}) {
  const { workspaceId, section } = await params;
  const parsedSection = parseLearningSection(section);
  if (!parsedSection) notFound();
  return <LearningRoute workspaceId={workspaceId} section={parsedSection} />;
}
