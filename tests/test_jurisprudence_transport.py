"""Network is mocked; hostile URL, response and session behavior is exercised."""
from unittest.mock import MagicMock

import pytest
import requests

from leis_brasileiras.jurisprudence import transport
from leis_brasileiras.jurisprudence.catalog import source
from leis_brasileiras.jurisprudence.transport import SourceClient, secure_pdf_url, validate_url


@pytest.mark.parametrize("address", [
    "http://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26",
    "https://portal.stf.jus.br.evil.invalid/jurisprudencia/sumariosumulas.asp?base=26",
    "https://user:secret@portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26",
    "https://127.0.0.1/", "file:///etc/passwd", "https://169.254.169.254/metadata",
    "https://portal.stf.jus.br:444/jurisprudencia/sumariosumulas.asp?base=26",
    "https://portal.stf.jus.br/jurisprudencia/../private?base=26",
    "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&sumula=../../secret",
    "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&sumula=1&sumula=2",
    "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26&token=secret",
    "https://portal.stf.jus.br/jurisprudencia/sumariosumulas.asp?base=26#fragment",
])
def test_ssrf_credentials_and_ambiguous_urls_are_rejected(address):
    with pytest.raises(ValueError):
        validate_url("stf_sumulas_vinculantes", address, "html")


@pytest.mark.parametrize("identifier", ["stj_temas", "stf_teses_rg", "tjmg_sumulas", "tjpe_sumulas"])
def test_static_source_endpoints_cannot_take_arbitrary_queries(identifier):
    with pytest.raises(ValueError):
        validate_url(identifier, source(identifier)["official_url"] + "?url=https://attacker.invalid", "html")


@pytest.mark.parametrize("offset", ["0", "2", "1551", "abc", "1&i=51"])
def test_pagination_is_bounded(offset):
    with pytest.raises(ValueError):
        validate_url("stj_sumulas", source("stj_sumulas")["official_url"].format(i=offset), "html")


def setup_http(monkeypatch, *, status=200, mime="text/csv", chunks=None):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = status
    response.headers = {"Content-Type": mime}
    response.iter_content.return_value = iter(chunks if chunks is not None else [b"a,b\n1,2\n"])
    session = MagicMock()
    session.__enter__.return_value = session
    session.request.return_value = response
    factory = MagicMock(return_value=session)
    monkeypatch.setattr(transport.requests, "Session", factory)
    monkeypatch.setattr(transport, "sleep", lambda seconds: None)
    return factory, session, response


def test_session_disables_ambient_credentials_redirects_and_tls_bypass(monkeypatch):
    factory, session, _ = setup_http(monkeypatch)
    client = SourceClient("stj_temas")
    assert client.fetch(source("stj_temas")["official_url"], "csv") == b"a,b\n1,2\n"
    assert session.trust_env is False
    arguments = session.request.call_args.kwargs
    assert arguments["allow_redirects"] is False
    assert arguments["verify"] is True
    assert arguments["stream"] is True
    session.cookies.clear.assert_called_once()
    assert factory.call_count == 1


@pytest.mark.parametrize("status,mime,chunks", [(302, "text/csv", [b"x"]), (200, "image/png", [b"x"]),
                                                (200, "text/csv", []), (200, "text/csv", [b"123456"])])
def test_bad_responses_fail_without_fallback(monkeypatch, status, mime, chunks):
    setup_http(monkeypatch, status=status, mime=mime, chunks=chunks)
    monkeypatch.setattr(transport, "MAX_BYTES", 5)
    with pytest.raises(ValueError):
        SourceClient("stj_temas").fetch(source("stj_temas")["official_url"], "csv")


def test_retry_is_bounded_and_clears_cookies(monkeypatch):
    _, session, response = setup_http(monkeypatch)
    session.request.side_effect = [requests.Timeout(), response]
    SourceClient("stj_temas").fetch(source("stj_temas")["official_url"], "csv")
    assert session.request.call_count == session.cookies.clear.call_count == 2


def test_tls_failure_is_not_retried_with_weaker_verification(monkeypatch):
    _, session, _ = setup_http(monkeypatch)
    session.request.side_effect = requests.exceptions.SSLError()
    with pytest.raises(requests.exceptions.SSLError):
        SourceClient("stj_temas").fetch(source("stj_temas")["official_url"], "csv")
    assert session.request.call_count == 1


def test_stf_form_is_read_only_and_referer_is_fixed(monkeypatch):
    _, session, _ = setup_http(monkeypatch, mime="text/html", chunks=[b"[]"])
    client = SourceClient("stf_teses_rg")
    client.fetch(source("stf_teses_rg")["official_url"], "json", "com")
    assert session.request.call_args.args[0] == "POST"
    assert session.request.call_args.kwargs["data"] == {"tipo": "com"}
    with pytest.raises(ValueError):
        client.fetch(source("stf_teses_rg")["official_url"], "json", "delete")


def test_expired_collection_stops_before_request(monkeypatch):
    _, session, _ = setup_http(monkeypatch)
    client = SourceClient("stj_temas")
    client.deadline = 0
    with pytest.raises(TimeoutError):
        client.fetch(source("stj_temas")["official_url"], "csv")
    session.request.assert_not_called()


def test_http_pdf_link_is_upgraded_without_contacting_http(monkeypatch):
    address = "http://www.tjmg.jus.br/data/files/official.pdf"
    assert secure_pdf_url("tjmg_sumulas", address) == "https://www.tjmg.jus.br/data/files/official.pdf"
    for bad in ("http://attacker.invalid/data/files/official.pdf", "http://user@www.tjmg.jus.br/data/files/a.pdf",
                "http://www.tjmg.jus.br:80/data/files/a.pdf", "http://www.tjmg.jus.br/private/a.pdf"):
        with pytest.raises(ValueError):
            secure_pdf_url("tjmg_sumulas", bad)
