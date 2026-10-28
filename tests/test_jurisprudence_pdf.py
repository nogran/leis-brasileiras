"""Antivirus gate and resource-isolated PDF text extraction contracts."""
import gzip
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from leis_brasileiras.jurisprudence import pdf


def test_actual_pdf_worker_extracts_pages_without_running_active_content(monkeypatch):
    scan = Mock()
    monkeypatch.setattr(pdf, "scan_pdf", scan)
    fixture = Path(__file__).parent / "fixtures/jurisprudence/tjmg_sumulas_amostra.pdf.gz"
    pages = pdf.extract_pages(gzip.decompress(fixture.read_bytes()))
    assert len(pages) == 3
    assert "ENUNCIADO" in "\n".join(pages)
    scan.assert_called_once()
    assert not scan.call_args.args[0].exists()  # quarantine cleaned


@pytest.mark.parametrize("raw", [b"", b"<html>not pdf</html>", b"MZbinary", b"%PDF-" + b"x" * 25_165_825],
                         ids=["empty", "html", "executable", "oversize"])
def test_malformed_and_excessive_files_never_reach_scanner(monkeypatch, raw):
    scan = Mock()
    monkeypatch.setattr(pdf, "scan_pdf", scan)
    with pytest.raises(ValueError):
        pdf.extract_pages(raw)
    scan.assert_not_called()


def test_scan_failure_stops_before_pdf_parser(monkeypatch):
    monkeypatch.setattr(pdf, "scan_pdf", Mock(side_effect=ValueError("infected")))
    worker = Mock()
    monkeypatch.setattr(pdf.subprocess, "run", worker)
    with pytest.raises(ValueError, match="infected"):
        pdf.extract_pages(b"%PDF-test")
    worker.assert_not_called()


@pytest.mark.parametrize("returncode", [1, 2])
def test_scanner_infection_and_failure_are_both_rejected(tmp_path, monkeypatch, returncode):
    run = Mock(return_value=SimpleNamespace(returncode=returncode))
    monkeypatch.setattr(pdf.subprocess, "run", run)
    with pytest.raises(ValueError):
        pdf.scan_pdf(tmp_path / "payload.pdf", Path("clamscan"))
    assert run.call_args.kwargs["shell"] is False
    assert run.call_args.args[0][-2] == "--"


def test_defender_adapter_does_not_remediate_files(tmp_path, monkeypatch):
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(pdf.subprocess, "run", run)
    pdf.scan_pdf(tmp_path / "file.pdf", Path("MpCmdRun.exe"))
    assert "-DisableRemediation" in run.call_args.args[0]


def test_worker_timeout_cleans_quarantine(monkeypatch):
    paths = []
    monkeypatch.setattr(pdf, "scan_pdf", lambda path, scanner: paths.append(path))
    monkeypatch.setattr(pdf.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("worker", 60)))
    with pytest.raises(subprocess.TimeoutExpired):
        pdf.extract_pages(b"%PDF-test")
    assert not paths[0].exists()
