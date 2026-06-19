import { lazy, Suspense } from "react";
import { LectureHomeScreen } from "./screens/LectureHomeScreen";
import { AuthProvider } from "./auth/AuthProvider";
import { AuthGate } from "./auth/AuthGate";
import { ThemeProvider } from "./theme/ThemeProvider";
import { MarketingLanding } from "./marketing/MarketingLanding";
import { AccountChip } from "./auth/AccountChip";
import { FeedbackFab } from "./feedback/FeedbackFab";
import { ExitIntentFeedback } from "./feedback/ExitIntentFeedback";
import { useLectureChapterParam } from "./hooks/useLectureChapterParam";

// Spinner keyframe for the lecture-loading fallback (inline styles can't carry
// @keyframes; inject once — the established pattern in this codebase).
if (typeof document !== "undefined" && !document.getElementById("lv-load-kf")) {
  const s = document.createElement("style");
  s.id = "lv-load-kf";
  s.textContent =
    "@keyframes lv-load-spin { to { transform: rotate(360deg); } }";
  document.head.appendChild(s);
}

// The immersive lecture experience (ClassroomScreen + the whiteboard engine,
// LiveKit, katex, charts, gsap, roughjs…) is the bulk of the JS bundle. It is
// only needed once a student opens a lecture (?lecture=<id>), so we lazy-load
// it — the product front door (LectureHomeScreen) stays small and fast to first
// paint. Vite splits this dynamic import into its own chunk automatically.
const MainApp = lazy(() =>
  import("./MainApp").then((m) => ({ default: m.MainApp })),
);

export function App() {
  // Gate the entire product behind Google sign-in + profile completion. The
  // feedback surfaces mount inside the gate so only signed-in users see them.
  //
  // `?preview=landing` renders the public marketing page standalone (inside the
  // AuthProvider so its Try-Now sign-in works, but bypassing the gate) — so the
  // light landing page can be viewed without a live auth session, even when
  // VITE_AUTH_DISABLED is set or Firebase isn't configured locally.
  const previewLanding =
    new URLSearchParams(window.location.search).get("preview") === "landing";
  return (
    <ThemeProvider>
      <AuthProvider>
        {previewLanding ? (
          <MarketingLanding />
        ) : (
          <AuthGate>
            <AppShell />
          </AuthGate>
        )}
      </AuthProvider>
    </ThemeProvider>
  );
}

function AppShell() {
  // The account chip stays available everywhere (sign-out must always be
  // reachable), but it MOVES during a lecture: the immersive viewer puts the
  // slide title in the top-left, so a top-left avatar would cover it. In a
  // lecture the chip drops to the bottom-left control cluster instead. The hook
  // is popstate-aware so the position toggles on navigation.
  const lecture = useLectureChapterParam();
  return (
    <>
      <MainEntry />
      <AccountChip inLecture={!!lecture} />
      <FeedbackFab inLecture={!!lecture} />
      <ExitIntentFeedback />
    </>
  );
}

function MainEntry() {
  // ?lecture=<id> in the URL → the (lazy-loaded) immersive lecture app, which
  // renders the precomputed lecture (LiveKit connects lazily, only on the first
  // doubt). No param → product front door (LectureHomeScreen).
  const params = new URLSearchParams(window.location.search);
  if (params.get("lecture")) {
    return (
      <Suspense fallback={<LectureLoading />}>
        <MainApp />
      </Suspense>
    );
  }
  return <LectureHomeScreen />;
}

function LectureLoading() {
  // Shown for the fraction of a second while the lecture chunk loads on first
  // open. The product shell is the light "Living Notebook" skin (home picker +
  // marketing landing), so this hand-off renders in the same warm-paper palette
  // — opening a lecture from the home stays continuous and light instead of
  // flashing to a dark screen before the room mounts. Inline values mirror the
  // `.notebook` tokens (styles/notebook-theme.css): this renders outside that
  // scope, so it can't read the CSS variables directly.
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 18,
        background: "#faf6ee", // --paper
        color: "rgba(27, 25, 22, 0.5)", // --ink, faded for a quiet label
        fontFamily: "'Hanken Grotesk', -apple-system, system-ui, sans-serif", // --body
        fontSize: "0.78rem",
        fontWeight: 600,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 26,
          height: 26,
          borderRadius: "50%",
          border: "2px solid rgba(39, 64, 221, 0.16)", // --blue @ low alpha
          borderTopColor: "#2740dd", // --blue
          animation: "lv-load-spin 0.8s linear infinite",
        }}
      />
      Loading…
    </div>
  );
}
