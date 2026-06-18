/**
 * "Try Now" popup for the marketing landing page.
 *
 * Reuses the product's real auth: it calls `signInWithGoogle()` from the auth
 * context (the same Firebase Google popup the SignInScreen uses) and surfaces
 * `authError`. On success the AuthGate re-renders past `!user`, the marketing
 * page unmounts, and the modal goes with it — so there's no explicit "close on
 * success" to manage. Closeable via the ✕, the backdrop, or Escape.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/authContext";

export function TryNowModal({ onClose }: { readonly onClose: () => void }) {
  const { signInWithGoogle, authError } = useAuth();
  const [busy, setBusy] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  const onSignIn = useCallback(async () => {
    setBusy(true);
    await signInWithGoogle();
    setBusy(false);
  }, [signInWithGoogle]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    cardRef.current?.querySelector<HTMLButtonElement>(".fey-mkt-modal__google")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fey-mkt-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Sign in to Feynman"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="fey-mkt-modal__card" ref={cardRef}>
        <button
          type="button"
          className="fey-mkt-modal__close"
          aria-label="Close"
          onClick={onClose}
        >
          ✕
        </button>

        <div className="fey-mkt-modal__mark" aria-hidden>
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2 L13.9 10.1 L22 12 L13.9 13.9 L12 22 L10.1 13.9 L2 12 L10.1 10.1 Z"
              fill="#ffffff"
              fillOpacity="0.96"
            />
          </svg>
        </div>

        <h2>Start tonight's lesson</h2>
        <p>Sign in with Google and your AI teacher is ready in seconds.</p>

        <button
          type="button"
          className="fey-mkt-modal__google"
          onClick={onSignIn}
          disabled={busy}
        >
          {busy ? <span className="fey-mkt__spin" aria-hidden /> : <GoogleGlyph />}
          <span>{busy ? "Signing you in…" : "Continue with Google"}</span>
        </button>

        {authError && <p className="fey-mkt-modal__err">{authError}</p>}

        <p className="fey-mkt-modal__fine">
          We'll ask your name and number next — just to set up the profile.
          Nothing is shared.
        </p>
      </div>
    </div>
  );
}

function GoogleGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden>
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}
