import re
import unicodedata


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[^\w\s]", " ", s)  # drop punctuation
    return re.sub(r"\s+", " ", s).strip()


def verify_quote(quote: str, source_text: str, min_words: int = 6) -> bool:
    q = normalize(quote)
    if len(q.split()) < min_words:
        return False
    return q in normalize(source_text)
