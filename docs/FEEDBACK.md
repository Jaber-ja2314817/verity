# Feedback on Nebius Token Factory, NVIDIA Nemotron and Nebius AI Cloud

Notes logged while building Verity (Oct 13–29, 2026). Verity sends every AI call to Token Factory
and uses only `nvidia/Nemotron-3_5-Lightning` and `nvidia/Nemotron-3-Ultra-550b-a55b`.

## Nebius Token Factory

### What worked well
- The OpenAI-compatible API worked with the official `openai` Python SDK (`AsyncOpenAI`) by only
  changing the base URL; no custom client was needed.
- Forced tool calls (`tool_choice` with a JSON schema) worked for every Nemotron model we probed
  (Lightning, Ultra, Nano 30B), which gave us reliable structured output without a JSON mode.
- The OpenAI tool-calling contract for corrections works: answering a bad forced tool call with an
  `assistant` tool-call message plus a `tool` message made the model fix its arguments on the next turn.
- Cost: checking one claim (5 model calls across both models) costs about $0.004.

### Problems we hit
- 2026-10-14: Qatar is not in the Token Factory billing country list, and signup cannot skip the
  billing page, so a participant based in Qatar could not redeem the hackathon promo code. We asked
  for help in the Nebius Discord. Nebius AI Cloud billing worked from Qatar, so the two products
  have different country lists.
- 2026-10-19: the same tiny forced-tool call to Nemotron 3.5 Lightning (905 in / 78 out tokens,
  reasoning off) took 51 s once and 0.85 s right after. Outliers like this make a fixed client
  timeout hard to pick.
- 2026-10-19: in an eval run with 3 checks starting at once, one call failed with
  `APIConnectionError` even after the OpenAI SDK's 2 quick retries. We now retry connection errors,
  timeouts, 429 and 5xx ourselves with 1 s / 3 s / 8 s backoff inside a time budget.

### Suggestions
- Accept more billing countries for Token Factory, or let hackathon participants redeem credits
  without a billing profile.
- Publish a latency SLO, or return a queueing signal (for example a header), so clients can choose
  timeouts and retries sensibly.
- List "JSON mode: no, function calling: yes" clearly per model in the catalog, with a short example
  of structured output through forced tool calls.

## NVIDIA Nemotron models

### What worked well
- Nemotron 3 Ultra was fast for its size (0.7 s for a short forced tool call in our probe) and a
  strong independent juror next to Lightning.
- Turning reasoning on or off per request with `chat_template_kwargs: {"enable_thinking": ...}` let
  us tune each pipeline step separately.

### Problems we hit
- 2026-10-17, Lightning, reasoning on (the default): reasoning for an 8-source evidence prompt used
  about 3,600–4,100 of 4,096 output tokens before the forced `submit` tool call, so calls were often
  cut off (`finish_reason=length`). `enable_thinking: false` fixed it: 455 tokens and 1.8 s instead
  of about 13 s. A `/no_think` system prompt did not work.
- 2026-10-17, Lightning, reasoning off: a source containing double quotes (a quoted astronaut
  sentence) made the model break its JSON string while copying the quote, then emit whitespace until
  `max_tokens` (3 of 5 runs). The server-side tool-call parser then returned no tool call, only raw
  `<tool_call>` text in `content`. We now turn `"` into `'` in source text sent to the model.
- 2026-10-17, Lightning, reasoning off: it sometimes added claims the input never made (for example
  a counter-claim). Reasoning on for that short step fixed it in 9 of 9 runs.
- 2026-10-19, Lightning, reasoning off: asked to assess 8 numbered sources in one forced tool call,
  it often returned an item for source 1 only (2 of 2 claims in our test), silently dropping the
  rest. Naming the exact ids and count in the prompt ("one item per source id, for all 8 sources
  (1, 2, ..., 8)") fixed it: 8 of 8 items in 10 of 10 later calls.
- 2026-10-19, Lightning, reasoning on for the same 8-source step: 30–46 s and 6,700–9,800 output
  tokens per call (vs 2–3 s and about 500 tokens with reasoning off), with no better stances on our
  test sets, so we keep it off for this step.

### Suggestions
- Document how reasoning tokens count toward `max_tokens` when `tool_choice` is forced.
- Offer a way to cap reasoning tokens separately from the answer.
- Make the tool-call parser more robust to quotes inside JSON strings, or return a clear parse error
  instead of raw `<tool_call>` text.

## Nebius AI Cloud

- Billing signup worked from Qatar (see above), and we prepared scripts for a CPU Serverless
  Endpoint (`deploy/`). In the end we hosted the web app on Vercel, so we have no further feedback
  on AI Cloud hosting. All inference still runs on Token Factory.
