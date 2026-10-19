# Feedback on Nebius Token Factory, Nemotron and Nebius AI Cloud

Running log kept while building. Edited into final form before submission.

## Nebius Token Factory

### Problems we hit
- 2026-10-14: Qatar is not in the Token Factory billing country list, and signup cannot skip the
  billing page, so a participant based in Qatar could not redeem the hackathon promo code.
  Asked for help in the Nebius Discord. Nebius AI Cloud billing worked from Qatar, so the two
  products have different country lists.

## Nemotron models

### 2026-10-17 — Nemotron 3.5 Lightning: reasoning and forced tool calls
- With reasoning on (the default), Lightning's reasoning for an 8-source evidence prompt used
  ~3,600–4,100 of 4,096 output tokens before the forced `submit` tool call, so calls were often
  cut off (`finish_reason=length`). `chat_template_kwargs: {"enable_thinking": false}` fixed it:
  455 tokens, 1.8 s instead of ~13 s. Docs on how reasoning tokens count toward `max_tokens`
  with `tool_choice` forced would help. A `/no_think` system prompt did NOT work.
- With reasoning off, a source containing double quotes (a quoted astronaut sentence) made the
  model break its JSON string while copying the quote, then emit whitespace until `max_tokens`
  (3 of 5 runs). The server-side tool-call parser then returned no tool call, only raw
  `<tool_call>` text in `content`. We now turn " into ' in source text sent to the model.
- With reasoning off, Lightning sometimes added claims the input never made (e.g. a
  counter-claim). Reasoning on for that short step fixed it in 9/9 runs.

## Nebius AI Cloud

### 2026-10-19 — Token Factory: latency spikes and transient connection errors
- The same tiny forced-tool call to Nemotron 3.5 Lightning (905 in / 78 out tokens, reasoning off)
  took 51 s once and 0.85 s right after. Short outliers like this make a fixed client timeout
  hard to pick; a documented latency SLO or queueing signal (e.g. a header) would help.
- In an eval run with 3 checks starting at once, one call failed with `APIConnectionError`
  even after the OpenAI SDK's 2 quick retries. We now retry connection errors, timeouts, 429
  and 5xx ourselves with 1 s / 3 s / 8 s backoff inside a time budget.
- Answering a bad forced tool call with an `assistant` tool-call message plus a `tool` message
  (OpenAI tool-calling contract) works on Token Factory with `tool_choice` forced; the model
  corrected its arguments on the next turn.

### 2026-10-19 — Nemotron 3.5 Lightning: items dropped from a list, reasoning cost
- Asked to assess 8 numbered sources in one forced tool call (reasoning off), Lightning often
  returned an item for source 1 only (2 of 2 claims in our test), silently dropping the rest.
  Naming the exact ids and count in the prompt ("one item per source id, for all 8 sources
  (1, 2, ..., 8)") fixed it: 8/8 items in 10/10 later calls.
- Same 8-source step with reasoning on: 30–46 s and 6,700–9,800 output tokens per call
  (vs 2–3 s and ~500 tokens off), for no better stances on our test sets, so we keep it off
  for this step. A way to cap reasoning tokens separately from the answer would help.
