"""Bounded, read-only HTTP transport for catalogued official sources."""
from time import monotonic, sleep
from urllib.parse import urlsplit

import requests

MAX_HTML_BYTES = 16 * 1024 * 1024
MAX_SECONDS = 90
ALLOWED_HOSTS = frozenset({"www.planalto.gov.br", "planalto.gov.br"})
# Bare product tokens are reset by the origin. A compatible token that still names this
# project is the identification that receives a response. Do not follow redirects;
# catalog URLs must be the location that returns the HTML.
USER_AGENT = (
    "Mozilla/5.0 (compatible; leis-brasileiras/0.2; "
    "+https://github.com/nogran/leis-brasileiras)"
)


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.startswith("/ccivil_03/") or parsed.query or parsed.fragment):
        raise ValueError("Only catalogued Planalto HTTPS sources are allowed")


def fetch_html(url: str) -> bytes:
    """Two attempts, bounded body/deadline, TLS verification, no redirects or browser execution.

    Each call owns its session. Cookies and ambient .netrc credentials cannot cross calls.
    TLS verification is never disabled. Ambient proxy/.netrc discovery is disabled.
    """
    validate_url(url)
    deadline = monotonic() + MAX_SECONDS
    with requests.Session() as session:
        session.trust_env = False
        session.headers["User-Agent"] = USER_AGENT
        for attempt in range(2):
            try:
                with session.get(url, timeout=(10, 25), stream=True, allow_redirects=False) as response:
                    if 300 <= response.status_code < 400:
                        raise ValueError("Redirect refused; review the official catalog URL")
                    response.raise_for_status()
                    mime = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if mime not in ("text/html", "application/xhtml+xml"):
                        raise ValueError("Expected an HTML response")
                    chunks = []
                    size = 0
                    for chunk in response.iter_content(chunk_size=65536):
                        size += len(chunk)
                        if size > MAX_HTML_BYTES or monotonic() > deadline:
                            raise ValueError("Source exceeds byte or elapsed-time limit")
                        chunks.append(chunk)
                    if not size:
                        raise ValueError("Empty HTML response")
                    return b"".join(chunks)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 1 or monotonic() >= deadline:
                    raise
                sleep(1)
    raise RuntimeError("No HTML received")
