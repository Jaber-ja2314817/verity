import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from difflib import SequenceMatcher


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s]", " ", s)  # drop punctuation
    return re.sub(r"\s+", " ", s).strip()


GAP = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]")  # "[...]" joins passages that are not adjacent


def verify_quote(quote: str, source_text: str, min_words: int = 6) -> bool:
    """True if the quote's words appear, in order, inside one passage of the source: a quote
    may not run across a "[...]" gap, since that text is not contiguous on the page."""
    q = normalize(quote)
    if len(q.split()) < min_words:
        return False
    return any(q in normalize(part) for part in GAP.split(source_text))


# ---- quote recovery ----
# Small models copy quotes almost, but not exactly: "1000" for "1,000", a dropped "the", two
# passages glued across "[...]". find_quote maps such a quote back to the exact source text,
# always within one passage. Any difference that could change the meaning (a number, a
# negation, a content word) means no match: the shown quote is always source text, never the
# model's version.

_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+")
_ELLIPSIS = re.compile(rf"{GAP.pattern}|\.{{3,}}|…")  # where a model's quote skips text
_SENTENCE_END = re.compile(r"[.!?]+[\"'”’)\]]*(?=\s)|\n")
NEGATIONS = frozenset("not no never nor neither none nobody nothing nowhere cannot without".split())
CONTRACTED = {"can": "can", "won": "will", "shan": "shall"}  # stems of can't, won't, shan't
FILLER = frozenset(
    "a an the this that these those and also of to in on at for by with as from "
    "is are was were be been it its s which who very just percent per cent".split()
)  # words a quote may drop or add without changing its meaning
ARTICLES = frozenset("a an the this that these those".split())
MIN_RATIO = 0.8  # token similarity between the model's quote and the source span
MAX_SENTENCE_WORDS = 50  # a match grows to its whole sentence(s) up to this many words


@dataclass
class _Indexed:
    text: str  # NFC form of the source; spans index into it
    words: list[str]
    spans: list[tuple[int, int]]
    unit: list[int]  # sentence number of each word (sentences never cross a gap)
    chunk: list[int]  # passage number of each word, between "[...]" gaps


def _word(raw: str) -> str:
    w = unicodedata.normalize("NFKC", raw).lower()
    return re.sub(r",(?=\d{3}(?!\d))", "", w)  # 1,000 -> 1000; 2.5 and 2,5 stay as they are


def _uncontract(words: list[str]) -> list[str]:
    """isn't -> is not, can't -> can not: the tokens "isn", "t" become "is", "not"."""
    out = list(words)
    for i in range(1, len(out)):
        if out[i] == "t" and out[i - 1].endswith("n") and len(out[i - 1]) > 2:
            out[i - 1], out[i] = CONTRACTED.get(out[i - 1], out[i - 1][:-1]), "not"
    return out


def _words(text: str) -> list[str]:
    raw = [_word(m.group()) for m in _TOKEN.finditer(unicodedata.normalize("NFC", text))]
    return _uncontract(raw)


def _index(source_text: str) -> _Indexed:
    text = unicodedata.normalize("NFC", source_text)
    matches = list(_TOKEN.finditer(text))
    chunk_cuts = [m.end() for m in GAP.finditer(text)]
    cuts = sorted(chunk_cuts + [m.end() for m in _SENTENCE_END.finditer(text)])
    return _Indexed(
        text=text,
        words=_uncontract([_word(m.group()) for m in matches]),
        spans=[m.span() for m in matches],
        unit=[bisect_right(cuts, m.start()) for m in matches],
        chunk=[bisect_right(chunk_cuts, m.start()) for m in matches],
    )


def _quote_parts(quote: str) -> list[str]:
    """The whole quote, then its pieces around "..." / "[...]", longest first."""
    parts = [p for p in _ELLIPSIS.split(quote) if p.strip()]
    return [quote] + sorted(parts, key=len, reverse=True) if len(parts) > 1 else [quote]


def _negations(words: list[str]) -> list[str]:
    return sorted(w for w in words if w in NEGATIONS)


def _variant(x: str, y: str) -> bool:
    """Spelling variants (colour/color, visible/visibly), not antonyms (careful/careless)."""
    if not (x.isalpha() and y.isalpha()) or min(len(x), len(y)) < 5 or x[:3] != y[:3]:
        return False
    if x.endswith("less") != y.endswith("less"):
        return False
    return SequenceMatcher(None, x, y).ratio() >= 0.8


def _minor(a: list[str], b: list[str]) -> bool:
    """True if quote words a in place of source words b cannot change the meaning."""
    if a and b and "".join(a) == "".join(b):
        return True  # "1 000" vs "1000", "long term" vs "longterm"
    words = a + b
    if NEGATIONS.intersection(words) or any(c.isdigit() for w in words for c in w):
        return False
    if not a or not b:
        return FILLER.issuperset(words)
    if len(a) == len(b) == 1:
        return _variant(a[0], b[0]) or ARTICLES.issuperset(words)
    return False


def _similarity(q: list[str], span: list[str]) -> float:
    """Token similarity of q and span, or 0 if any difference between them is not minor."""
    sm = SequenceMatcher(None, q, span, autojunk=False)
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag != "equal" and not _minor(q[a0:a1], span[b0:b1]):
            return 0.0
    return sm.ratio()


def _exact(q: list[str], src: _Indexed) -> tuple[int, int] | None:
    n = len(q)
    for i in range(len(src.words) - n + 1):
        if src.words[i : i + n] == q and src.chunk[i] == src.chunk[i + n - 1]:
            return i, i + n
    return None


def _units(src: _Indexed) -> list[tuple[int, int]]:
    """Word index ranges of each sentence."""
    bounds = [i for i in range(len(src.words)) if i == 0 or src.unit[i] != src.unit[i - 1]]
    return list(zip(bounds, bounds[1:] + [len(src.words)], strict=True))


def _near(q: list[str], src: _Indexed, min_words: int) -> tuple[int, int] | None:
    """Best span within 1-3 consecutive sentences that differs from q only in minor ways."""
    units = _units(src)
    best, best_score = None, MIN_RATIO
    for k in range(len(units)):
        for lo, hi in ((units[k][0], units[min(k + n, len(units)) - 1][1]) for n in (1, 2, 3)):
            if src.chunk[lo] != src.chunk[hi - 1]:
                break
            sm = SequenceMatcher(None, q, src.words[lo:hi], autojunk=False)
            blocks = [b for b in sm.get_matching_blocks() if b.size]
            if not blocks:
                continue
            i, j = lo + blocks[0].b, lo + blocks[-1].b + blocks[-1].size
            score = _similarity(q, src.words[i:j]) if j - i >= min_words else 0.0
            if score > best_score:
                best, best_score = (i, j), score
    return best


def _pieces(sm: SequenceMatcher, src: _Indexed) -> list[tuple[int, int, int]]:
    """Matching blocks (q start, source start, size), cut where they cross a "[...]" gap."""
    out = []
    for blk in sm.get_matching_blocks():
        a, b, end = blk.a, blk.b, blk.b + blk.size
        while b < end:
            stop = b
            while stop < end and src.chunk[stop] == src.chunk[b]:
                stop += 1
            out.append((a, b, stop - b))
            a, b = a + stop - b, stop
    return out


def _glued(q: list[str], src: _Indexed, min_words: int) -> tuple[int, int] | None:
    """q joins text from different passages, which often overlap ("seen with the [...] seen
    with the naked eye"). Return q's longest piece within one passage that keeps all of q's
    negations, so the shown quote never runs across a gap."""
    sm = SequenceMatcher(None, q, src.words, autojunk=False)
    pieces = [p for p in _pieces(sm, src) if p[2] >= 3]
    covered = {i for a, _, n in pieces for i in range(a, a + n)}
    if len(pieces) < 2 or not FILLER.issuperset(w for i, w in enumerate(q) if i not in covered):
        return None
    pairs = zip(pieces, pieces[1:], strict=False)
    if any(src.chunk[x[1] + x[2] - 1] == src.chunk[y[1]] for x, y in pairs):
        return None  # a gap inside one passage means the model skipped real text
    keep = [
        p
        for p in pieces
        if p[2] >= min_words and _negations(q[p[0] : p[0] + p[2]]) == _negations(q)
    ]
    if not keep:
        return None
    _, start, size = max(keep, key=lambda p: p[2])
    return start, start + size


def _display(src: _Indexed, i: int, j: int) -> str:
    """Source text of words i..j, grown to whole sentences when short, plus adjacent
    punctuation such as $, % or closing quotes."""
    lo, hi = i, j
    while lo > 0 and src.unit[lo - 1] == src.unit[i]:
        lo -= 1
    while hi < len(src.words) and src.unit[hi] == src.unit[j - 1]:
        hi += 1
    if hi - lo <= MAX_SENTENCE_WORDS:
        i, j = lo, hi
    text, start, end = src.text, src.spans[i][0], src.spans[j - 1][1]
    for _ in range(3):
        if start > 0 and _is_punct(text[start - 1]):
            start -= 1
        if end < len(text) and _is_punct(text[end]):
            end += 1
    return " ".join(text[start:end].split())


def _is_punct(c: str) -> bool:
    return not (c.isspace() or c.isalnum())


def find_quote(
    quote: str, source_text: str, min_words: int = 6, min_words_number: int = 4
) -> str | None:
    """Return the exact source text the model's quote stands for, or None if there is none.
    Tries an exact word match, then a near match within a sentence, then glued chunks; for a
    quote with "..." it also tries each piece, longest first. A quote with a number (a table
    row such as "15 April 1912 | sank") may be shorter, but must then match exactly."""
    src = _index(source_text)
    for part in _quote_parts(quote):
        q = _words(part)
        has_number = any(c.isdigit() for w in q for c in w)
        if len(q) < (min_words_number if has_number else min_words):
            continue
        span = _exact(q, src)
        if span is None and len(q) >= min_words:
            span = _near(q, src, min_words) or _glued(q, src, min_words)
        if span:
            text = _display(src, *span)
            if verify_quote(text, source_text, min(len(q), min_words)):  # belt and braces
                return text
    return None
