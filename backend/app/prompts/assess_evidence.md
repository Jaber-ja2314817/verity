Task: For EACH source, decide whether it supports or refutes the claim.

For every source id, return:
- stance: "supports" | "refutes" | "mixed" | "irrelevant"
- quote: ONE sentence copied EXACTLY, word for word, from that source that best shows the stance.
  Do not paraphrase, do not fix typos, do not merge sentences. Use "" if stance is "irrelevant".
- note: max 20 words.

Judge only what the source text says. A source that merely repeats the claim without evidence
is weak; say so in the note.

<claim>
{claim}
</claim>

{sources}
