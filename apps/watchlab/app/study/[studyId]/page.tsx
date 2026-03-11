import StudyClient from './study-client';

export default async function StudyPage({
  params
}: {
  params: Promise<{ studyId: string }>;
}) {
  const { studyId } = await params;
  return <StudyClient studyId={studyId} />;
}
