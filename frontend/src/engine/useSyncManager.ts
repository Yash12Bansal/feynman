import { createContext, useContext, useState } from "react";
import { SyncManager } from "./SyncManager";

export const SyncManagerContext = createContext<SyncManager | null>(null);

export function useCreateSyncManager(): SyncManager {
  const [manager] = useState(() => new SyncManager());
  return manager;
}

export function useSyncManager(): SyncManager | null {
  return useContext(SyncManagerContext);
}
