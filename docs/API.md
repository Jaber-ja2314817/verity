# Verity API (v1)

Check a claim, headline or article from your own app. Interactive docs: `/v1/docs`
(OpenAPI: `/v1/openapi.json`).

## Quick start

```bash
curl -X POST "https://YOUR-VERITY-HOST/v1/checks?wait=true" \
  -H "Authorization: Bearer vrt_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "The Eiffel Tower was completed in 1889.", "mode": "auto"}'
```

`wait=true` holds the request until the verdict is ready (about 10 to 30 seconds) and returns
`200` with the full result. Without it you get `202` and an `id`, and poll
`GET /v1/checks/{id}` until `status` is `done` or `error`.

> **On Vercel always use `wait=true`.** Without it the check runs after the response is sent,
> and a serverless host may pause it. On the Docker/Render backend both ways work.

## Endpoints

| Method and path | What it does |
| --- | --- |
| `POST /v1/checks` | Start a check. Body: `text` **or** `url`, optional `mode` (`auto` default, `news`, `web`). Query: `wait=true`. |
| `GET /v1/checks/{id}` | Status and result. Only the key that started the check can read it. |
| `GET /v1/usage` | This key's limits and how much of today's quota is used. |

Input limits are the same as the website: text up to `MAX_INPUT_CHARS` (5,000), or a link.
Up to 3 claims per check are verified.

### Result

```json
{
  "id": "k3T9xQ1aB2c",
  "status": "done",
  "created_at": "2026-11-03T15:20:00+00:00",
  "language": "en",
  "duration_s": 9.1,
  "claims": [
    {
      "id": 1,
      "text": "The Eiffel Tower was completed in 1889.",
      "verdict": "TRUE",
      "confidence": 96,
      "explanation": "...",
      "models_agreed": true,
      "search": "web",
      "sources": [
        {
          "id": 1, "url": "https://...", "title": "...", "domain": "...",
          "published_date": "2025-05-01", "reliability": "high",
          "stance": "supports", "quote": "Sentence copied word for word from the page.",
          "cited": true
        }
      ]
    }
  ],
  "skipped_claims": [{"text": "It is beautiful.", "reason": "opinion"}]
}
```

- `verdict` is `TRUE`, `FALSE`, `MISLEADING` or `UNVERIFIED`. **UNVERIFIED means "not enough
  reliable evidence", not false.** Show it as such.
- `confidence` is 0 to 100. Every `quote` is verified to appear in the source page.
- `models_agreed` is false when the two independent models disagreed and a debate round decided.
- `search` says where the sources came from: `web`, `news` or `mixed`.
- `status: "error"` comes with a user-safe `error` message.

## Authentication, limits, errors

Send `Authorization: Bearer vrt_...` on every request. Each key has a per-minute rate limit
(per server instance) and a daily quota (UTC day). The whole service also has a daily cap, to
protect its model credits.

| Status | Meaning |
| --- | --- |
| `400` | Invalid body (text too short or long, both or neither of `text`/`url`, bad `mode`). Not counted. |
| `401` | Missing, wrong or revoked key. |
| `404` | Unknown check id, or a check that belongs to another key. |
| `429` | Per-minute limit or daily quota reached. `Retry-After` says how many seconds to wait. |
| `503` | The service's daily cap is reached. `Retry-After` is seconds to 00:00 UTC. |

Errors look like `{"detail": "..."}`.

## Managing keys (you, the operator)

The easy way: open **/admin** on your site, sign in with the admin secret, and create, copy and
revoke keys there. Developers get a public guide at **/developers**. The curl commands below do
the same from a terminal.

Set `ADMIN_SECRET` (at least 24 characters) on the server. Without it these endpoints are off.

```bash
# create (the key is shown once)
curl -X POST https://YOUR-HOST/api/admin/keys \
  -H "Authorization: Bearer $ADMIN_SECRET" -H "Content-Type: application/json" \
  -d '{"name": "News app", "rate_per_minute": 10, "daily_quota": 200}'

# list (names, prefixes, today's usage; never the keys)
curl https://YOUR-HOST/api/admin/keys -H "Authorization: Bearer $ADMIN_SECRET"

# revoke
curl -X DELETE https://YOUR-HOST/api/admin/keys/KEY_ID -H "Authorization: Bearer $ADMIN_SECRET"
```

Keys are stored as SHA-256 hashes. A wrong admin secret 10 times from one IP locks that IP out
for 10 minutes. Omitted limits use `API_DEFAULT_RATE_PER_MINUTE` and `API_DEFAULT_DAILY_QUOTA`.

## Storage: Neon Postgres

Without `DATABASE_URL` Verity uses a local SQLite file. That is fine for the Docker/Render
backend with a disk, but on Vercel the file disappears, which is why share links vanished and
why API keys could not persist there.

1. Create a free project at <https://neon.tech> and copy the **pooled** connection string.
2. Set `DATABASE_URL` to it (locally in `.env`; on Vercel, in **Preview** first).
3. Start the backend. The tables are created automatically.

Checks, share links, the search cache and API keys then live in Postgres and are shared by
every instance. Keep one database per environment (preview vs production), so test keys never
work on the judged site.

## Limits to know

- The per-minute limit is kept in memory, so on several serverless instances the effective
  limit can be a little higher. The daily quota and the service-wide cap are exact (database).
- Checks are private to their key: they are not reachable through the website's share links.
- The API is not rate-limited by IP; the key is the identity. Protect keys like passwords.
