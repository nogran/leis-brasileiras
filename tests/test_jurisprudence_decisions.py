"""Contract regressions ported independently of private persistence and ingestion."""
import copy
import json
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest
from leis_brasileiras.jurisprudence.decisions import content_hash, validate_decision


def draft(document_id='official-42'):
    record = {'source': 'STJ', 'tipo': 'acordao', 'numero': document_id, 'enunciado': 'Texto oficial sintético exclusivamente para teste de contrato.', 'has_thesis': True, 'situacao': 'publicado', 'orgao_julgador': 'Turma sintética', 'data_julgamento': '2026-01-01', 'extracted_at': '2026-09-25', 'url_fonte': 'https://www.stj.jus.br/fixture', 'decision_context': {'document_id': document_id, 'case_reference': 'Processo sintético 1', 'facts': 'Fatos delimitados.', 'question': 'Questão específica.', 'holding': 'Conclusão no caso.', 'limits': 'Não decidiu o caso vizinho.', 'source_url': 'https://www.stj.jus.br/fixture', 'evidence_sha256': 'b' * 64}}
    record['hash'] = content_hash(record)
    return record

def approved():
    record = draft()
    record['curation_review'] = {'decision': 'approved', 'reviewer': 'synthetic-test-reviewer', 'reviewed_at': '2026-09-25T10:00:00Z', 'record_hash': record['hash'], 'evidence_sha256': 'b' * 64, 'approval_ref': 'synthetic-test-only'}
    return record

def test_review_binds_official_bytes_content_and_scope_and_does_not_change_hash():
    record = approved()
    validate_decision(record, require_review=True)
    assert content_hash(record) == record['hash']
    changed = copy.deepcopy(record)
    changed['decision_context']['limits'] = 'Escopo ampliado.'
    with pytest.raises(ValueError, match='hash mismatch'):
        validate_decision(changed, require_review=True)
    changed['hash'] = content_hash(changed)
    with pytest.raises(ValueError, match='approval does not cover'):
        validate_decision(changed, require_review=True)

@pytest.mark.parametrize('field', list(draft()['decision_context']))
def test_incomplete_context_cannot_be_ingested(field):
    record = draft()
    del record['decision_context'][field]
    record['hash'] = content_hash(record)
    with pytest.raises(ValueError):
        validate_decision(record)

@pytest.mark.parametrize('field,value', [('document_id', 'other-id'), ('source_url', 'https://www.stj.jus.br.evil.invalid/doc'), ('evidence_sha256', 'wrong'), ('limits', ''), ('facts', 'x' * 16001), ('holding', 'nul\x00')])
def test_malformed_context_never_passes(field, value):
    record = draft()
    record['decision_context'][field] = value
    record['hash'] = content_hash(record)
    with pytest.raises(ValueError):
        validate_decision(record)

@pytest.mark.parametrize('field,value', [('decision', 'pending'), ('record_hash', 'a' * 64), ('evidence_sha256', 'c' * 64), ('reviewed_at', '2026-01-01'), ('reviewer', ''), ('approval_ref', '')])
def test_stale_or_incomplete_review_is_not_authorization(field, value):
    record = approved()
    record['curation_review'][field] = value
    with pytest.raises(ValueError):
        validate_decision(record, require_review=True)

@pytest.mark.parametrize('value', ['not-a-date', '9999-01-01', '2026-01'])
def test_judgment_date_is_not_inferred(value):
    record = draft()
    record['data_julgamento'] = value
    record['hash'] = content_hash(record)
    with pytest.raises(ValueError, match='judgment date'):
        validate_decision(record)


def test_cli_requires_explicit_judgment_and_review(tmp_path, capsys):
    from leis_brasileiras.cli import main
    path = tmp_path / "decision.json"
    path.write_text(json.dumps(draft()), encoding="utf-8")
    assert main(["jurisprudence", "validate-decision", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["review_required"] is False
    assert main(["jurisprudence", "validate-decision", str(path), "--require-review"]) == 1
    capsys.readouterr()
    path.write_text(json.dumps(approved()), encoding="utf-8")
    assert main(["jurisprudence", "validate-decision", str(path), "--require-review"]) == 0
    capsys.readouterr()
    path.write_text('{"tipo":"sumula"}', encoding="utf-8")
    assert main(["jurisprudence", "validate-decision", str(path)]) == 1
