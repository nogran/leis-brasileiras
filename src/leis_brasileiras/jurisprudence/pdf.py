"""Quarantine and scan PDFs before text-only extraction in a resource-limited child."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .models import MAX_BYTES

# The child starts with an isolated interpreter; PDF content never becomes Python code.
WORKER = r'''
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

LIMIT = 768 * 1024 * 1024
if os.name == "nt":
    class Basic(ctypes.Structure):
        _fields_ = [("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                    ("Flags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                    ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                    ("Scheduling", wintypes.DWORD)]
    class Counters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]
    class Extended(ctypes.Structure):
        _fields_ = [("Basic", Basic), ("IO", Counters), ("ProcessMemory", ctypes.c_size_t),
                    ("JobMemory", ctypes.c_size_t), ("PeakProcess", ctypes.c_size_t),
                    ("PeakJob", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.Basic.Flags = 0x100 | 0x2000
    limits.ProcessMemory = LIMIT
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise RuntimeError("Cannot enforce PDF memory limit")
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise RuntimeError("Cannot isolate PDF process")
else:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (LIMIT, LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    resource.setrlimit(resource.RLIMIT_FSIZE, (24 * 1024 * 1024, 24 * 1024 * 1024))

from pypdf import PdfReader
reader = PdfReader(sys.argv[1], strict=True)
if reader.is_encrypted or not 1 <= len(reader.pages) <= 300:
    raise ValueError("Encrypted PDF or page limit exceeded")
pages = []
total = 0
for page in reader.pages:
    contents = page.get_contents()
    if contents is not None and len(contents.get_data()) > 16 * 1024 * 1024:
        raise ValueError("Page content stream exceeds limit")
    text = page.extract_text() or ""
    total += len(text.encode("utf-8"))
    if total > 16 * 1024 * 1024:
        raise ValueError("Extracted text exceeds limit")
    pages.append(text)
if sum(len(text.strip()) for text in pages) < 200:
    raise ValueError("Insufficient digital text; OCR is not supported")
Path(sys.argv[2]).write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
'''


def scan_pdf(path: Path, scanner: Path | None = None) -> None:
    """ClamAV or Windows Defender; unavailable, infected and indeterminate all fail closed."""
    executable = str(scanner) if scanner else shutil.which("clamscan")
    if not executable and os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Windows Defender/MpCmdRun.exe"
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        raise RuntimeError("PDF scanning requires ClamAV or Windows Defender")
    if Path(executable).name.lower() == "mpcmdrun.exe":
        arguments = [executable, "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"]
    else:
        arguments = [executable, "--no-summary", "--infected", "--", str(path)]
    # Do not capture an unbounded scanner log or reveal local paths through CLI diagnostics.
    result = subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=90, check=False, shell=False)
    if result.returncode != 0:
        raise ValueError("PDF malware scan did not pass")


def extract_pages(raw: bytes, scanner: Path | None = None) -> list[str]:
    if not isinstance(raw, bytes) or not raw.startswith(b"%PDF-") or len(raw) > MAX_BYTES:
        raise ValueError("Invalid PDF signature or size")
    with tempfile.TemporaryDirectory(prefix="juris-quarantine-") as directory:
        folder = Path(directory)
        source, output = folder / "source.pdf", folder / "pages.json"
        source.write_bytes(raw)
        scan_pdf(source, scanner)
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        result = subprocess.run([sys.executable, "-I", "-c", WORKER, str(source), str(output)],
                                cwd=folder, env=environment, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=60, check=False, shell=False)
        if result.returncode or not output.is_file() or output.stat().st_size > MAX_BYTES:
            raise ValueError("Isolated PDF extraction failed")
        pages = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(pages, list) or not pages or any(not isinstance(page, str) for page in pages):
            raise ValueError("Invalid isolated PDF result")
        return pages
