import { GITHUB_URL } from "../api";

export default function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          Powered by <span className="font-medium text-ink">NVIDIA Nemotron</span> on Nebius Token
          Factory <span aria-hidden>·</span> Search by Tavily <span aria-hidden>·</span>{" "}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-line underline-offset-2 hover:text-ink hover:decoration-accent"
          >
            Open source
          </a>
        </p>
        <p className="font-serif italic">Fact-checks you can audit.</p>
      </div>
    </footer>
  );
}
