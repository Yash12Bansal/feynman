/**
 * Best-effort "the user actually left without finishing feedback" logging.
 *
 * Honest about the browser limit: a real tab-close cannot show our own form
 * (browsers only allow their generic "Leave site?" dialog), so the *form* is
 * opened proactively by exit-intent BEFORE the page unloads. This hook is the
 * complement — it records a lightweight `bounce` to Firestore when the page is
 * genuinely going away, so we can measure how many people leave without giving
 * feedback.
 *
 * We listen on `pagehide` (fires on real navigation/close/refresh, NOT on a
 * mere tab-switch — so it doesn't pollute the bounce metric the way
 * `visibilitychange:hidden` would). It's still best-effort: a tab killed before
 * the async write flushes may drop it. Deduped to one bounce per session.
 *
 * `ENABLE_BEFOREUNLOAD_NUDGE` is an opt-in lever (default OFF) for the browser's
 * native confirm dialog on close — kept off because it shows only the generic
 * dialog (never our form) and reads as intrusive/distrustful.
 */

import { useEffect, useRef } from "react";
import { useAuth } from "../auth/authContext";
import { recordBounce } from "./feedbackService";
import { feedbackSession } from "./feedbackSession";

const ENABLE_BEFOREUNLOAD_NUDGE = false;

export function useLeaveSignals(): void {
  const { user, profile } = useAuth();
  const userRef = useRef(user);
  const profileRef = useRef(profile);
  const sentRef = useRef(false);
  useEffect(() => {
    userRef.current = user;
    profileRef.current = profile;
  }, [user, profile]);

  useEffect(() => {
    const sendBounce = () => {
      if (sentRef.current || feedbackSession.hasSubmitted()) return;
      sentRef.current = true;
      void recordBounce("exit", {
        uid: userRef.current?.uid ?? null,
        email: userRef.current?.email ?? null,
        name: profileRef.current?.name ?? userRef.current?.displayName ?? null,
        lectureChapterId: new URLSearchParams(window.location.search).get("lecture"),
      });
    };

    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (feedbackSession.hasSubmitted()) return;
      e.preventDefault();
      e.returnValue = "";
    };

    window.addEventListener("pagehide", sendBounce);
    if (ENABLE_BEFOREUNLOAD_NUDGE) {
      window.addEventListener("beforeunload", onBeforeUnload);
    }
    return () => {
      window.removeEventListener("pagehide", sendBounce);
      if (ENABLE_BEFOREUNLOAD_NUDGE) {
        window.removeEventListener("beforeunload", onBeforeUnload);
      }
    };
  }, []);
}
