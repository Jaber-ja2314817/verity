Task: Write {n} web search queries to fact-check the claim.
- One "neutral" query that finds the core facts without assuming the answer (e.g. "how tall
  is the Burj Khalifa", not "Burj Khalifa is 900 metres tall").
- One "support" query that would find evidence the claim is true.
- One "refute" query that would find debunks or contrary evidence (e.g. add "fact check",
  "myth" or "false").
- Use the claim's key names, numbers, dates and places; drop filler words.
- Aim at least one query at authoritative sources: official data, encyclopedias, journals,
  fact-checkers or reputable news.
- If the claim is about recent or current events ("now", "current", "latest", this year), add
  the year {year} or the year the claim mentions.
- Max 12 words each, in English unless the claim is about a local topic best searched in its
  own language.



Also set time_sensitive: true when the claim is about a recent or ongoing event that news
outlets would be reporting on now (an announcement, election, attack, match, market move, a
statement someone made this week). Set it to false for settled facts (history, science,
geography, definitions, long-standing statistics).

<claim>
{claim}
</claim>
