"""Inert HTML evidence map, constructed before any legal-content transformation.

DOM paths refer to this exact parser and captured byte hash, not to a live website.
All text nodes, comments, markup and attributes remain addressable. No resource is
fetched and no stylesheet/script is executed. Source markup is data, never safe HTML.
"""
from bs4 import BeautifulSoup, Comment, Declaration, Doctype, NavigableString, Tag

from .evidence import MAX_NODES, MAX_SOURCE_BYTES, raw_digest, text_digest

ACTIVE = {"script", "style"}
TECHNICAL = {"head", "nav", "footer", "header", "aside"}
BLOCKS = {"p", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre", "blockquote"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
PARSER_VERSION = "html-evidence@1"


def decode_source(raw: bytes, encoding: str | None = None) -> tuple[str, str]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid or excessive source")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    elif raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif encoding == "utf-16":
        encoding = "utf-16-le" if raw[1:2] == b"\x00" else "utf-16-be"
    if encoding is None:
        try:
            return raw.decode("utf-8"), "utf-8"
        except UnicodeDecodeError:
            encoding = "windows-1252"
    if encoding.lower().startswith("utf-16") and len(raw) % 2:
        # Caller records the undecodable tail separately; original bytes remain immutable.
        raw = raw[:-1]
    try:
        text = raw.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        # Undefined cp1252 bytes are retained one-to-one, never replaced by U+FFFD.
        if encoding.lower() not in {"windows-1252", "cp1252"}:
            raise
        text, encoding = raw.decode("iso-8859-1"), "iso-8859-1"
    return text, encoding


def html_map(raw: bytes, encoding: str | None = None) -> dict:
    decoded, codec = decode_source(raw, encoding)
    if "\x00" in decoded:
        raise ValueError("NUL in decoded HTML")
    soup = BeautifulSoup(decoded, "html.parser")
    elements, texts = [], []
    # Iterative traversal bounds depth without depending on Python recursion limits.
    pending = [(soup, "", [], None, None)]
    while pending:
        node, path, ancestors, block, table = pending.pop()
        if len(elements) + len(texts) > MAX_NODES or len(ancestors) > 128:
            raise ValueError("Excessive HTML structure")
        if isinstance(node, Tag):
            if node is not soup:
                attrs = {key: value for key, value in node.attrs.items()}
                elements.append({"path": path, "tag": node.name, "attributes": attrs})
                ancestors = [*ancestors, {"path": path, "tag": node.name, "attributes": attrs}]
                if node.name in BLOCKS:
                    block = path
                if node.name == "table":
                    table = path
            children = list(node.children)
            counters = {}
            entries = []
            for child in children:
                kind = child.name if isinstance(child, Tag) else "#text"
                counters[kind] = counters.get(kind, 0) + 1
                entries.append((child, f"{path}/{kind}[{counters[kind]}]", ancestors, block, table))
            pending.extend(reversed(entries))
        elif isinstance(node, NavigableString):
            tags = {entry["tag"] for entry in ancestors}
            kind = ("comment" if isinstance(node, (Comment, Declaration, Doctype)) else
                    "active" if tags & ACTIVE else "page_chrome" if tags & TECHNICAL else "content")
            marks = [entry["path"] for entry in ancestors
                     if entry["tag"] in {"s", "del", "strike"}
                     or "line-through" in str(entry["attributes"].get("style", "")).lower()]
            text = str(node)
            texts.append({"id": f"text-{len(texts) + 1}", "path": path, "text": text,
                          "text_sha256": text_digest(text), "kind": kind,
                          "block": block, "table": table, "struck_by": marks})
    return {"parser_version": PARSER_VERSION, "raw_sha256": raw_digest(raw),
            "undecoded_tail_hex": raw[-1:].hex() if codec.startswith("utf-16") and len(raw) % 2 else None,
            "encoding": codec, "decoded_sha256": text_digest(decoded),
            "elements": elements, "texts": texts}


def text_map(text: str) -> dict:
    """Historical derived text is evidence of that file only, never of missing HTML."""
    if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Invalid or excessive historical text")
    entries = []
    for index, line in enumerate(text.splitlines(keepends=True), 1):
        entries.append({"id": f"text-{index}", "path": f"/line[{index}]", "text": line,
                        "text_sha256": text_digest(line), "kind": "content",
                        "block": f"/line[{index}]", "table": None, "struck_by": []})
    return {"parser_version": "historical-text@1", "raw_sha256": None, "undecoded_tail_hex": None,
            "encoding": "utf-8", "decoded_sha256": text_digest(text),
            "elements": [], "texts": entries}
