import { useEffect } from "react";

const BASE = "Verity";

/** Per-page document title, so tabs, history and screen readers announce where you are. */
export function useTitle(title: string | null) {
  useEffect(() => {
    document.title = title ? `${title} · ${BASE}` : `${BASE} — An evidence investigation desk`;
  }, [title]);
}
