/**
 * Immersive lecture viewer mounted by ClassroomScreen when the session is
 * bound to a precomputed chapter. Consumes the same `useExtractionPlayback`
 * hook as the dev playground, but with `autoStart: true` and zero control
 * surface — the student watches a lecture, they don't operate a player.
 *
 * Future Ask Feynman affordance (Phase 3+) mounts on top of this view as a
 * floating button overlay; the SatisfactionPrompt (Phase 5+) renders as a
 * modal layer when a doubt resolution completes.
 */

import { useEffect, useState } from "react";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
import {
  useExtractionPlayback,
  type ChapterPayload,
} from "../hooks/useExtractionPlayback";

interface LectureViewerProps {
  readonly chapterId: string;
}

export function LectureViewer({ chapterId }: LectureViewerProps) {
  const [chapter, setChapter] = useState<ChapterPayload | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard fetch-on-prop-change pattern.
    setChapter(null);
    setFetchError(null);
    fetch(`/lecture-api/chapter/${encodeURIComponent(chapterId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: ChapterPayload) => setChapter(data))
      .catch((e: Error) => setFetchError(e.message));
  }, [chapterId]);

  const { slide, notebook, setAudioElement } = useExtractionPlayback({
    chapter,
    autoStart: true,
  });

  if (fetchError) {
    return (
      <ImmersiveShell>
        <div style={statusTextStyle}>Failed to load lecture: {fetchError}</div>
      </ImmersiveShell>
    );
  }

  if (!chapter) {
    return (
      <ImmersiveShell>
        <div style={statusTextStyle}>Preparing lecture…</div>
      </ImmersiveShell>
    );
  }

  return (
    <ImmersiveShell>
      <SplitBoard
        slide={slide}
        notebook={notebook}
        mode="split"
        notebookTitle={chapter.title}
      />
      <audio ref={setAudioElement} preload="auto" />
    </ImmersiveShell>
  );
}

interface ImmersiveShellProps {
  readonly children: React.ReactNode;
}

function ImmersiveShell({ children }: ImmersiveShellProps) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#0a0a0a",
        color: "#fafafa",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {children}
    </div>
  );
}

const statusTextStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#6b7280",
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontSize: "0.95rem",
  letterSpacing: "0.05em",
};
