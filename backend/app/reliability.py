"""Deterministic domain reliability tiers. A small curated list, not a judgement of every site:
unlisted domains are "unknown", which is neutral."""

from urllib.parse import urlsplit

from .schemas import Reliability

HIGH = frozenset(
    {
        # intergovernmental and public bodies outside .gov/.int
        "un.org", "europa.eu", "oecd.org", "worldbank.org", "imf.org", "canada.ca",
        "ourworldindata.org", "nobelprize.org",
        # science, medicine, reference
        "nature.com", "science.org", "sciencemag.org", "thelancet.com", "nejm.org", "bmj.com",
        "jamanetwork.com", "cell.com", "pnas.org", "plos.org", "springer.com", "wiley.com",
        "sciencedirect.com", "cochranelibrary.com", "royalsocietypublishing.org",
        "mayoclinic.org", "hopkinsmedicine.org", "britannica.com", "wikipedia.org",
        # wire services and major newsrooms
        "reuters.com", "apnews.com", "ap.org", "afp.com", "bbc.com", "bbc.co.uk", "npr.org",
        "pbs.org", "nytimes.com", "washingtonpost.com", "wsj.com", "ft.com", "economist.com",
        "theguardian.com", "bloomberg.com",
        # established fact-checkers
        "snopes.com", "politifact.com", "factcheck.org", "fullfact.org", "leadstories.com",
        "healthfeedback.org", "sciencefeedback.co", "africacheck.org", "chequeado.com",
        "maldita.es", "correctiv.org", "poynter.org",
    }
)  # fmt: skip

MEDIUM = frozenset(
    {
        "cnn.com", "nbcnews.com", "cbsnews.com", "abcnews.go.com", "foxnews.com", "usatoday.com",
        "latimes.com", "theatlantic.com", "newyorker.com", "newsweek.com", "time.com",
        "forbes.com", "cnbc.com", "politico.com", "politico.eu", "axios.com", "thehill.com",
        "vox.com", "slate.com", "huffpost.com", "businessinsider.com", "independent.co.uk",
        "telegraph.co.uk", "thetimes.co.uk", "news.sky.com", "dw.com", "france24.com",
        "lemonde.fr", "spiegel.de", "aljazeera.com", "abc.net.au", "cbc.ca", "scmp.com",
        "japantimes.co.jp", "nationalgeographic.com", "scientificamerican.com",
        "newscientist.com", "smithsonianmag.com", "livescience.com", "space.com",
        "history.com", "healthline.com", "webmd.com", "clevelandclinic.org", "statista.com",
        "investopedia.com", "arxiv.org", "theverge.com", "wired.com", "arstechnica.com",
        "techcrunch.com", "nypost.com", "theconversation.com",
    }
)  # fmt: skip

LOW = frozenset(
    {
        # social, video, forums, Q&A, user-generated
        "reddit.com", "quora.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
        "threads.net", "tiktok.com", "youtube.com", "youtu.be", "pinterest.com", "tumblr.com",
        "linkedin.com", "t.me", "4chan.org", "rumble.com", "bitchute.com", "medium.com",
        "substack.com", "blogspot.com", "wordpress.com", "wixsite.com", "weebly.com",
        "sites.google.com", "fandom.com", "answers.com", "answers.yahoo.com", "wikihow.com",
        "ehow.com", "brainly.com", "chegg.com", "coursehero.com", "quizlet.com", "scribd.com",
        # known misinformation outlets
        "naturalnews.com", "infowars.com", "beforeitsnews.com", "globalresearch.ca",
        "thegatewaypundit.com",
    }
)  # fmt: skip

TIERS: dict[str, Reliability] = (
    {d: "low" for d in LOW} | {d: "medium" for d in MEDIUM} | {d: "high" for d in HIGH}
)

# Government, military, education and intergovernmental TLDs (.gov, .gov.uk, .gouv.fr, .ac.jp, ...)
OFFICIAL_TLDS = frozenset({"gov", "mil", "edu", "int"})
OFFICIAL_SLDS = frozenset({"gov", "mil", "edu", "ac", "gouv", "gob", "go", "govt", "gc"})


def _host(domain: str) -> str:
    domain = domain.strip().lower()
    if "/" in domain:
        domain = urlsplit(domain if "//" in domain else f"//{domain}").hostname or ""
    domain = domain.split(":")[0].rstrip(".")
    return domain[4:] if domain.startswith("www.") else domain


def domain_reliability(domain: str) -> Reliability:
    """Tier of a domain or URL. The longest listed suffix wins on whole labels
    (en.wikipedia.org -> wikipedia.org; notreuters.com does not match reuters.com)."""
    labels = _host(domain).split(".")
    if len(labels) < 2 or not all(labels):
        return "unknown"
    for i in range(len(labels) - 1):
        tier = TIERS.get(".".join(labels[i:]))
        if tier:
            return tier
    tld, sld = labels[-1], labels[-2]
    if tld in OFFICIAL_TLDS or (len(tld) == 2 and sld in OFFICIAL_SLDS):
        return "high"
    return "unknown"
