import { LectureViewer } from "./LectureViewer";

interface ClassroomScreenProps {
  readonly lectureChapterId?: string | null;
  /** Firebase uid — keys the per-(student, chapter) resume position. */
  readonly studentId?: string | null;
  /** The study session opened on lecture-open — attributes question attempts. */
  readonly studySessionId?: string | null;
  /** Lazy-connect: called the first time the student asks a doubt, to spin up
   *  the LiveKit session/room/agent on demand. */
  readonly onRequestDoubtSession?: () => void;
  /** Called when playback reaches the end of the lecture (marks the study
   *  session complete in the memory layer). */
  readonly onLectureComplete?: () => void;
}

export function ClassroomScreen({
  lectureChapterId,
  studentId,
  studySessionId,
  onRequestDoubtSession,
  onLectureComplete,
}: ClassroomScreenProps) {
  if (lectureChapterId) {
    return (
      <LectureViewer
        chapterId={lectureChapterId}
        studentId={studentId}
        studySessionId={studySessionId}
        onRequestDoubtSession={onRequestDoubtSession}
        onLectureComplete={onLectureComplete}
      />
    );
  }
  return null;
}
