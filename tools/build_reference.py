"""Build an offline, historical reference release from the explicit reviewed fixtures.

This does not contact a database, an LLM or any remote service. It does not claim a new
capture date. Fresh-source release builds use `leis-brasileiras bundle` instead.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import tempfile
import zipfile

from leis_brasileiras import __version__
from leis_brasileiras.capture import json_bytes, sha256
from leis_brasileiras.catalog import LAWS
from leis_brasileiras.corpus import validate_articles
from leis_brasileiras.extraction import LEIS_CONFIG, PARSER_VERSION, hash_texto, html_to_clean_text, parse_law
from leis_brasileiras.integrity import verificar_integridade
from leis_brasileiras.canonical import extract_document
from leis_brasileiras.canonical_validation import validate_document
from leis_brasileiras.compatibility import LEGACY_FORMAT, measure_records
from leis_brasileiras.models import CANONICAL_FORMAT, CANONICAL_PARSER_VERSION

ROOT=Path(__file__).resolve().parents[1]


def build(output: Path, version: str, *, format: str = LEGACY_FORMAT) -> dict:
    if format not in (LEGACY_FORMAT, CANONICAL_FORMAT):
        raise ValueError('Unknown reference format')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}',version):
        raise ValueError('Invalid reference version')
    payloads={}
    inventory=[]
    with tempfile.TemporaryDirectory(prefix='leis-reference-') as temp:
        directory=Path(temp)
        for law in LAWS:
            candidates=[p for p in (ROOT/'tests/fixtures/baseline').glob(law['nome_base']+'_*.json.gz')
                        if re.search(r'_\d{4}-\d{2}-\d{2}\.json\.gz$',p.name)]
            if len(candidates)!=1:
                raise ValueError('Reference requires one snapshot per law')
            expected_path=candidates[0]
            expected=json.loads(gzip.decompress(expected_path.read_bytes()))
            base=expected_path.name.removesuffix('.json.gz')
            date=expected[0]['data_extracao']
            clean=gzip.decompress((expected_path.parent/(base+'_clean.txt.gz')).read_bytes()).decode('utf-8').replace('\r\n','\n')
            cfg=LEIS_CONFIG[law['sigla']]
            parsed,_=parse_law(clean,law['sigla'],cfg['versao'],cfg['url'],date,cfg)
            if parsed!=expected:
                raise ValueError(f"Reference contract changed for {law['sigla']}")
            sidecar=json.loads(gzip.decompress((expected_path.parent/(base+'_riscadas.json.gz')).read_bytes()))
            if sidecar['lei']!=law['sigla'] or sidecar['data_extracao']!=date or 'capture_id' in sidecar:
                raise ValueError('Invalid reference sidecar provenance')
            if sidecar['total']!=len(sidecar['riscadas']) or any(r['hash']!=hash_texto(r['texto']) for r in sidecar['riscadas']):
                raise ValueError('Reference redaction checksum mismatch')
            files={base+'.json':json_bytes(parsed),base+'_clean.txt':clean.encode(),base+'_riscadas.json':json_bytes(sidecar)}
            raw_path=ROOT/'tests/fixtures/html'/f"{law['nome_base']}.htm.gz"
            raw = None
            if raw_path.exists():
                raw=gzip.decompress(raw_path.read_bytes())
                if html_to_clean_text(raw,law['sigla'],cfg)!=clean:
                    raise ValueError('Raw source does not reproduce reference clean text')
                files[base+'_source.html']=raw
            (directory/(base+'.json')).write_bytes(files[base+'.json'])
            (directory/(base+'_clean.txt')).write_bytes(files[base+'_clean.txt'])
            result=validate_articles(directory/(base+'.json'),strict=True)
            if not result['ok']:
                raise ValueError(f'Reference validation failed: {result}')
            if format == CANONICAL_FORMAT:
                from leis_brasileiras.extraction import harvest_redacoes_riscadas

                document = extract_document(clean, law['sigla'], date, precision='date',
                                            raw_sha256=sha256(raw) if raw else None,
                                            prior_redactions=harvest_redacoes_riscadas(raw,law['sigla'],cfg) if raw else [])
                if not validate_document(document)['ok']:
                    raise ValueError('Canonical reference validation failed')
                canonical_files = {'canonical.json':json_bytes(document),'clean.txt':clean.encode()}
                if raw:
                    canonical_files['source.html'] = raw
                # Original sidecar remains evidence; its dedup entries are not asserted
                # to be legally prior redactions in the canonical document.
                canonical_files['legacy_redactions.json'] = json_bytes(sidecar)
                payloads.update({law['sigla']+'/'+name:data for name,data in canonical_files.items()})
            else:
                payloads.update(files)
            inventory.append({'law':law['sigla'],'source_url':law['url'],
                              'observed_date':date,'capture_time_precision':'date',
                              'raw_source_available':raw_path.exists(),
                              'content_hash':sha256(clean.encode()),'legacy_counts':measure_records(parsed),
                              **({'canonical_units':len(document['units']),
                                  'document_revision':document['revision']} if format == CANONICAL_FORMAT else {}),
                              'prior_redactions':sidecar['total']})
        if not verificar_integridade(str(directory)):
            raise ValueError('Reference integrity failed')
    manifest={'format_version':2,'format':format,'corpus_version':version,'kind':'historical-reference',
              'extractor_version':__version__,
              'parser_version':CANONICAL_PARSER_VERSION if format == CANONICAL_FORMAT else PARSER_VERSION,
              'license_status':'pending owner decision',
              'limitations':['Historical observed text, not a current legal-validity determination',
                             'Capture times unknown beyond recorded calendar dates',
                             'L9099 has clean text and JSON but no raw HTML fixture'],
              'laws':inventory,'files':{name:{'bytes':len(data),'sha256':sha256(data)} for name,data in payloads.items()}}
    payloads['manifest.json']=json_bytes(manifest)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(payloads.items()):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644 << 16
            archive.writestr(info,data)
    print(json.dumps({'laws':len(inventory),'legacy_records':sum(law['legacy_counts']['records'] for law in inventory),'sha256':sha256(output.read_bytes())}))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--format',choices=[LEGACY_FORMAT,CANONICAL_FORMAT],default=LEGACY_FORMAT)
    args=parser.parse_args()
    build(args.output,args.version,format=args.format)
