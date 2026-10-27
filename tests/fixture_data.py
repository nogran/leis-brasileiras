"""Materialize reviewed, frozen reference JSONs outside the checkout for legacy tests."""
import atexit
import gzip
from pathlib import Path
import tempfile

_TEMP = tempfile.TemporaryDirectory(prefix="leis-fixtures-")
atexit.register(_TEMP.cleanup)
DATA_DIR = Path(_TEMP.name)
for _path in (Path(__file__).parent / "fixtures" / "baseline").glob("*.gz"):
    (DATA_DIR / _path.stem).write_bytes(gzip.decompress(_path.read_bytes()))
