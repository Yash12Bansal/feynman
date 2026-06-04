/**
 * Auth context + `useAuth` hook, split out from AuthProvider so the provider
 * file exports only its component (keeps React Fast Refresh happy — a file
 * mixing a component with hooks/constants breaks HMR).
 */

import { createContext, useContext } from "react";
import type { User } from "firebase/auth";
import type { UserProfile } from "./types";

export interface AuthContextValue {
  /** False when Firebase env is missing (show the setup notice). */
  readonly configured: boolean;
  /** True until the first auth-state resolution completes. */
  readonly initializing: boolean;
  readonly user: User | null;
  readonly profile: UserProfile | null;
  readonly profileComplete: boolean;
  readonly authError: string | null;
  readonly signInWithGoogle: () => Promise<void>;
  readonly saveProfile: (data: { name: string; phone: string }) => Promise<void>;
  readonly signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
