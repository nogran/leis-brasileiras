"""Contract regressions ported independently of private persistence and ingestion."""
import copy
import json
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from leis_brasileiras.jurisprudence.decisions import content_hash, validate_decision


def record():
    return {'source': 'TJPE', 'tipo': 'sumula_tj', 'numero': '169', 'enunciado': 'Texto sintético para provar o transporte dos metadados.', 'situacao': 'em_vigor', 'has_thesis': True, 'hash': 'a' * 16, 'url_fonte': 'https://portal.tjpe.jus.br/source', 'extracted_at': '2026-09-01', 'status_observation': {'court': 'TJPE', 'doc_type': 'sumula_tj', 'number': '169', 'record_hash': 'a' * 16, 'situation': 'em_vigor', 'checked_at': '2026-09-25T10:00:00Z', 'source_url': 'https://portal.tjpe.jus.br/source', 'evidence_sha256': 'b' * 64}}

@pytest.mark.parametrize('field,value', [('court', 'STJ'), ('doc_type', 'sumula'), ('number', '137'), ('record_hash', 'c' * 16), ('situation', 'cancelada'), ('checked_at', '2026-09-25'), ('checked_at', '9999-01-01T00:00:00Z'), ('checked_at', 'nonsense'), ('evidence_sha256', 'hash'), ('source_url', 'https://www.stj.jus.br/source'), ('source_url', 'https://portal.tjpe.jus.br.evil.invalid/source'), ('source_url', 'https://user@portal.tjpe.jus.br/source'), ('source_url', 'http://portal.tjpe.jus.br/source'), ('source_url', 'https://portal.tjpe.jus.br:bad/source')])
def test_every_dimension_is_bound_or_rejected(field, value):
    from leis_brasileiras.jurisprudence.provenance import validate_status_observation
    item = record()
    item['status_observation'][field] = value
    with pytest.raises(ValueError, match='status_observation'):
        validate_status_observation(item)

@pytest.mark.parametrize('field', list(record()['status_observation']))
def test_partial_observation_never_passes(field):
    from leis_brasileiras.jurisprudence.provenance import validate_status_observation
    item = record()
    del item['status_observation'][field]
    with pytest.raises(ValueError, match='status_observation'):
        validate_status_observation(item)

@pytest.mark.parametrize('observation', [None, 'today', {}, {'extra': 'value'}])
def test_non_objects_and_empty_observations_do_not_claim_a_date(observation):
    from leis_brasileiras.jurisprudence.provenance import validate_status_observation
    item = record()
    item['status_observation'] = observation
    with pytest.raises(ValueError, match='status_observation'):
        validate_status_observation(item)

def test_malformed_field_types_and_control_characters_are_rejected():
    from leis_brasileiras.jurisprudence.provenance import validate_status_observation
    item = record()
    item['status_observation']['checked_at'] = 20260925
    with pytest.raises(ValueError, match='nonempty strings'):
        validate_status_observation(item)
    item = record()
    item['situacao'] = item['status_observation']['situation'] = 'em_vigor\nATUAL'
    with pytest.raises(ValueError, match='invalid situation'):
        validate_status_observation(item)
