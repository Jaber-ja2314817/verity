Task: Decide the verdict for the claim using ONLY the evidence below. Each evidence item is
[id | stance toward the claim | domain | reliability tier | published date if known] title,
then a verified quote and a short note.

Labels:
- TRUE: reliable evidence clearly supports the claim as stated, including its key part.
- FALSE: reliable evidence clearly contradicts the claim. Myths, hoaxes and misconceptions that
  reliable sources debunk are FALSE, not UNVERIFIED.
- MISLEADING: partly true, but missing context that changes what a reader would conclude,
  exaggerated, cherry-picked, or outdated. NOT for technicalities that leave the main point
  intact (e.g. a prize dated by its prize year vs. its ceremony year, normal rounding, an
  informal name).
- UNVERIFIED: evidence is weak, conflicting, or does not address the key part of the claim.

Guidance:
- Reliability: "high" (official statistics, peer-reviewed research, encyclopedias, major news)
  outweighs "low" (blogs, forums, content farms); "unknown" is neutral, so judge the quote.
  Several independent sources agreeing is stronger than one. A source that only repeats the
  claim is weak.
- Judge the claim as an ordinary reader means it. If its main point is correct, it is TRUE.
  A rare exception, exotic lab result or edge case does not make a general statement FALSE
  (e.g. "water freezes at 0 °C" stays TRUE despite supercooling experiments);
  mention it, and use MISLEADING only if it changes what a reader would conclude.
- Numbers: approximate wording is TRUE when the real value is close ("about 3 million" for
  2.9 million). A clearly wrong number, date, name or place makes the claim FALSE, or
  MISLEADING if the main point survives.
- "First", "only", "largest": the evidence must back that exact part; a reliable, ordinary
  counterexample makes the claim FALSE (e.g. a reliable source naming an earlier "first").
- Time: use today's date from the system prompt and the published dates. Prefer the newest
  reliable evidence for anything that changes over time. A claim stated as current but no longer
  true (e.g. a former office holder called the current one) is FALSE; one that is outdated in a
  way that changes the conclusion is MISLEADING.
- Partial evidence: if the evidence confirms only a side detail but not the key part, choose
  UNVERIFIED, not TRUE.
- Absence of evidence is not refutation: sources that simply do not mention something make it
  UNVERIFIED, not FALSE. FALSE needs evidence against the claim.
- The stance tag is a quick first guess by a smaller model. Read each quote yourself and trust
  the quote over the tag (e.g. a quote giving 120 km refutes "300 km long" even if tagged
  "supports").
- confidence (0-100) = how sure you are of the label given this evidence.
- explanation: max 90 words, plain language, mention the key evidence. Write in language "{language}".
- cited_source_ids: ids of the evidence items you relied on (must be ids from the evidence).
- missing_evidence_queries: if you chose UNVERIFIED or the evidence is weak or conflicting, up
  to 2 specific search queries that would settle it; otherwise [].

<claim>
{claim}
</claim>

<evidence>
{evidence}
</evidence>
