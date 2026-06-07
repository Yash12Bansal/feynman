/**
 * Auth context provider: wraps Firebase Auth + the Firestore profile doc.
 *
 * Exposes the current user, their profile (name/phone/email), and the three
 * actions the gate needs: sign in with Google, save the profile, sign out.
 * When Firebase isn't configured it stays inert (`configured: false`) so the
 * app can render a setup notice instead of crashing.
 *
 * The context + `useAuth` hook live in ./authContext so this file exports only
 * the component.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  onAuthStateChanged,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { doc, getDoc, serverTimestamp, setDoc } from "firebase/firestore";

import { auth, db, firebaseConfigured, googleProvider } from "../lib/firebase";
import { AuthContext, type AuthContextValue } from "./authContext";
import type { UserProfile } from "./types";

export function AuthProvider({ children }: { readonly children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  // Only "initializing" when we'll actually wait for an auth callback. When
  // Firebase is unconfigured we never subscribe, so start resolved.
  const [initializing, setInitializing] = useState(firebaseConfigured);
  const [profileLoading, setProfileLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    if (!firebaseConfigured || !auth) return;
    const unsub = onAuthStateChanged(auth, (nextUser) => {
      // Unblock the gate the instant auth resolves — do NOT wait on the Firestore
      // read here. A slow/blocked Firestore would otherwise hold the splash for
      // seconds (and the read can fail "offline"). Fetch the profile in the
      // background under its own flag so the gate can show a splash (not the
      // setup form) while it resolves. React batches these same-tick updates, so
      // there's no flash of the form for a signed-in user.
      setUser(nextUser);
      setInitializing(false);
      if (nextUser && db) {
        const database = db;
        setProfileLoading(true);
        getDoc(doc(database, "users", nextUser.uid))
          .then((snap) => {
            if (snap.exists()) {
              setProfile(snap.data() as UserProfile);
              return;
            }
            // First time we've seen this account — record the sign-in right away
            // (don't wait for them to finish the profile) so every signed-in user
            // has a Firestore row. profileComplete:false keeps the gate on the
            // setup form; keeping the stub in local state also lets saveProfile
            // preserve createdAt when it later completes the doc.
            const stub: UserProfile = {
              uid: nextUser.uid,
              name: nextUser.displayName ?? "",
              email: nextUser.email ?? "",
              phone: "",
              photoURL: nextUser.photoURL ?? null,
              profileComplete: false,
            };
            setProfile(stub);
            void setDoc(
              doc(database, "users", nextUser.uid),
              { ...stub, createdAt: serverTimestamp(), updatedAt: serverTimestamp() },
              { merge: true },
            ).catch((err) => console.error("[auth] failed to record sign-in", err));
          })
          .catch((err) => {
            console.error("[auth] failed to load profile", err);
            setProfile(null);
          })
          .finally(() => setProfileLoading(false));
      } else {
        setProfile(null);
        setProfileLoading(false);
      }
    });
    return unsub;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!auth || !googleProvider) return;
    setAuthError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err: unknown) {
      const code = (err as { code?: string })?.code ?? "";
      // User dismissed the popup — not an error worth surfacing.
      if (
        code === "auth/popup-closed-by-user" ||
        code === "auth/cancelled-popup-request"
      ) {
        return;
      }
      console.error("[auth] sign-in failed", err);
      setAuthError(humanAuthError(code));
    }
  }, []);

  const saveProfile = useCallback(
    async ({ name, phone }: { name: string; phone: string }) => {
      if (!db || !user) return;
      const next: UserProfile = {
        uid: user.uid,
        name: name.trim(),
        email: user.email ?? "",
        phone: phone.trim(),
        photoURL: user.photoURL ?? null,
        profileComplete: true,
      };
      // Optimistic: open the gate immediately rather than waiting on the network
      // write. The persistent cache queues the write and syncs it when the
      // transport recovers, so we don't roll back on a transient failure.
      setProfile(next);
      try {
        await setDoc(
          doc(db, "users", user.uid),
          {
            ...next,
            updatedAt: serverTimestamp(),
            // Only stamp createdAt on first write (merge preserves it after).
            ...(profile ? {} : { createdAt: serverTimestamp() }),
          },
          { merge: true },
        );
      } catch (err) {
        console.error("[auth] failed to persist profile", err);
      }
    },
    [user, profile],
  );

  const signOut = useCallback(async () => {
    if (auth) await firebaseSignOut(auth);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      configured: firebaseConfigured,
      initializing,
      profileLoading,
      user,
      profile,
      profileComplete: Boolean(profile?.profileComplete),
      authError,
      signInWithGoogle,
      saveProfile,
      signOut,
    }),
    [initializing, profileLoading, user, profile, authError, signInWithGoogle, saveProfile, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

function humanAuthError(code: string): string {
  switch (code) {
    case "auth/operation-not-allowed":
    case "auth/configuration-not-found":
      return "Google sign-in isn't enabled in Firebase yet — Authentication → Sign-in method → Google → Enable.";
    case "auth/unauthorized-domain":
      return "This domain isn't authorised yet — add it in Firebase → Authentication → Settings → Authorized domains.";
    case "auth/popup-blocked":
      return "Your browser blocked the sign-in popup. Allow popups for this site and try again.";
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again.";
    case "auth/invalid-api-key":
    case "auth/api-key-not-valid":
      return "The Firebase API key looks invalid — check frontend/.env.local and restart the dev server.";
    default:
      return `Sign-in didn't go through${code ? ` (${code})` : ""}. Please try again.`;
  }
}
