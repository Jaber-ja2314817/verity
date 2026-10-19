import pytest

from app.reliability import domain_reliability


@pytest.mark.parametrize(
    "domain, tier",
    [
        ("reuters.com", "high"),
        ("www.reuters.com", "high"),
        ("en.wikipedia.org", "high"),
        ("https://en.m.wikipedia.org/wiki/X", "high"),
        ("pubmed.ncbi.nlm.nih.gov", "high"),
        ("www.cdc.gov", "high"),
        ("www.gov.uk", "high"),
        ("ons.gov.uk", "high"),
        ("defense.mil", "high"),
        ("who.int", "high"),
        ("ec.europa.eu", "high"),
        ("mit.edu", "high"),
        ("ox.ac.uk", "high"),
        ("insee.gouv.fr", "high"),
        ("factcheck.afp.com", "high"),
        ("news.bbc.co.uk", "high"),
        ("CNN.com", "medium"),
        ("abcnews.go.com", "medium"),
        ("www.reddit.com", "low"),
        ("x.com", "low"),
        ("someone.blogspot.com", "low"),
        ("sites.google.com", "low"),
        ("notreuters.com", "unknown"),
        ("reuters.com.evil.io", "unknown"),
        ("go.com", "unknown"),
        ("google.com", "unknown"),
        ("example.com", "unknown"),
        ("", "unknown"),
        ("localhost", "unknown"),
    ],
)
def test_domain_reliability(domain, tier):
    assert domain_reliability(domain) == tier
