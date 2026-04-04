import { useCallback } from "react";
import { WhiteboardScene } from "../engine/whiteboard/WhiteboardScene";
import {
  useCreateSyncManager,
  SyncManagerContext,
} from "../engine/useSyncManager";
import { useVisualChannel } from "../livekit/useVisualChannel";
import { useAgentTranscription } from "../livekit/useAgentTranscription";

export function ClassroomScreen() {
  const {
    activeInstructions,
    activeWalks,
    activeBoardId,
    activeBoardMeta,
    pendingTransition,
    cameraState,
    clearTransition,
    getBoardInstructions,
  } = useVisualChannel();
  const syncManager = useCreateSyncManager();
  const handleWord = useCallback(
    (word: string) => syncManager.onWord(word),
    [syncManager],
  );
  useAgentTranscription(handleWord);

  return (
    <SyncManagerContext.Provider value={syncManager}>
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
    </SyncManagerContext.Provider>
  );
}
