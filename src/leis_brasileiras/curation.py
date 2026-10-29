"""Inspect the historical registry for audit only; never included in observation exports."""
import json
from pathlib import Path

from .models import digest


def load_curation(law: str) -> tuple[str, list[dict]]:
    """Return a revision and review-pending annotations from the packaged registry.

    A textual reference in a legacy note is not independently verified evidence.
    No note establishes effective dates or changes the canonical observed text.
    """
    registry = json.loads(Path(__file__).with_name("known_issues.json").read_text(encoding="utf-8"))
    notes = []
    missing = registry.get("artigos_faltantes_verificados", {}).get(law, {})
    for number, explanation in missing.items():
        if not number.startswith("_"):
            notes.append({"kind": "missing_from_compilation", "target_label": f"Art. {number}",
                          "assertion": explanation, "origin": "editorial",
                          "evidence": [], "review_status": "pending"})
    overrides = registry.get("overrides_pos_extracao", {})
    for kind, by_law in overrides.items():
        if kind.startswith("_") or not isinstance(by_law, dict):
            continue
        for target, value in by_law.get(law, {}).items():
            notes.append({"kind": kind, "target_label": target, "assertion": value,
                          "origin": "editorial", "evidence": [], "review_status": "pending"})
    return digest(notes), notes
