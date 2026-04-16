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

export function ClassroomScreen() {
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
