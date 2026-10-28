"""Small replaceable HTTP adapter: bounded requests, no ambient credentials or cookies."""
from pathlib import Path
import re
from time import monotonic, sleep
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from .catalog import source
from .models import MAX_BYTES


def secure_pdf_url(identifier: str, url: str) -> str:
    """Upgrade a catalogued court's HTTP link before any network operation.

    This is not a redirect or a fallback: only the same reviewed HTTPS host/path is fetched.
    The original link remains in the raw index for evidence replay.
    """
    parsed = urlsplit(url)
    if parsed.scheme == "http":
        url = parsed._replace(scheme="https").geturl()
    validate_url(identifier, url, "pdf")
    return url


def validate_url(identifier: str, url: str, kind: str) -> None:
    original = source(identifier)["official_url"]
    parsed, base = urlsplit(url), urlsplit(original)
    if (len(url) > 2048 or any(ord(c) < 33 for c in url) or parsed.scheme != "https"
            or parsed.hostname != base.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or "\\" in unquote(url) or ".." in unquote(parsed.path).split("/")):
        raise ValueError("Unapproved official-source URL")
    if kind == "pdf" and identifier in {"tjpe_sumulas", "tjmg_sumulas"}:
        prefixes = ("/documents/",) if identifier == "tjpe_sumulas" else ("/data/files/", "/portal-tjmg/data/files/")
        if not parsed.path.startswith(prefixes) or parsed.query:
            raise ValueError("Unapproved official PDF path")
        return
    if parsed.path != base.path:
        raise ValueError("Unapproved source endpoint")
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    if identifier == "stj_sumulas":
        expected = {"livre": ["@docn"], "b": ["SUMU"], "p": ["true"], "numDocsPagina": ["50"]}
        if any(query.get(k) != v for k, v in expected.items()) or set(query) != {*expected, "i"}:
            raise ValueError("Unapproved pagination query")
        if len(query["i"]) != 1 or not re.fullmatch(r"[0-9]{1,4}", query["i"][0]):
            raise ValueError("Invalid page offset")
        if int(query["i"][0]) not in range(1, 1502, 50):
            raise ValueError("Page offset exceeds bound")
    elif identifier == "stf_sumulas_vinculantes":
        if query.get("base") != ["26"] or set(query) - {"base", "sumula"}:
            raise ValueError("Unapproved summary query")
        if "sumula" in query and (len(query["sumula"]) != 1 or not re.fullmatch(r"[0-9]{1,8}", query["sumula"][0])):
            raise ValueError("Invalid summary identifier")
    elif parsed.query:
        raise ValueError("Unexpected source query")


class SourceClient:
    """One call owns one session. Two attempts; 60 seconds/request; 10 minutes/source.

    No fallback changes the source, TLS policy or corpus. Failed batches stop before publication.
    A reviewed CA bundle can be supplied explicitly for incomplete server chains.
    """

    def __init__(self, identifier: str, ca_bundle: Path | None = None):
        source(identifier)
        self.identifier = identifier
        self.deadline = monotonic() + 600
        self.ca_bundle = str(ca_bundle) if ca_bundle else True
        self.last_request = 0.0

    def fetch(self, url: str, kind: str, form: str | None = None) -> bytes:
        validate_url(self.identifier, url, kind)
        if form is not None and (self.identifier != "stf_teses_rg" or form not in {"com", "sem"}):
            raise ValueError("Only catalogued read-only STF query forms are allowed")
        sleep(max(0, 1 - (monotonic() - self.last_request)))
        deadline = min(self.deadline, monotonic() + 60)
        with requests.Session() as session:
            session.trust_env = False
            session.headers["User-Agent"] = "leis-brasileiras/0.1 (official-source research)"
            if form:
                session.headers["Referer"] = "https://portal.stf.jus.br/repercussaogeral/teses.asp"
            for attempt in range(2):
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError("Source deadline exceeded")
                self.last_request = monotonic()
                try:
                    session.cookies.clear()
                    with session.request("POST" if form else "GET", url,
                                         data={"tipo": form} if form else None,
                                         timeout=(min(10, remaining), min(20, remaining)),
                                         verify=self.ca_bundle, stream=True, allow_redirects=False) as response:
                        if 300 <= response.status_code < 400:
                            raise ValueError("Redirect refused; review catalog")
                        if response.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                            sleep(1)
                            continue
                        response.raise_for_status()
                        mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
                        allowed = {"html": {"text/html", "application/xhtml+xml"},
                                   "json": {"application/json", "text/html", "text/plain"},
                                   "csv": {"text/csv", "application/csv", "application/octet-stream", "text/plain"},
                                   "pdf": {"application/pdf", "application/octet-stream"}}
                        if mime not in allowed[kind]:
                            raise ValueError("Unexpected source media type")
                        chunks, size = [], 0
                        for chunk in response.iter_content(65536):
                            size += len(chunk)
                            if size > MAX_BYTES or monotonic() > deadline:
                                raise ValueError("Source size or time limit exceeded")
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                        if not raw or (kind == "pdf" and not raw.startswith(b"%PDF-")):
                            raise ValueError("Empty response or invalid PDF signature")
                        return raw
                except requests.exceptions.SSLError:
                    raise
                except (requests.ConnectionError, requests.Timeout):
                    if attempt or monotonic() >= deadline:
                        raise
                    sleep(1)
        raise RuntimeError("Source unavailable")
