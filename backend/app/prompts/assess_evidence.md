Task: For EVERY source below, decide whether the source ITSELF says the claim is true or false.

<claim>
{claim}
</claim>

{sources}

Each source has reliability="high|medium|low|unknown" and may have published="YYYY-MM-DD".
"[...]" marks text left out between passages.

Return exactly one item per source id, for all {count} sources ({ids}), in that order.

For each source:
- quote: ONE full sentence copied EXACTLY, word for word, from that source, that states the
  source's own position on the claim (prefer the sentence with the key fact, number or date).
  Never paraphrase, fix typos, change numbers, or run a quote across "[...]". "" if irrelevant.
- note: max 20 words: what the source itself concludes, in your words.
- stance, for the claim EXACTLY as worded (its numbers, dates, names and scope):
  - "supports": according to the source, the claim is true.
  - "refutes": according to the source, the claim is false, or the source gives a different
    number, date, name or place (claim "opened in 1931", source "opened in 1937" -> refutes).
  - "mixed": the source itself gives evidence both ways, or says the claim is partly true.
  - "irrelevant": the source says nothing about the claim's fact. A source that rebuts a
    different claim on the same topic (e.g. who or why, when the claim is about when) is
    irrelevant.

Rules:
- Watch the claim's direction. Claim "X cannot Y": a source saying X can Y refutes it; a
  source saying X cannot Y supports it.
- Myth-busting and fact-check pages often restate the claim ("Claim: ...", "Many believe ...",
  "It is a myth that ...", a line from a film or meme). That is not their position: quote and
  judge their own conclusion.
- A source that states the claim as its own view but gives no evidence is "supports", and the
  note must say "weak: no evidence given". A source that only mentions or quotes the claim
  without taking a side is "irrelevant".
- If the claim depends on time (current office holders, latest figures) and the source is
  old, add "possibly outdated" to the note.
- Judge only from the source text, not from memory.
