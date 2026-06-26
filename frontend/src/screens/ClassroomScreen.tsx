import { LectureViewer } from "./LectureViewer";

interface ClassroomScreenProps {
  readonly lectureChapterId?: string | null;
  readonly personaId?: string;
  /** Lazy-connect: called the first time the student asks a doubt, to spin up
   *  the LiveKit session/room/agent on demand. */
  readonly onRequestDoubtSession?: () => void;
}

export function ClassroomScreen({
  lectureChapterId,
  personaId = "default",
  onRequestDoubtSession,
}: ClassroomScreenProps) {
  if (lectureChapterId) {
    return (
      <LectureViewer
        chapterId={lectureChapterId}
        personaId={personaId}
        onRequestDoubtSession={onRequestDoubtSession}
      />
    );
  }
  return null;
}
