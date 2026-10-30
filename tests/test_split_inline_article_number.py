"""An article number split across inline spans is one article, not the next reading."""
import gzip
from pathlib import Path

from leis_brasileiras.canonical import extract_document
from leis_brasileiras.reconciliation import source_article_census

WHEN = "2026-10-30T00:00:00+00:00"

SPLIT = """<html><body>
<p>Art. 5. Para os fins desta Lei, considera-se dado pessoal.</p>
<p><span>Art. 5</span><span lang="EN-US">7.</span><span>(VETADO).</span></p>
<p>Art. 58. (VETADO).</p>
</body></html>""".encode()

BODY = b"<html><body><p>Art. 5 Para os fins. 7. item interno.</p></body></html>"

SEPARATE = b"""<html><body>
<p>Art. 5</p>
<p>7. (VETADO).</p>
</body></html>"""


def _locators(raw):
    document = extract_document(raw, "LGPD", WHEN)
    return [unit["locator"] for unit in document["units"] if unit["kind"] == "article"]


def test_inline_digit_span_is_its_own_article():
    document = extract_document(SPLIT, "LGPD", WHEN)
    articles = {unit["locator"]: unit for unit in document["units"] if unit["kind"] == "article"}
    assert set(articles) == {"main/5", "main/57", "main/58"}
    assert articles["main/57"]["label"] == "Art. 57"
    assert articles["main/5"]["quality"] == "observed"
    assert articles["main/57"]["quality"] == "observed"
    assert len(articles["main/5"]["readings"]) == 1
    assert "dado pessoal" in articles["main/5"]["text"]
    assert "(VETADO)" not in articles["main/5"]["text"]
    assert len(articles["main/57"]["readings"]) == 1
    assert "(VETADO)" in articles["main/57"]["text"]
    assert "dado pessoal" not in articles["main/57"]["text"]
    census = source_article_census(SPLIT)
    assert census["identities"] == ["main/5", "main/57", "main/58"]
    assert census["occurrences"].count("main/5") == 1
    assert "main/57" in census["occurrences"]


def test_digits_inside_the_article_body_stay_there():
    assert _locators(BODY) == ["main/5"]
    assert source_article_census(BODY)["identities"] == ["main/5"]


def test_digit_in_the_next_paragraph_is_not_joined():
    assert _locators(SEPARATE) == ["main/5"]
    assert source_article_census(SEPARATE)["identities"] == ["main/5"]


def test_lgpd_fixture_keeps_article_5_and_recognizes_57():
    raw = gzip.decompress((Path(__file__).parents[1] / "tests/fixtures/html/lgpd.htm.gz").read_bytes())
    document = extract_document(raw, "LGPD", "2026-07-07", precision="date")
    articles = {unit["locator"]: unit for unit in document["units"] if unit["kind"] == "article"}
    assert articles["main/5"]["quality"] == "observed"
    assert len(articles["main/5"]["readings"]) == 1
    assert "dado pessoal" in articles["main/5"]["text"]
    assert "(VETADO)" not in articles["main/5"]["text"]
    article = articles["main/57"]
    assert article["label"] == "Art. 57"
    assert article["quality"] == "observed"
    assert len(article["readings"]) == 1
    assert "(VETADO)" in article["text"]
    assert "dado pessoal" not in article["text"]
    assert "Seção II" not in article["text"]
    headings = [unit for unit in document["units"] if unit["kind"] == "heading" and "Conselho Nacional" in (unit.get("text") or "")]
    assert len(headings) == 1
    assert headings[0]["text"].lstrip().startswith("Seção II")
