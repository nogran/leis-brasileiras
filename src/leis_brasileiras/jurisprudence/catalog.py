"""Packaged official source catalog, with historical counts identified as such."""
import json
from importlib.resources import files


def catalog() -> dict:
    """Return a fresh catalog so callers cannot mutate another capture's state."""
    return json.loads(files(__package__).joinpath("sources.json").read_text(encoding="utf-8"))


def source(identifier: str) -> dict:
    for entry in catalog()["sources"]:
        if entry["extractor_id"] == identifier:
            return entry
    raise ValueError("Unknown jurisprudence source")


SOURCE_IDS = tuple(entry["extractor_id"] for entry in catalog()["sources"])
