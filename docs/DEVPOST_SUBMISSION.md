# Devpost submission text

Copy each section into the matching Devpost field. Fill in the two `_TODO_` items first.

- **Project name:** Verity
- **Tagline:** Fact-check any text claim by claim, with verified quotes and a jury of two NVIDIA Nemotron models.
- **Try it out:** https://verity-six-kappa.vercel.app · https://github.com/Jaber-ja2314817/verity
- **Video:** _TODO: YouTube link (public, under 3 minutes)_
- **Track:** Best Apps and Agents (also select Best Use of Tavily if the form lists it)

---

## Inspiration

A claim can reach millions of people before anyone checks it. Most people don't have the time to
trace a forwarded message or a viral post back to its sources, and AI chatbots often answer
confidently without sources, sometimes inventing quotes. We wanted a tool that shows its work: what
was checked, where the evidence came from, and how sure it is.

## What it does

Paste text or an article link. Verity:

1. finds up to three checkable claims in it,
2. plans neutral, supporting and refuting searches for each claim and runs them with Tavily,
3. reads the sources and pulls out exact quotes, which code then verifies against the page (invented
   quotes are thrown away),
4. asks two different NVIDIA Nemotron models for a verdict independently: Nemotron 3.5 Lightning
   drafts while Nemotron 3 Ultra judges the same evidence,
5. if they disagree, or both say the evidence is too weak, searches again for what they asked for,
   and Ultra makes the final ruling.

Each claim gets `TRUE`, `FALSE`, `MISLEADING` or `UNVERIFIED`, with a confidence, an explanation,
sources with verified quotes, and a note on whether the jury agreed. Progress streams live while the
check runs. A model trace lists every AI call (model, step, tokens, time, cost), and a benchmark page
compares a single model with the jury on a labeled test set. A typical check takes 10–30 seconds and
costs under half a cent per claim.

## How we built it

- **AI:** all inference runs on **Nebius Token Factory** through its OpenAI-compatible API, using
  only NVIDIA Nemotron models: `nvidia/Nemotron-3_5-Lightning` for the fast steps (claims, queries,
  evidence, draft) and `nvidia/Nemotron-3-Ultra-550b-a55b` as the independent juror and final judge.
  We probed every Nemotron model on Token Factory before choosing these two.
- **Structured output:** Nemotron on Token Factory offers function calling but no JSON mode, so each
  step forces a tool call with a JSON schema. Invalid output is sent back to the model once as a tool
  result so it can fix it.
- **Search:** Tavily Search with full page text, cached for 24 hours, at most 2 sources per site;
  Tavily Extract for article links. Tavily's AI answers are never used.
- **Trust:** quotes are verified by code against the source text; web content is tagged as untrusted
  in every prompt; a small fixed list of reliable domains helps ranking.
- **Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite; React, TypeScript, Vite, Tailwind CSS. 315
  backend tests and 38 frontend tests run in GitHub Actions.
- **Hosting:** the web app runs on Vercel (FastAPI backend and Vite frontend as two services in one
  project). Each check runs inside its own request and streams its progress back, so it works on
  serverless hosting.

## Challenges we ran into

- **Reasoning ate the output budget.** With reasoning on, Lightning could spend almost all of its
  4,096 output tokens thinking before the forced tool call, so answers were cut off. We turned
  reasoning off per step (`enable_thinking: false`): the evidence step went from 30–46 s to 2–3 s
  per call. We kept it on only for claim extraction, where it stopped the model from inventing claims.
- **Quotes broke the JSON.** A source containing double quotes made the model break its JSON string
  while copying the quote. We now turn `"` into `'` in source text before sending it.
- **Silently dropped items.** Asked to assess 8 sources in one call, Lightning sometimes returned
  only the first one. Naming the exact source ids and count in the prompt fixed it (8 of 8 in 10 of
  10 calls), and we retry for any source it still leaves out.
- **Latency spikes and connection errors** on a few calls: we added our own retries with backoff
  inside a time budget.
- **Serverless hosting:** our first design ran checks in the background after the response, which
  serverless platforms pause. We changed it so each check runs inside its request and streams the
  result back.

## Accomplishments that we're proud of

- Every quote a user sees is verified to exist in its source.
- Two different NVIDIA Nemotron models act as a real, independent jury, with a debate round when
  they disagree.
- Full transparency: every model call, its cost and its timing are visible on the result page.
- A complete, tested product (live progress, share links, examples, "How it works" and benchmark
  pages) at under half a cent per claim.

## What we learned

- Reasoning models need per-step control: reasoning helps some steps and only adds time and cost to
  others.
- Forced tool calls are a reliable way to get structured output when there is no JSON mode, as long
  as the prompt names exactly what it expects.
- Verifying model output in code (quotes, ids, counts) catches errors that prompting alone does not.

## What's next

- Store results in a shared database so share links last forever.
- Better handling of `MISLEADING` claims and more languages.
- A browser extension to check a claim right where you read it.

## Built with

nvidia-nemotron, nebius-token-factory, tavily, python, fastapi, pydantic, sqlite, react, typescript,
vite, tailwindcss, vercel, docker, github-actions

## Feedback on Nebius Token Factory and NVIDIA models

Paste from `docs/FEEDBACK.md`.

---

## Submission checklist

- [ ] Working demo URL (https://verity-six-kappa.vercel.app)
- [ ] Public YouTube video, under 3 minutes
- [ ] Public repo with the MIT license visible in the GitHub About section
- [ ] Team names in `LICENSE` (it still says "Verity team")
- [ ] README explains how Nemotron and Token Factory are used
- [ ] Feedback pasted from `docs/FEEDBACK.md`
- [ ] Track: Best Apps and Agents (+ Tavily bonus if listed)
- [ ] All team members added on Devpost
- [ ] **Submitted** (not a draft) before Fri Oct 30, 8:00 pm Doha time
