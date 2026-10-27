import gzip
import json
from pathlib import Path
import zipfile

import pytest

from leis_brasileiras import corpus
from leis_brasileiras.capture import extract_html, write_capture, sha256
from leis_brasileiras.integrity import verificar_integridade
from tests.fixture_data import DATA_DIR


def test_all_reference_files_have_integrity():
    assert verificar_integridade(str(DATA_DIR))


def test_empty_integrity_is_failure(tmp_path):
    assert verificar_integridade(str(tmp_path)) is False


@pytest.mark.parametrize('value',[[],[1],[{'texto_limpo':[]}],[{'lei':[]}],{'not':'articles'}])
def test_malformed_article_validation_fails(tmp_path,value):
    path=tmp_path/'cdc_2026-07-07.json';path.write_text(json.dumps(value))
    assert corpus.validate_articles(path)['ok'] is False


@pytest.mark.parametrize('text',['\x00','\ufffd','<script>evil()</script>'])
def test_integrity_checks_all_rows_not_only_first_five(tmp_path,text):
    source=DATA_DIR/'cdc_2026-07-07.json'
    records=json.loads(source.read_text(encoding='utf-8'))
    records[-1]['texto_limpo']=text
    (tmp_path/source.name).write_text(json.dumps(records))
    assert verificar_integridade(str(tmp_path)) is False


def test_validated_release_is_deterministic(monkeypatch,tmp_path):
    raw=gzip.decompress((Path(__file__).parent/'fixtures/html/cdc.htm.gz').read_bytes())
    path=write_capture(extract_html(raw,'CDC','2026-07-07T12:00:00Z'),tmp_path/'captures')
    monkeypatch.setattr(corpus,'SIGLAS',['CDC'])
    first=corpus.build_release([path],tmp_path/'a.zip','test-1')
    second=corpus.build_release([path],tmp_path/'b.zip','test-1')
    assert first.read_bytes()==second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert manifest['laws']==['CDC']
        for name,info in manifest['files'].items():
            assert sha256(archive.read(name))==info['sha256']
    with pytest.raises(ValueError,match='exactly one'):
        corpus.build_release([path,path],tmp_path/'duplicate.zip','test-1')
