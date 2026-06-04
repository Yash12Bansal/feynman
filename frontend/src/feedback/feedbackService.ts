/**
 * Persists feedback to Firestore (`feedback` collection). Degrades to a console
 * log when Firebase isn't configured, so the UI never breaks in local dev.
 *
 * All fields are kept defined (never undefined) — Firestore rejects undefined.
 * `ratings` values may be null (question skipped); null is allowed.
 */

import { addDoc, collection, serverTimestamp } from "firebase/firestore";
import { db, firebaseConfigured } from "../lib/firebase";

export interface FeedbackContext {
  readonly uid: string | null;
  readonly email: string | null;
  readonly name: string | null;
  readonly lectureChapterId: string | null;
}

export interface FeedbackPayload {
  readonly variant: "exit" | "manual";
  /** questionId → chosen option index (0-based), or null if not answered. */
  readonly ratings: Record<string, number | null>;
  /** questionId → chosen option label, for human-readable analysis. */
  readonly ratingLabels: Record<string, string>;
  readonly liked: string;
  readonly disliked: string;
  readonly future: string;
  readonly note: string;
}

export async function submitFeedback(
  payload: FeedbackPayload,
  ctx: FeedbackContext,
): Promise<void> {
  if (!firebaseConfigured || !db) {
    console.info("[feedback] firebase not configured — would submit:", payload, ctx);
    return;
  }
  await addDoc(collection(db, "feedback"), {
    ...payload,
    uid: ctx.uid,
    email: ctx.email,
    name: ctx.name,
    lectureChapterId: ctx.lectureChapterId,
    path: window.location.pathname + window.location.search,
    userAgent: navigator.userAgent,
    createdAt: serverTimestamp(),
  });
}
