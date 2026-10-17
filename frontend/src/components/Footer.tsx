import { GITHUB_URL } from "../api";

export default function Footer() {
  return (
    <footer className="mx-auto w-full max-w-[60rem] px-4 sm:px-12">
      <div className="flex flex-col gap-2 border-t border-line py-6 text-[11px] text-muted sm:flex-row sm:items-center sm:justify-between">
        <p>
          <span className="uppercase">Verity</span> / Follow the evidence.
        </p>
        <p className="text-note">
          NVIDIA Nemotron on Nebius Token Factory <span aria-hidden>·</span> Search by Tavily{" "}
          <span aria-hidden>·</span>{" "}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline decoration-note/40 underline-offset-2 hover:text-ink"
          >
            Open source
          </a>
        </p>
      </div>
    </footer>
  );
}
