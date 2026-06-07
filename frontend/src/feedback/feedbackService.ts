/**
 * Persists feedback to Firestore (`feedback` collection). Degrades to a console
 * log when Firebase isn't configured, so the UI never breaks in local dev.
 *
 * All fields are kept defined (never undefined) — Firestore rejects undefined.
 * `ratings` values may be null (question skipped); null is allowed.
 *
 * SCHEMA NOTE — read before renaming question ids:
 *   `source` is the canonical channel tag going forward
 *   ("manual" | "exit" | "in_lecture"). The legacy `variant` field is kept only
 *   so older dashboards keep reading. The keys inside `answers` and `ratings`
 *   are the step ids from `steps.ts` and are now a STABLE CONTRACT — renaming a
 *   step id silently fragments historical data. The four legacy string fields
 *   (liked/disliked/future/note) are always-defined MIRRORS of specific answers,
 *   retained for back-compat; new analysis should read `answers` keyed by id.
 */

import { addDoc, collection, serverTimestamp } from "firebase/firestore";
import { db, firebaseConfigured } from "../lib/firebase";

export type FeedbackSource = "manual" | "exit" | "in_lecture";

export interface FeedbackContext {
  readonly uid: string | null;
  readonly email: string | null;
  readonly name: string | null;
  readonly lectureChapterId: string | null;
}

export interface FeedbackPayload {
  /** Canonical channel this feedback came from. */
  readonly source: FeedbackSource;
  /** Legacy channel tag — kept so older Firestore reads don't break. */
  readonly variant: "exit" | "manual";
  /** stepId → chosen option index (0-based), or null if not answered. */
  readonly ratings: Record<string, number | null>;
  /** stepId → chosen option label, for human-readable analysis. */
  readonly ratingLabels: Record<string, string>;
  /** stepId → free-text answer; MCQ comments live under `${stepId}__comment`. */
  readonly answers: Record<string, string>;
  // ── Legacy always-defined mirrors of specific answers (back-compat) ──
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
    // Tagged so real submissions and bounce beacons filter symmetrically
    // (`where type == "submission"` vs `"bounce"`) in the same collection.
    type: "submission",
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

/**
 * Fire-and-forget "the user left without finishing feedback" beacon. Best-effort
 * only — Firestore's `addDoc` is not `navigator.sendBeacon`, so a tab killed
 * mid-write may drop it. Written to the same `feedback` collection with
 * `type: "bounce"` so it's trivially filterable from real submissions.
 */
export async function recordBounce(
  source: FeedbackSource,
  ctx: FeedbackContext,
): Promise<void> {
  if (!firebaseConfigured || !db) {
    console.info("[feedback] firebase not configured — would record bounce:", source, ctx);
    return;
  }
  try {
    await addDoc(collection(db, "feedback"), {
      type: "bounce",
      source,
      uid: ctx.uid,
      email: ctx.email,
      name: ctx.name,
      lectureChapterId: ctx.lectureChapterId,
      path: window.location.pathname + window.location.search,
      userAgent: navigator.userAgent,
      createdAt: serverTimestamp(),
    });
  } catch (err) {
    console.error("[feedback] bounce write failed", err);
  }
}
