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
