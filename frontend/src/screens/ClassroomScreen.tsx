import { useCallback } from "react";
import { VisualScene } from "../engine/VisualScene";
import {
  useCreateSyncManager,
  SyncManagerContext,
} from "../engine/useSyncManager";
import { useVisualChannel } from "../livekit/useVisualChannel";
import { useAgentTranscription } from "../livekit/useAgentTranscription";

export function ClassroomScreen() {
  const { instructions } = useVisualChannel();
  const syncManager = useCreateSyncManager();
  const handleWord = useCallback(
    (word: string) => syncManager.onWord(word),
    [syncManager],
  );
  useAgentTranscription(handleWord);

  return (
    <SyncManagerContext.Provider value={syncManager}>
      <VisualScene instructions={instructions} />
    </SyncManagerContext.Provider>
  );
}
