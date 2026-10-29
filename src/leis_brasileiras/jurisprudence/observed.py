"""Source-bound jurisprudence observations. No synthetic holdings or inferred validity."""
import csv
import io
import json
import re
from collections import OrderedDict

from ..evidence import OBSERVATION_CONTRACT, observation, raw_digest, seal, text_digest
from ..source_map import html_map
from .models import MAX_RECORDS
from .catalog import source

FORMAT = "observed-jurisprudence-v1"
PARSER_VERSION = "observed-jurisprudence@1"


def build_document(identifier, items, observed_at, coverage, pages_by_hash):
    source(identifier)
    records, sources = [], []
    groups = OrderedDict()

    def add(number, location, value, text, source_id, *, fields=None, thesis=None):
        if len(records) >= MAX_RECORDS:
            raise ValueError("Excessive records")
        # Unidentified source material never acquires a fabricated official number.
        identity = (f"br:{identifier}:{number}" if number is not None
                    else f"br:{identifier}:unclassified:{source_id}:{location}")
        occurrence = {"id": f"{identity}/occurrence-{len(groups.get(identity, [])) + 1}",
                      "source_id": source_id, "location": location,
                      "source_record": value, "source_text": text,
                      "text_sha256": text_digest(text), "fields": fields or {},
                      "thesis_presence": thesis,
                      "situation": (fields or {}).get("situacao"),
                      "dates": [{"source_field": key, "literal": val, "value": None, "precision": None}
                                for key, val in (fields or {}).items() if key.startswith("data")],
                      "source_statements": [{"literal": m[0], "start": m.start(), "end": m.end(), "target": None}
                                            for m in re.finditer(r"\b(?:cancelad[oa]s?|revogad[oa]s?|alterad[oa]s?)\b", text, re.I)]}
        groups.setdefault(identity, []).append(occurrence)
        records.append((identity, number))

    for descriptor, raw in items:
        source_id = descriptor["name"]
        item = {"id": source_id, "url": descriptor["url"], "raw_sha256": raw_digest(raw),
                "kind": descriptor["kind"], "request_form": descriptor["form"]}
        kind = descriptor["kind"]
        if kind == "csv":
            from .extraction import decodificar_bytes
            decoded, codec = decodificar_bytes(raw)
            reader = csv.reader(io.StringIO(decoded))
            header = next(reader)
            if len(set(header)) != len(header):
                raise ValueError("Duplicate CSV column")
            rows = list(reader)
            item.update(encoding=codec, header=header, rows=rows)
            for index, row in enumerate(rows):
                if len(row) != len(header):
                    raise ValueError("Malformed CSV row; raw capture must be inspected")
                fields = dict(zip(header, row))
                number = fields.get("sequencialPrecedente") or None
                # Every field is retained verbatim, including unknown columns and notes.
                text = fields.get("teseFirmada", "")
                add(number, f"/rows/{index}", row, text, source_id, fields=fields,
                    thesis=bool(text.strip()))
        elif kind == "json":
            from .extraction import decodificar_bytes
            decoded, codec = decodificar_bytes(raw)
            def unique(pairs):
                value = {}
                for key, field in pairs:
                    if key in value:
                        raise ValueError("Duplicate JSON key")
                    value[key] = field
                return value
            values = json.loads(decoded, object_pairs_hook=unique)
            if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
                raise ValueError("Expected official JSON records")
            item.update(encoding=codec, records=values)
            for index, value in enumerate(values):
                number = value.get("numeroTema")
                if number is not None and not isinstance(number, (str, int)):
                    raise ValueError("Invalid source identity")
                text = value.get("descricaoTese", "")
                if not isinstance(text, str):
                    raise ValueError("Invalid source text")
                add(str(number) if number is not None else None, f"/{index}", value, text,
                    source_id, fields=value, thesis=descriptor["form"] == "com")
        elif kind == "html":
            mapping = html_map(raw)
            item["map"] = mapping
            elements = mapping["elements"]
            if identifier == "stj_sumulas":
                roots = [e["path"] for e in elements if "gridSumula" in e["attributes"].get("class", [])]
            elif identifier == "stf_sumulas_vinculantes" and "&sumula=" in descriptor["url"]:
                roots = [e["path"] for e in elements if e["tag"] == "body"] or [""]
            else:
                roots = []
            for root in roots:
                nodes = [n for n in mapping["texts"] if n["kind"] == "content" and n["path"].startswith(root + "/")]
                transcript = "".join(n["text"] for n in nodes)
                number = None
                if identifier == "stj_sumulas":
                    paths = [e["path"] for e in elements if e["path"].startswith(root + "/")
                             and "numeroSumula" in e["attributes"].get("class", [])]
                    candidate = "".join(n["text"] for n in nodes if any(n["path"].startswith(p + "/") for p in paths)).strip()
                    number = candidate if candidate.isdigit() else None
                else:
                    found = re.search(r"S[úu]mula\s+Vinculante\s+(\d+)", transcript, re.I)
                    number = found[1] if found else None
                add(number, root, {"evidence_ids": [n["id"] for n in nodes]}, transcript, source_id)
            item["unclassified_evidence_ids"] = [
                n["id"] for n in mapping["texts"] if n["kind"] == "content"
                and not any(n["path"].startswith(root + "/") for root in roots)]
        elif kind == "pdf":
            pages = pages_by_hash[raw_digest(raw)]
            item["pages"] = [{"number": i, "text": text, "text_sha256": text_digest(text)}
                             for i, text in enumerate(pages, 1)]
            joined = "\n".join(pages)
            starts = []
            pattern = (r"(?im)^\s*ENUNCIADO\s+0*(\d+)\b" if identifier == "tjmg_sumulas"
                       else r"(?im)^\s*S[úu]mula\s*\n\s*0*(\d+)\b")
            for match in re.finditer(pattern, joined):
                starts.append((match.start(), match[1]))
            for index, (start, number) in enumerate(starts):
                end = starts[index + 1][0] if index + 1 < len(starts) else len(joined)
                # Index entries are retained as occurrences, not silently discarded.
                text = joined[start:end]
                add(number, f"/page-transcript/{start}:{end}", {"start": start, "end": end},
                    text, source_id)
            item["unclassified_prefix"] = joined[:starts[0][0]] if starts else joined
        else:
            raise ValueError("Unsupported source kind")
        sources.append(item)
    unique_records = []
    for identity, number in dict.fromkeys(records):
        related = []
        if identifier == "stf_sumulas_vinculantes":
            detail_urls = {s["url"] for s in sources if s["id"] in {r["source_id"] for r in groups[identity]}}
            for item in sources:
                if item["kind"] != "html" or "&sumula=" in item["url"]:
                    continue
                for element in item["map"]["elements"]:
                    href = str(element["attributes"].get("href", ""))
                    match = re.search(r"[?&]sumula=(\d+)", href)
                    if match and any(url.endswith("&sumula=" + match[1]) for url in detail_urls):
                        related.append({"source_id": item["id"], "path": element["path"]})
        unique_records.append({"id": identity, "number": number, "court": identifier.split("_")[0].upper(),
                               "collection": identifier, "legal_validity": "unknown",
                               "readings": groups[identity], "related_evidence": related})
    if not unique_records:
        raise ValueError("No documentary records identified")
    document = {"format": FORMAT, "observation_contract": OBSERVATION_CONTRACT,
                "parser_version": PARSER_VERSION, "source": identifier,
                "observed_at": observed_at,
                "observation_precision": observation(observed_at, "day" if len(observed_at) == 10 else "instant")["precision"],
                "coverage": coverage, "records": unique_records, "evidence": sources,
                "provenance": {"observation": observation(observed_at, "day" if len(observed_at) == 10 else "instant")},
                "reconciliation": {"complete": False, "structure": "incomplete",
                    "discrepancies": ["field_and_boundary_review_required"],
                    "source_records": len(records), "structured_identities": len(unique_records)}}
    return seal(document)


def validate_observed(value):
    from ..canonical_validation import _bounded
    from ..evidence import verify_seal
    from .provenance import validate_official_url

    _bounded(value)
    if set(value) != {"format", "observation_contract", "parser_version", "source", "observed_at",
                     "observation_precision", "coverage", "records", "evidence", "provenance",
                     "reconciliation", "structured_sha256", "revision"}:
        raise ValueError("Unexpected observation fields")
    if value["format"] != FORMAT or value["parser_version"] != PARSER_VERSION or value["observation_contract"] != OBSERVATION_CONTRACT:
        raise ValueError("Unsupported observation")
    identifier = value["source"]
    source(identifier)
    expected_date = observation(value["observed_at"], value["observation_precision"])
    if value["provenance"] != {"observation": expected_date}:
        raise ValueError("Observation mismatch")
    if value["coverage"] not in {"sample", "source_snapshot"} or not 0 < len(value["records"]) <= MAX_RECORDS:
        raise ValueError("Invalid coverage")
    sources = {}
    for item in value["evidence"]:
        if item["id"] in sources or not re.fullmatch(r"[0-9a-f]{64}", item["raw_sha256"]):
            raise ValueError("Evidence identity")
        validate_official_url(item["url"], identifier.split("_")[0])
        sources[item["id"]] = item
    identities = set()
    total = 0
    for record in value["records"]:
        if set(record) != {"id", "number", "court", "collection", "legal_validity", "readings", "related_evidence"}:
            raise ValueError("Unexpected record fields")
        if (record["id"] in identities or record["court"] != identifier.split("_")[0].upper()
                or record["collection"] != identifier or record["legal_validity"] != "unknown"
                or not record["id"].startswith(f"br:{identifier}:") or not record["readings"]):
            raise ValueError("Record identity")
        identities.add(record["id"])
        for link in record["related_evidence"]:
            item = sources[link["source_id"]]
            if item["kind"] != "html" or not any(e["path"] == link["path"] for e in item["map"]["elements"]):
                raise ValueError("Related evidence does not resolve")
        for index, reading in enumerate(record["readings"], 1):
            if set(reading) != {"id", "source_id", "location", "source_record", "source_text", "text_sha256",
                               "fields", "thesis_presence", "situation", "dates", "source_statements"}:
                raise ValueError("Unexpected occurrence fields")
            total += 1
            item = sources[reading["source_id"]]
            location = reading["location"]
            if reading["id"] != record["id"] + f"/occurrence-{index}":
                raise ValueError("Occurrence identity")
            if item["kind"] == "csv":
                if not re.fullmatch(r"/rows/\d+", location):
                    raise ValueError("Invalid row locator")
                original = item["rows"][int(location.removeprefix("/rows/"))]
                fields = dict(zip(item["header"], original))
                text = fields.get("teseFirmada", "")
                thesis = bool(text.strip())
                source_number = fields.get("sequencialPrecedente") or None
            elif item["kind"] == "json":
                if not re.fullmatch(r"/\d+", location):
                    raise ValueError("Invalid record locator")
                original = item["records"][int(location.removeprefix("/"))]
                fields = original
                text = original.get("descricaoTese", "")
                thesis = item["request_form"] == "com"
                source_number = str(original["numeroTema"]) if original.get("numeroTema") is not None else None
            elif item["kind"] == "html":
                nodes = [n for n in item["map"]["texts"] if n["kind"] == "content"
                         and n["path"].startswith(location + "/")]
                original = {"evidence_ids": [n["id"] for n in nodes]}
                text = "".join(n["text"] for n in nodes)
                fields, thesis = {}, None
                if identifier == "stj_sumulas":
                    paths = [e["path"] for e in item["map"]["elements"] if e["path"].startswith(location + "/")
                             and "numeroSumula" in e["attributes"].get("class", [])]
                    candidate = "".join(n["text"] for n in nodes if any(n["path"].startswith(p + "/") for p in paths)).strip()
                    source_number = candidate if candidate.isdigit() else None
                else:
                    found = re.search(r"S[úu]mula\s+Vinculante\s+(\d+)", text, re.I)
                    source_number = found[1] if found else None
            elif item["kind"] == "pdf":
                if not re.fullmatch(r"/page-transcript/\d+:\d+", location):
                    raise ValueError("Invalid PDF locator")
                start, end = map(int, location.removeprefix("/page-transcript/").split(":"))
                original = {"start": start, "end": end}
                transcript = "\n".join(p["text"] for p in item["pages"])
                if not 0 <= start < end <= len(transcript):
                    raise ValueError("Invalid PDF span")
                text = transcript[start:end]
                fields, thesis = {}, None
                pattern = r"(?im)^\s*ENUNCIADO\s+0*(\d+)\b" if identifier == "tjmg_sumulas" else r"(?im)^\s*S[úu]mula\s*\n\s*0*(\d+)\b"
                found = re.match(pattern, text)
                source_number = found[1] if found else None
            else:
                raise ValueError("Unknown evidence kind")
            identity = (f"br:{identifier}:{source_number}" if source_number is not None else
                        f"br:{identifier}:unclassified:{item['id']}:{location}")
            if record["number"] != source_number or record["id"] != identity:
                raise ValueError("Identity is not bound to source record")
            if (reading["source_record"] != original or reading["fields"] != fields
                    or reading["source_text"] != text or reading["text_sha256"] != text_digest(text)
                    or reading["thesis_presence"] is not thesis or reading["situation"] != fields.get("situacao")):
                raise ValueError("Source projection mismatch")
            dates = [{"source_field": key, "literal": val, "value": None, "precision": None}
                     for key, val in fields.items() if key.startswith("data")]
            if reading["dates"] != dates:
                raise ValueError("Unsupported temporal assertion")
            statements = [{"literal": m[0], "start": m.start(), "end": m.end(), "target": None}
                          for m in re.finditer(r"\b(?:cancelad[oa]s?|revogad[oa]s?|alterad[oa]s?)\b", text, re.I)]
            if reading["source_statements"] != statements:
                raise ValueError("Unsupported source statement")
    if value["reconciliation"] != {"complete": False, "structure": "incomplete",
            "discrepancies": ["field_and_boundary_review_required"],
            "source_records": total, "structured_identities": len(identities)}:
        raise ValueError("Unsupported completeness claim")
    verify_seal(value)
    return {"ok": True, "source": identifier, "records": len(identities), "coverage": value["coverage"], "complete": False}

