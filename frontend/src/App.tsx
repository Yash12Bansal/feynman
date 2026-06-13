import { lazy, Suspense } from "react";
import { LectureHomeScreen } from "./screens/LectureHomeScreen";
import { AuthProvider } from "./auth/AuthProvider";
import { AuthGate } from "./auth/AuthGate";
import { AccountChip } from "./auth/AccountChip";
import { FeedbackFab } from "./feedback/FeedbackFab";
import { ExitIntentFeedback } from "./feedback/ExitIntentFeedback";
import { useLectureChapterParam } from "./hooks/useLectureChapterParam";

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
  return (
    <AuthProvider>
      <AuthGate>
        <AppShell />
      </AuthGate>
    </AuthProvider>
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
      <FeedbackFab />
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
  // Minimal, theme-neutral placeholder shown for the fraction of a second while
  // the lecture chunk loads on first open (cached thereafter).
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "#888",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      Loading…
    </div>
  );
}
