"""Independent lexical source census. Never imports the legislative segmenter."""
from html.parser import HTMLParser
import re

from .evidence import structured_digest
from .source_map import decode_source


class ArticleCensus(HTMLParser):
    """A second traversal (stdlib HTMLParser, not the evidence DOM) counts labels."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.pending = []
        self.ignored = []

    def flush(self):
        if self.pending:
            self.blocks.append("".join(self.pending))
            self.pending = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored.append(tag)
        if not self.ignored and tag in {"p", "br", "div", "td", "th", "li", "blockquote",
                                        "pre", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.flush()

    def handle_endtag(self, tag):
        if tag in self.ignored:
            self.ignored.remove(tag)
        if not self.ignored and tag in {"p", "div", "td", "th", "li", "blockquote",
                                        "pre", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.flush()

    def handle_data(self, data):
        if not self.ignored:
            self.pending.append(data)


def source_article_census(raw: bytes, encoding: str | None = None) -> dict:
    text, _ = decode_source(raw, encoding)
    reader = ArticleCensus()
    reader.feed(text)
    reader.close()
    reader.flush()
    component = "main"
    identities = set()
    occurrences = []
    for block in reader.blocks:
        normalized = re.sub(r"\s+", " ", block).strip()
        if normalized == "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS":
            component = "adct"
        match = re.match(r"Art[\s.]*([0-9]+(?:\.[0-9]{3})*)(?:\s*[-–]\s*([A-Z]+)(?![A-Za-z])|([A-Z]+)(?![A-Za-z]))?(?=[.\sº°o-]|$)", normalized)
        if match:
            suffix = match[2] or match[3]
            number = match[1].replace(".", "") + ("-" + suffix if suffix else "")
            key = component + "/" + number
            identities.add(key)
            occurrences.append(key)
    return {"identities": sorted(identities), "occurrences": occurrences,
            "method": "stdlib-htmlparser-block-break-labels@2"}


def reconcile(source_map: dict, units: list[dict], census: dict | None) -> dict:
    expected = {entry["id"] for entry in source_map["texts"] if entry["kind"] == "content"}
    assigned = []
    unclassified = []
    for unit in units:
        for reading in unit["readings"]:
            assigned.extend(reading["evidence_ids"])
        if unit["kind"] == "unclassified":
            unclassified.append(unit["id"])
    identities = sorted({unit["locator"] for unit in units if unit["kind"] == "article"})
    discrepancies = []
    if set(assigned) != expected or len(assigned) != len(set(assigned)):
        discrepancies.append("text_coverage_mismatch")
    missing = sorted(set(census["identities"]) - set(identities)) if census else []
    extra = sorted(set(identities) - set(census["identities"])) if census else []
    if missing or extra:
        discrepancies.append("independent_article_census_mismatch")
    if census is None:
        discrepancies.append("raw_source_unavailable")
    if unclassified:
        discrepancies.append("unclassified_content")
    if source_map.get("undecoded_tail_hex"):
        discrepancies.append("undecodable_source_bytes")
    # A label census does not prove correct boundaries, table semantics or note targets.
    discrepancies.append("structural_boundary_review_required")
    result = {"source_identities": census["identities"] if census else None,
              "structured_identities": identities, "missing_identities": missing,
              "extra_identities": extra, "source_occurrences": census["occurrences"] if census else None,
              "unmapped_evidence_ids": sorted(expected - set(assigned)),
              "unclassified_units": unclassified, "discrepancies": discrepancies,
              "preservation": "mapped" if set(assigned) == expected and len(assigned) == len(set(assigned)) else "incomplete",
              "structure": "incomplete", "complete": False,
              "census_method": census["method"] if census else None}
    result["report_sha256"] = structured_digest(result)
    return result
