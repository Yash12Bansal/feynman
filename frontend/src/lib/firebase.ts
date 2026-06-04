/**
 * Firebase client initialisation.
 *
 * Client-only: Auth (Google) + Firestore. No server secrets — the web config
 * below is public by design (Firestore security rules are the real guard; see
 * AUTH_FEEDBACK_SETUP.md). Everything is read from `VITE_FIREBASE_*` env vars.
 *
 * If the env is missing, `firebaseConfigured` is false and the singletons stay
 * null — the app shows a "configure Firebase" notice instead of crashing, and
 * feedback writes no-op. This keeps local dev unblocked before Firebase is set
 * up (also see `VITE_AUTH_DISABLED` in config.ts for a full gate bypass).
 */

import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";
import { getFirestore, type Firestore } from "firebase/firestore";
import { getAnalytics, isSupported as analyticsIsSupported } from "firebase/analytics";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID,
};

/** True only when the minimum required web config is present. */
export const firebaseConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.appId,
);

let app: FirebaseApp | null = null;
let authInstance: Auth | null = null;
let dbInstance: Firestore | null = null;
let googleProviderInstance: GoogleAuthProvider | null = null;

if (firebaseConfigured) {
  app = initializeApp(firebaseConfig);
  authInstance = getAuth(app);
  dbInstance = getFirestore(app);
  googleProviderInstance = new GoogleAuthProvider();
  // Always let the user pick which Google account — important for shared
  // demo machines in a feedback cohort.
  googleProviderInstance.setCustomParameters({ prompt: "select_account" });

  // Google Analytics — optional + best-effort. `isSupported()` is false in
  // tests/SSR/unsupported browsers, so this never runs there; any failure is
  // swallowed and never blocks the app.
  if (firebaseConfig.measurementId) {
    void analyticsIsSupported()
      .then((ok) => {
        if (ok && app) getAnalytics(app);
      })
      .catch(() => {
        /* analytics is best-effort */
      });
  }
}

export const auth = authInstance;
export const db = dbInstance;
export const googleProvider = googleProviderInstance;
