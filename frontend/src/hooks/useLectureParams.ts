import { useEffect, useState } from "react";

/** Read `?lecture=` and `?persona=` from the URL (popstate-aware). */
export function useLectureParams(): {
  chapterId: string | null;
  personaId: string;
} {
  const read = () => {
    const params = new URLSearchParams(window.location.search);
    return {
      chapterId: params.get("lecture"),
      personaId: params.get("persona") ?? "default",
    };
  };

  const [value, setValue] = useState(read);

  useEffect(() => {
    const onPop = () => setValue(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return value;
}
