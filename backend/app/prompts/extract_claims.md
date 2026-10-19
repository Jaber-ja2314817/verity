Task: Split the input into atomic factual claims that can be checked against public sources.

Rules:
- A claim must be a factual statement about the world (numbers, events, dates, scientific facts,
  quotes, rankings). Opinions, predictions, questions and jokes are NOT checkworthy.
- Rewrite each claim so it stands alone: replace pronouns with names, include dates/places
  mentioned in the input. Keep the original meaning. Max 30 words.
- Keep every qualifier exactly as stated: numbers, units, "about", "first", "only",
  "most", time words ("now", "in 2020") and who said it. They decide the verdict.
- Extract ONLY claims the input itself makes. Never add claims from your own knowledge:
  no corrections, counter-claims, background facts or related claims. A one-sentence input
  usually has exactly one claim. Do not judge whether a claim is true here.
- Questions: people often ask instead of stating. Turn a yes/no or either/or question into the
  statement it asks about and check it (checkworthy=true), e.g. "Is the Earth flat or round?"
  -> "The Earth is flat."; "Did NASA fake the Moon landing?" -> "NASA faked the Moon landing.".
  For a question about rumors or reports, check the event itself: "Are there rumors that X
  bought Y?" -> "X bought Y.". Open questions (who/what/when/how many) have no claim to check:
  checkworthy=false, reason "Open question - rephrase it as a statement".
- Merge duplicates. Order by importance (most central claim first).
- Return at most {max_claims_plus_two} claims. Set checkworthy=false with a short reason for
  ones that can't be checked.
- language = ISO 639-1 code of the input.

<input>
{text}
</input>
