"""Explicit extraction, validation and local distribution commands."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from .capture import extract_html, write_capture
from .catalog import LAWS, SIGLAS
from .corpus import build_release, validate_articles, verify_capture
from .extraction import LEIS_CONFIG
from .integrity import verificar_integridade
from .transport import fetch_html
from .models import CANONICAL_FORMAT
from .compatibility import LEGACY_FORMAT
from .canonical_validation import validate_path


def main(argv=None) -> int:
    if sys.platform == "win32" and hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="leis-brasileiras")
    commands = parser.add_subparsers(dest="command",required=True)
    jurisprudence = commands.add_parser("jurisprudence", help="Official jurisprudence corpus")
    from .jurisprudence.catalog import SOURCE_IDS
    operations = jurisprudence.add_subparsers(dest="juris_command", required=True)
    operations.add_parser("catalog", help="List official sources and dated historical counts")
    jextract = operations.add_parser("extract", help="Capture and validate one complete official source")
    jextract.add_argument("source", choices=SOURCE_IDS)
    jextract.add_argument("--output", type=Path, required=True)
    jextract.add_argument("--scanner", type=Path, help="ClamAV executable or Windows MpCmdRun.exe")
    jextract.add_argument("--ca-bundle", type=Path, help="Explicit reviewed TLS CA bundle")
    for name in ("validate", "verify-capture", "validate-decision"):
        operation = operations.add_parser(name)
        operation.add_argument("path", type=Path)
        if name == "verify-capture":
            operation.add_argument("--scanner", type=Path)
        if name == "validate-decision":
            operation.add_argument("--require-review", action="store_true")
    jbundle = operations.add_parser("bundle", help="Verify and package a local jurisprudence archive")
    jbundle.add_argument("captures", nargs="+", type=Path)
    jbundle.add_argument("--output", type=Path, required=True)
    jbundle.add_argument("--version", required=True)
    jbundle.add_argument("--sources", nargs="+", choices=SOURCE_IDS)
    jbundle.add_argument("--scanner", type=Path)
    jbundle.add_argument("--allow-samples", action="store_true")
    commands.add_parser("catalog",help="List supported sources")
    extract = commands.add_parser("extract",help="Capture official sources; no database")
    extract.add_argument("laws",nargs="+",choices=[*SIGLAS,"ALL"])
    extract.add_argument("--output",type=Path,required=True)
    extract.add_argument("--force",action="store_true",help="Explicit fresh capture (all runs are fresh)")
    extract.add_argument("--format", choices=[CANONICAL_FORMAT], default=CANONICAL_FORMAT,
                         help="Evidence-bound observation; legacy generation is disabled")
    validate = commands.add_parser("validate",help="Validate article JSONs, including multipart integrity")
    validate.add_argument("path",type=Path)
    validate.add_argument("--strict",action="store_true")
    validate.add_argument("--format", choices=[CANONICAL_FORMAT, LEGACY_FORMAT], default=CANONICAL_FORMAT)
    integrity = commands.add_parser("integrity")
    integrity.add_argument("path",type=Path)
    verify = commands.add_parser("verify-capture")
    verify.add_argument("path",type=Path)
    release = commands.add_parser("bundle",help="Prepare local ZIP; does not publish")
    release.add_argument("captures",nargs="+",type=Path)
    release.add_argument("--output",type=Path,required=True)
    release.add_argument("--version",required=True)
    release.add_argument("--laws", nargs="+", choices=SIGLAS,
                         help="Explicit subset; omission requires the full catalog")
    args = parser.parse_args(argv)
    try:
        if args.command == "jurisprudence":
            return jurisprudence_command(args)
        elif args.command == "catalog":
            print(json.dumps(LAWS,ensure_ascii=False,indent=2))
        elif args.command == "extract":
            selected = SIGLAS if "ALL" in args.laws else list(dict.fromkeys(args.laws))
            failed = []
            for law in selected:
                try:
                    raw = fetch_html(LEIS_CONFIG[law]["url"])
                    capture = extract_html(raw,law,datetime.now(timezone.utc).isoformat(),format=args.format)
                    path = write_capture(capture,args.output)
                    verify_capture(path)
                    print(json.dumps({"law":law,"capture":str(path),"status":"validated"}))
                except Exception as exc:
                    # No response bodies, ambient credentials or query strings in output.
                    failed.append({"law":law,"error_type":type(exc).__name__})
                    print(json.dumps(failed[-1]),file=sys.stderr)
            if failed:
                return 1
        elif args.command == "validate":
            if args.format == CANONICAL_FORMAT:
                path = args.path if args.path.is_file() else args.path / "canonical.json"
                result = validate_path(path)
                print(json.dumps(result))
                return 0 if result["ok"] else 1
            paths = [args.path] if args.path.is_file() else sorted(args.path.glob("*.json"))
            from .integrity import eh_arquivo_de_lei
            paths = [p for p in paths if eh_arquivo_de_lei(p.name) and p.name not in ("manifest.json","known_issues.json")]
            if not paths:
                raise ValueError("No article files examined")
            results = [validate_articles(p,args.strict) for p in paths]
            print(json.dumps(results,ensure_ascii=False,indent=2))
            return 0 if all(r["ok"] for r in results) else 1
        elif args.command == "integrity":
            return 0 if verificar_integridade(str(args.path)) else 1
        elif args.command == "verify-capture":
            print(json.dumps(verify_capture(args.path),ensure_ascii=False,indent=2))
        elif args.command == "bundle":
            print(build_release(args.captures,args.output,args.version,selected_laws=args.laws))
    except Exception as exc:
        print(f"{type(exc).__name__}: operation failed; inspect input and validation report",file=sys.stderr)
        return 1
    return 0


def jurisprudence_command(args) -> int:
    """CLI-only dispatch; library APIs remain independent of argparse."""
    from .jurisprudence.catalog import catalog
    from .jurisprudence.capture import capture, verify_capture
    from .jurisprudence.corpus import build_release
    from .jurisprudence.decisions import validate_decision
    from .jurisprudence.validation import load_json, validate_document

    if args.juris_command == "catalog":
        result = catalog()
    elif args.juris_command == "extract":
        result = {"capture": str(capture(args.source, args.output, scanner=args.scanner, ca_bundle=args.ca_bundle))}
    elif args.juris_command == "validate":
        result = validate_document(load_json(args.path))
    elif args.juris_command == "verify-capture":
        result = verify_capture(args.path, scanner=args.scanner)
    elif args.juris_command == "validate-decision":
        record = load_json(args.path)
        if not isinstance(record, dict) or record.get("tipo") != "acordao":
            raise ValueError("Expected an individual judgment")
        validate_decision(record, require_review=args.require_review)
        result = {"ok": True, "type": "acordao", "review_required": args.require_review}
    else:
        result = {"archive": str(build_release(args.captures, args.output, args.version,
                                               selected_sources=args.sources, scanner=args.scanner,
                                               allow_samples=args.allow_samples))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
