import { LectureViewer } from "./LectureViewer";

interface ClassroomScreenProps {
  readonly lectureChapterId?: string | null;
  /** Lazy-connect: called the first time the student asks a doubt, to spin up
   *  the LiveKit session/room/agent on demand. */
  readonly onRequestDoubtSession?: () => void;
}

export function ClassroomScreen({
  lectureChapterId,
  onRequestDoubtSession,
}: ClassroomScreenProps) {
  if (lectureChapterId) {
    return (
      <LectureViewer
        chapterId={lectureChapterId}
        onRequestDoubtSession={onRequestDoubtSession}
      />
    );
  }
  return null;
}
