from leis_brasileiras.canonical import extract_document
from leis_brasileiras.curation import load_curation
from leis_brasileiras.models import digest


def test_editorial_assertions_do_not_become_statutory_text_or_validity():
    document = extract_document("Art. 1 Texto observado de teste suficientemente longo.", "CLT",
                                "2026-07-07", precision="date")
    assert len(document["units"]) == 1  # No synthetic tombstones in canonical units.
    assert not any("Não recepcionado" in unit["text"] for unit in document["units"])
    assert document["editorial_annotations"]
    assert all(note["origin"] == "editorial" and note["review_status"] == "pending"
               and note["evidence"] == [] for note in document["editorial_annotations"])


def test_curation_revision_and_session_independence():
    revision, notes = load_curation("CLT")
    assert revision == digest(notes)
    notes.clear()
    assert load_curation("CLT")[1]
