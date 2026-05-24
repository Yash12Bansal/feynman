import { useCallback } from "react";
import { WhiteboardScene } from "../engine/whiteboard/WhiteboardScene";
import {
  useCreateSyncManager,
  SyncManagerContext,
} from "../engine/useSyncManager";
import { useVisualChannel } from "../livekit/useVisualChannel";
import { useAgentTranscription } from "../livekit/useAgentTranscription";
import { SplitBoard } from "../engine/whiteboard/split/SplitBoard";
import { useSplitBoardState } from "../engine/whiteboard/split/useSplitBoardState";
import { config } from "../lib/config";
import { LectureViewer } from "./LectureViewer";

interface ClassroomScreenProps {
  readonly lectureChapterId?: string | null;
}

export function ClassroomScreen({ lectureChapterId }: ClassroomScreenProps) {
  // When the session is bound to a precomputed lecture chapter, render the
  // immersive viewer. The legacy live-agent path is preserved for non-lecture
  // sessions (existing topic/subject teaching).
  if (lectureChapterId) {
    return <LectureViewer chapterId={lectureChapterId} />;
  }

  return <LiveAgentClassroom />;
}

function LiveAgentClassroom() {
  const {
    activeInstructions,
    activeWalks,
    activeBoardId,
    activeBoardMeta,
    pendingTransition,
    cameraState,
    pendingSlide,
    clearTransition,
    getBoardInstructions,
  } = useVisualChannel();
  const syncManager = useCreateSyncManager();
  const handleWord = useCallback(
    (word: string) => syncManager.onWord(word),
    [syncManager],
  );
  useAgentTranscription(handleWord);

  const { slide, notebook } = useSplitBoardState(
    activeInstructions,
    pendingSlide[activeBoardId],
  );

  return (
    <SyncManagerContext.Provider value={syncManager}>
      {config.splitBoardEnabled ? (
        <SplitBoard slide={slide} notebook={notebook} mode="split" />
      ) : (
        <WhiteboardScene
          instructions={activeInstructions}
          walks={activeWalks}
          activeBoardId={activeBoardId}
          activeBoardMeta={activeBoardMeta}
          pendingTransition={pendingTransition}
          cameraState={cameraState}
          onTransitionComplete={clearTransition}
          getBoardInstructions={getBoardInstructions}
        />
      )}
    </SyncManagerContext.Provider>
  );
}
