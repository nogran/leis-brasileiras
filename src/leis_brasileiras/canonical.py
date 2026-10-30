"""Observed legislation from intact evidence; no legal consolidation or editorial repair."""
from collections import OrderedDict
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .catalog import by_sigla
from .evidence import OBSERVATION_CONTRACT, observation, seal, text_digest
from .models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION
from .reconciliation import reconcile, source_article_census
from .source_map import decode_source, html_map, text_map

ARTICLE = re.compile(r"^Art\s*\.?(?:\s*\.)?\s*(\d+(?:\.\d{3})*)(?:\s*[-–]\s*([A-Z]+)(?![A-Za-z])|([A-Z]+)(?![A-Za-z]))?(?=[.\sº°o-]|$)")
# A following inline fragment that is only more digits, not a word or an inciso.
_DIGIT_TAIL = re.compile(r"^(\d+)[.º°o]?$")
HEADING = re.compile(r"^(?:LIVRO|TÍTULO|TITULO|SUBTÍTULO|CAPÍTULO|CAPITULO|SEÇÃO|SECAO|SUBSEÇÃO)\b")
ANNEX = re.compile(r"^ANEXO(?:\s+([IVXLCDM]+|\d+))?(?:\s|$)")
ADCT = "ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS"


def _joined_split_number(items):
    """Join an article number split across adjacent inline text.

    `Art. 5` and `7.` in successive spans are the digits of Art. 57. The join
    runs only when the first fragment is the label alone. A fragment that
    already continues into words stays as written. This does not invent a
    number or choose vigência.
    """
    parts = [re.sub(r"\s+", " ", item["text"]).strip() for item in items]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return None
    match = ARTICLE.match(parts[0])
    tail = _DIGIT_TAIL.fullmatch(parts[1])
    if not match or not tail or parts[0][match.end():].strip():
        return None
    suffix = match[2] or match[3]
    number = match[1].replace(".", "") + tail[1]
    if suffix:
        number += "-" + suffix
    label = "Art. " + match[1].replace(".", "") + tail[1]
    if suffix:
        label += "-" + suffix
    return label, number


def _blocks(source, mapping):
    """Keep evidence intact, but expose explicit br boundaries within DOM blocks.

    The evidence lists store elements and texts separately. A traversal of the same
    pinned DOM parser recovers their interleaving without changing paths or nodes.
    Whole named headings retain their multi-line context.
    """
    epochs = {}
    if isinstance(source, bytes):
        decoded, _ = decode_source(source, mapping["encoding"])
        soup = BeautifulSoup(decoded, "html.parser")
        records = iter(mapping["texts"])
        epoch = 0
        for node in soup.descendants:
            if isinstance(node, Tag) and node.name == "br":
                epoch += 1
            elif isinstance(node, NavigableString):
                record = next(records)
                if record["text"] != str(node):
                    raise ValueError("DOM traversal does not reproduce evidence")
                epochs[record["id"]] = epoch
        if next(records, None) is not None:
            raise ValueError("DOM traversal leaves evidence unvisited")
    grouped = []
    for item in mapping["texts"]:
        if item["kind"] == "content":
            key = item["block"] or item["path"]
            if not grouped or grouped[-1][0] != key:
                grouped.append((key, []))
            grouped[-1][1].append(item)
    blocks = []
    for path, items in grouped:
        normalized = re.sub(r"\s+", " ", "".join(item["text"] for item in items)).strip()
        if normalized == ADCT or HEADING.match(normalized) or ANNEX.match(normalized):
            blocks.append((path, items))
            continue
        prior = None
        for item in items:
            epoch = epochs.get(item["id"], 0)
            if prior != epoch:
                # A split block uses its first text path as the capture-local locator.
                blocks.append((item["path"] if prior is not None else path, []))
                prior = epoch
            blocks[-1][1].append(item)
    return blocks


def _rubric_boundaries(blocks, mapping):
    """Find closed, wholly bold runs that precede an article in a broken block flow.

    Typography only: the run joins the article identified by the following label.
    It does not create an article number absent from the source, and it does not
    decide vigência. Ordinary paragraph rubrics remain for later review. A flow
    contains consecutive labels outside DOM blocks or exposed by br splits, plus
    its closing boundary. A single orphan label is insufficient. Bold emphasis,
    tables, and open wrappers are not boundaries.
    """
    bold_texts = {}
    for item in mapping["texts"]:
        if item["kind"] == "content" and item["text"].strip():
            for match in re.finditer(r"/(?:b|strong)\[\d+\]", item["path"]):
                bold_texts.setdefault(item["path"][:match.end()], set()).add(item["id"])
    normalized = [re.sub(r"\s+", " ", "".join(item["text"] for item in items)).strip()
                  for _, items in blocks]
    flow_labels = set()
    run = []
    for index, ((path, items), text) in enumerate(zip(blocks, normalized)):
        if ARTICLE.match(text):
            if items[0]["block"] is None or path != items[0]["block"]:
                run.append(index)
            else:
                if len(run) > 1:
                    flow_labels.update(run)
                run = []
    if len(run) > 1:
        flow_labels.update(run)
    previous_flow = []
    last_flow = False
    for index, text in enumerate(normalized):
        previous_flow.append(last_flow)
        if ARTICLE.match(text):
            last_flow = index in flow_labels
    boundaries = set()
    next_label = False
    next_flow = False
    for index in range(len(blocks) - 1, -1, -1):
        text = normalized[index]
        if not text:
            continue
        items = [item for item in blocks[index][1] if item["text"].strip()]
        ids = {item["id"] for item in items}
        if (next_label and (next_flow or previous_flow[index]) and not any(item["table"] for item in items)
                and not (ARTICLE.match(text) or HEADING.match(text) or ANNEX.match(text) or text == ADCT)):
            for match in re.finditer(r"/(?:b|strong)\[\d+\]", items[0]["path"]):
                if bold_texts[items[0]["path"][:match.end()]] == ids:
                    boundaries.add(index)
                    break
        next_label = bool(ARTICLE.match(text))
        next_flow = index in flow_labels
    return boundaries


def extract_document(source: bytes | str, law: str, observed_at: str, *,
                     precision: str = "timestamp", raw_sha256=None,
                     prior_redactions=None) -> dict:
    """Bytes are captured HTML; strings are incomplete historical derivations.

    The source-order transcript is NOT a consolidated reading. Mixed markings have
    no single text; callers retrieve fragments or occurrences explicitly.
    A detached hash cannot promote derived text into primary evidence.
    """
    entry = by_sigla(law)
    if entry is None:
        raise ValueError("Unknown law")
    if raw_sha256 is not None or prior_redactions is not None:
        raise ValueError("Supply captured bytes, not detached hashes or redactions")
    observed = observation(observed_at, precision)
    mapping = html_map(source, entry.get("parse", {}).get("encoding")) if isinstance(source, bytes) else text_map(source)
    blocks = _blocks(source, mapping)
    rubric_boundaries = _rubric_boundaries(blocks, mapping)
    units, components = OrderedDict(), OrderedDict()
    component = "main"
    current = None
    reading = None
    hierarchy = []
    pending = []

    def start(kind, label, locator, path):
        nonlocal current, reading
        component_id = f"{entry['public_id']}!{component}"
        components.setdefault(component_id, {"id": component_id, "label": component, "parent_id": entry["public_id"]})
        identity = f"{component_id}/{locator}"
        current = units.setdefault(identity, {"id": identity, "parent_id": component_id,
            "locator": f"{component}/{locator.removeprefix('art-')}", "kind": kind,
            "label": label, "order": len(units) + 1, "readings": [],
            "legal_validity": "unknown", "text": None, "text_sha256": None})
        reading = {"id": f"{identity}/occurrence-{len(current['readings']) + 1}",
                   "source_order": path, "evidence_ids": [], "source_text": "", "text": None,
                   "text_sha256": None, "hierarchy": list(hierarchy), "source_statements": [],
                   "dates": [], "mixed_markings": False}
        current["readings"].append(reading)

    def consume(chunk):
        for item in chunk:
            reading["evidence_ids"].append(item["id"])
            reading["source_text"] += item["text"]
            # Mentions are literal observations, not conclusions about the container.
            for marker in re.finditer(r"\b(?:revogad[oa]s?|vetad[oa]s?|suprimid[oa]s?|cancelad[oa]s?)\b", item["text"], re.I):
                reading["source_statements"].append({"literal": marker[0], "evidence_id": item["id"],
                    "start": marker.start(), "end": marker.end(), "target": None})

    def release_pending():
        nonlocal pending
        if not pending:
            return
        captured = pending
        pending = []
        start("unclassified", "", "unclassified-" + text_digest(captured[0]["path"])[:16], captured[0]["path"])
        consume(captured)

    for index, (path, items) in enumerate(blocks):
        literal = "".join(item["text"] for item in items)
        normalized = re.sub(r"\s+", " ", literal).strip()
        match = ARTICLE.match(normalized)
        if pending and not match and (normalized == ADCT or ANNEX.match(normalized) or HEADING.match(normalized)):
            release_pending()
        if normalized == ADCT:
            component, hierarchy = "adct", []
            start("heading", normalized, "heading-" + text_digest(path)[:16], path)
        elif ANNEX.match(normalized):
            component = "annex-" + text_digest(path)[:16]
            hierarchy = []
            start("annex", normalized, "heading", path)
        elif (joined := _joined_split_number(items)):
            label, number = joined
            start("article", label, "art-" + number, path)
            consume(pending)
            pending = []
        elif match:
            suffix = match[2] or match[3]
            number = match[1].replace(".", "") + ("-" + suffix if suffix else "")
            start("article", match[0].rstrip(), "art-" + number, path)
            consume(pending)
            pending = []
        elif HEADING.match(normalized):
            hierarchy = [{"text": literal, "evidence_ids": [item["id"] for item in items]}]
            start("heading", normalized, "heading-" + text_digest(path)[:16], path)
        elif index in rubric_boundaries:
            pending.extend(items)
            continue
        elif pending:
            pending.extend(items)
            continue
        elif current is None:
            start("unclassified", "", "unclassified-" + text_digest(path)[:16], path)
        consume(items)
    release_pending()
    by_id = {item["id"]: item for item in mapping["texts"]}
    if not any(unit["kind"] == "article" for unit in units.values()):
        raise ValueError("No legislative articles identified; retain raw source for diagnosis")
    for unit in units.values():
        for occurrence in unit["readings"]:
            marks = {bool(by_id[key]["struck_by"]) for key in occurrence["evidence_ids"] if by_id[key]["text"].strip()}
            occurrence["mixed_markings"] = len(marks) > 1
            occurrence["text_sha256"] = text_digest(occurrence["source_text"])
            if not occurrence["mixed_markings"]:
                occurrence["text"] = occurrence["source_text"]
        unit["quality"] = "ambiguous" if len(unit["readings"]) > 1 or any(r["mixed_markings"] for r in unit["readings"]) else "observed"
        if unit["quality"] == "observed":
            unit["text"] = unit["readings"][0]["text"]
            unit["text_sha256"] = text_digest(unit["text"])
    census = source_article_census(source, mapping["encoding"]) if isinstance(source, bytes) else None
    result = {"format": CANONICAL_FORMAT, "observation_contract": OBSERVATION_CONTRACT,
        "law": {"id": entry["public_id"], "aliases": [law]},
        "provenance": {"source_url": entry["url"], "observation": observed,
            "basis": "source-html" if isinstance(source, bytes) else "historical-clean-text",
            "raw_sha256": mapping["raw_sha256"], "parser_version": CANONICAL_PARSER_VERSION},
        "components": list(components.values()), "units": list(units.values()), "evidence": mapping,
        "reconciliation": reconcile(mapping, list(units.values()), census)}
    return seal(result)
