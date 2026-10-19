import { Link } from "react-router-dom";
import { useTitle } from "../lib/useTitle";

export default function NotFound() {
  useTitle("Page not found");
  return (
    <section className="flex flex-col items-start pt-16 sm:pt-24">
      <p className="font-serif text-7xl text-muted tabular-nums">404</p>
      <h1 className="mt-4 font-serif text-3xl tracking-tight">This page doesn't exist.</h1>
      <p className="mt-3 max-w-md text-muted">
        The link may be mistyped, or the page has moved. Fact-checking is still one click away.
      </p>
      <Link
        to="/"
        className="mt-8 rounded-xl bg-ink px-6 py-3 text-sm font-semibold text-paper transition hover:bg-accent-ink"
      >
        Back to Verity
      </Link>
    </section>
  );
}
