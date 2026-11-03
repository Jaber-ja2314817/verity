# News search: Auto and News modes (Dev branch)

Verity can search news articles instead of the general web. It is off until you configure a
news API, so the hackathon behaviour on `main` is unchanged.

## Turn it on

1. Get a free key at <https://gnews.io> (or <https://newsdata.io>).
2. Add to `.env` (local) or to the **Preview** environment on Vercel only, so the judged
   production site does not change:

   ```
   NEWS_PROVIDER=gnews        # or newsdata
   NEWS_API_KEY=...
   ```

3. Restart the backend. `GET /api/health` now returns `"news_search": true`, and the input box
   shows an **Auto | News** toggle.

Other settings (all optional, see `.env.example`): `NEWS_MAX_RESULTS`, `NEWS_LOOKBACK_DAYS`,
`NEWS_QUERIES_PER_CLAIM`, `NEWS_MIN_SOURCES`, `NEWS_FETCH_PAGES`.

## What the modes do

| Mode | Behaviour |
| --- | --- |
| `auto` (default) | Nemotron Lightning marks each claim as time-sensitive while planning its searches (`time_sensitive` in the query plan). Recent-event claims go to the news API; settled facts go to Tavily web search. |
| `news` | Every claim goes to the news API first. |
| `web` | Tavily only (what `main` does). Used by the API and by `run_eval.py`. |

`POST /api/checks` and `/api/checks/stream` accept `"mode": "auto" | "news" | "web"` next to
`text` or `url`. A headline is just a short claim; a pasted article or an article URL goes
through claim extraction as before.

## Fewer Tavily calls

A news-routed claim makes up to `NEWS_QUERIES_PER_CLAIM` (2) news API calls, then:

- 3 or more sources found: **0** Tavily calls (was 3).
- Fewer than 3: **1** Tavily query tops them up.
- News API down, out of quota or refused the key: the claim uses normal web search. A news
  outage never fails a check.

## Quote verification still applies

Free news plans return only a short snippet. Verity downloads each article page itself (public
http(s) hosts only, 10 s, 1.5 MB, HTML only), keeps the paragraph text, and verifies quotes
against it exactly like web sources. A blocked or paywalled page falls back to the snippet.
Page text is treated as untrusted data like everything else from the web.

Each claim card says which search was used and how many independent outlets have a verified
quote. Stored checks record it as `search: "web" | "news" | "mixed"`.

## Limits to know

- GNews's free plan is for non-commercial use and delays articles by about 12 hours, so
  breaking news can be missed. A public launch needs a paid plan.
- NewsData.io's free plan returns no article body; Verity reads the pages instead.
- Neither API is an AI service, so CLAUDE.md rule 1 still holds: the only models are the
  NVIDIA models through Nebius.

## Benchmark

```bash
.venv/bin/python scripts/run_eval.py --search web    # baseline (same as the hackathon version)
.venv/bin/python scripts/run_eval.py --search auto
.venv/bin/python scripts/run_eval.py --search news
```

Only a full `--search web` run updates `eval/results/latest.json`. The benchmark has no
results yet: `eval/claims.jsonl` does not exist until someone confirms the 40 labels in
`eval/claims_draft.jsonl` (see `eval/VERIFY_CLAIMS.md`). Add some claims from the last few
weeks, or Auto mode will rarely take the news route.
