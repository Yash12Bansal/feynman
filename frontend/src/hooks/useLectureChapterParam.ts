import { useState, useEffect } from "react";

/**
 * Reads `?lecture=<chapter_id>` from the URL and stays in sync with browser
 * back/forward (popstate). Returns the chapter id, or null on the front door.
 *
 * Extracted to its own module so both the eager app shell and the lazy-loaded
 * lecture app (`MainApp`) can share it without dragging one into the other's
 * bundle chunk.
 */
export function useLectureChapterParam(): string | null {
  const [value, setValue] = useState<string | null>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("lecture");
  });
  useEffect(() => {
    const onPop = () => {
      const params = new URLSearchParams(window.location.search);
      setValue(params.get("lecture"));
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return value;
}
