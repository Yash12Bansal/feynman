import { LectureViewer } from "./LectureViewer";

interface ClassroomScreenProps {
  readonly lectureChapterId?: string | null;
}

export function ClassroomScreen({ lectureChapterId }: ClassroomScreenProps) {
  if (lectureChapterId) {
    return <LectureViewer chapterId={lectureChapterId} />;
  }
  return null;
}
