# GEOLOGIA command-line interface (no extra dependencies).
# Usage:
#   geologia plan "طلب بالعربية أو English" [--lang ar|en] [--bbox X1 Y1 X2 Y2]
#   geologia domains
#   geologia engines [--domain DOMAIN]
#   geologia engine ENGINE_ID
#   geologia knowledge search "سؤال" [--top-k N] [--scope all|catalog|digest|engine_kb]
#   geologia knowledge add FILE --title "عنوان" [--author ...] [--year N]
#   geologia verify PATH [--type auto|las|geojson|csv|tiff]
#   geologia dataset add NAME PATH [--dtype auto] [--crs ...] [--units ...]
#   geologia dataset list | geologia dataset validate ID | geologia dataset checksum ID
#   geologia certify ENGINE_ID           (first-party engines only)
#   geologia task create TITLE ENGINE_ID DS... [--param KEY=VAL ...]
#   geologia task list | geologia task go ID STATE
#   geologia task execute ID | geologia task report ID | geologia task verify ID
#   geologia serve [--host HOST] [--port PORT]
# Or: python -m geologia ...
import argparse
import json
import sys
from typing import List, Optional

from geologia import __version__
from geologia.planner import UnknownDomainError, build_plan
from geologia.registry import get_engine, list_engines


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geologia",
        description="GEOLOGIA foundation CLI — registry + planner + knowledge + data verification.",
    )
    parser.add_argument("--version", action="version", version=f"geologia {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="build a deterministic analysis plan (plans only)")
    p_plan.add_argument("request", help="the user request, in Arabic or English")
    p_plan.add_argument("--lang", choices=["ar", "en"], default="ar")
    p_plan.add_argument("--bbox", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"),
                        help="area of interest bounding box")

    sub.add_parser("domains", help="list supported analysis domains")
    p_eng = sub.add_parser("engines", help="list registry engine cards")
    p_eng.add_argument("--domain", default=None)
    p_det = sub.add_parser("engine", help="show one engine card")
    p_det.add_argument("engine_id")

    p_cer = sub.add_parser(
        "certify", help="certify a first-party engine via its pinned reference test")
    p_cer.add_argument("engine_id")

    p_k = sub.add_parser("knowledge", help="knowledge base (retrieval-only)")
    ksub = p_k.add_subparsers(dest="kcmd", required=True)
    p_kq = ksub.add_parser("search")
    p_kq.add_argument("query")
    p_kq.add_argument("--top-k", type=int, default=5)
    p_kq.add_argument("--scope", default="all",
                      choices=["all", "catalog", "digest", "engine_kb", "user_corpus"])
    p_ka = ksub.add_parser("add")
    p_ka.add_argument("file")
    p_ka.add_argument("--title", required=True)
    p_ka.add_argument("--author", default="")
    p_ka.add_argument("--year", type=int, default=None)
    ksub.add_parser("stats")

    p_v = sub.add_parser("verify", help="validate a data file (LAS/GeoJSON/CSV/TIFF)")
    p_v.add_argument("path")
    p_v.add_argument("--type", default="auto",
                     choices=["auto", "las", "geojson", "csv", "tiff"])

    p_d = sub.add_parser("dataset", help="dataset registry")
    dsub = p_d.add_subparsers(dest="dcmd", required=True)
    p_da = dsub.add_parser("add")
    p_da.add_argument("name")
    p_da.add_argument("path")
    p_da.add_argument("--dtype", default="auto",
                      choices=["auto", "las", "geojson", "csv", "tiff"])
    p_da.add_argument("--crs", default=None)
    p_da.add_argument("--units", default=None)
    dsub.add_parser("list")
    p_dv = dsub.add_parser("validate")
    p_dv.add_argument("dataset_id")
    p_dc = dsub.add_parser("checksum")
    p_dc.add_argument("dataset_id")

    p_t = sub.add_parser("task", help="task ledger with gates")
    tsub = p_t.add_subparsers(dest="tcmd", required=True)
    p_tc = tsub.add_parser("create")
    p_tc.add_argument("title")
    p_tc.add_argument("engine_id")
    p_tc.add_argument("dataset_ids", nargs="+")
    p_tc.add_argument("--param", action="append", default=[],
                      metavar="KEY=VAL", help="engine parameter (repeatable)")
    tsub.add_parser("list")
    p_tg = tsub.add_parser("go")
    p_tg.add_argument("task_id")
    p_tg.add_argument("to_state")
    p_te = tsub.add_parser("execute", help="run the certified engine (gates enforced)")
    p_te.add_argument("task_id")
    p_tr = tsub.add_parser("report", help="show the execution evidence report")
    p_tr.add_argument("task_id")
    p_tv = tsub.add_parser("verify", help="mark executed task verified (evidence gate)")
    p_tv.add_argument("task_id")

    p_serve = sub.add_parser("serve", help="run the API locally (needs uvicorn)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    p_about = sub.add_parser(
        "about",
        help="project status, support appeal, and rights notice (bilingual)",
    )
    p_about.add_argument("--lang", choices=["ar", "en", "both"], default="both")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "plan":
        try:
            plan = build_plan(args.request, args.lang, args.bbox)
        except UnknownDomainError as exc:
            _print({
                "error": "unknown_domain",
                "message": exc.message,
                "supported_domains": exc.supported_domains,
            })
            print(
                "[!] لم يُبنَ أي plan — أعد صياغة الطلب بإحدى المجالات المدعومة أعلاه.",
                file=sys.stderr,
            )
            return 2
        _print(plan)
        return 0

    if args.command == "domains":
        from geologia.planner import list_planner_domains
        items = list_planner_domains()
        _print({"count": len(items), "domains": items})
        return 0

    if args.command == "engines":
        items = list_engines(args.domain)
        _print({"count": len(items), "engines": items})
        return 0

    if args.command == "engine":
        card = get_engine(args.engine_id)
        if card is None:
            print(f"[!] engine_id {args.engine_id!r} غير موجود في السجل.", file=sys.stderr)
            return 2
        _print(card)
        return 0

    if args.command == "certify":
        from geologia.data_layer.certification import CertificationRefused, certify_engine
        try:
            report = certify_engine(args.engine_id)
        except ValueError as exc:
            print(f"[!] {exc}", file=sys.stderr)
            return 2
        except CertificationRefused as exc:
            _print({"error": "certification_refused", "reasons": exc.reasons,
                    "message": str(exc)})
            print("[!] رُفض الاعتماد — هذا سلوك مقصود (سياسة الدمج).", file=sys.stderr)
            return 3
        _print(report)
        return 0 if report["certified"] else 3

    if args.command == "knowledge":
        from geologia.knowledge.retrieval import get_kb
        kb = get_kb()
        if args.kcmd == "search":
            _print(kb.search(args.query, top_k=args.top_k, scope=args.scope))
            return 0
        if args.kcmd == "add":
            try:
                _print(kb.add_document(args.file, args.title, author=args.author,
                                       year=args.year))
            except (FileNotFoundError, ValueError) as exc:
                print(f"[!] {exc}", file=sys.stderr)
                return 2
            return 0
        if args.kcmd == "stats":
            _print(kb.stats())
            return 0

    if args.command == "verify":
        from geologia.data_layer.validators import validate_file
        _print(validate_file(args.path, args.type))
        return 0 if _status_of(args) else 1

    if args.command == "dataset":
        from geologia.data_layer import records as ds
        if args.dcmd == "add":
            try:
                _print(ds.register_dataset(
                    name=args.name, path=args.path, dtype=args.dtype,
                    declared_crs=args.crs, declared_units=args.units))
            except (FileNotFoundError, ValueError) as exc:
                print(f"[!] {exc}", file=sys.stderr)
                return 2
            return 0
        if args.dcmd == "list":
            items = ds.list_datasets()
            _print({"count": len(items), "datasets": items})
            return 0
        if args.dcmd == "validate":
            try:
                result = ds.validate_dataset(args.dataset_id)
            except KeyError:
                print("[!] dataset_id غير موجود.", file=sys.stderr)
                return 2
            _print(result)
            return 0 if result["validation"]["status"] == "pass" else 1
        if args.dcmd == "checksum":
            try:
                result = ds.verify_checksum(args.dataset_id)
            except KeyError:
                print("[!] dataset_id غير موجود.", file=sys.stderr)
                return 2
            _print(result)
            return 0 if result["checksum_ok"] else 1

    if args.command == "task":
        from geologia.data_layer import tasks as tl
        if args.tcmd == "create":
            params = {}
            for kv in args.param:
                key, _, val = kv.partition("=")
                try:
                    params[key.strip()] = float(val) if "." in val else int(val)
                except ValueError:
                    params[key.strip()] = val
            try:
                _print(tl.create_task(title=args.title, engine_id=args.engine_id,
                                      dataset_ids=args.dataset_ids, params=params))
            except ValueError as exc:
                print(f"[!] {exc}", file=sys.stderr)
                return 2
            return 0
        if args.tcmd == "list":
            items = tl.list_tasks()
            _print({"count": len(items), "tasks": items})
            return 0
        if args.tcmd == "go":
            try:
                _print(tl.transition(args.task_id, args.to_state))
            except KeyError:
                print("[!] task_id غير موجود.", file=sys.stderr)
                return 2
            except tl.TaskGateError as exc:
                _print({"error": "gate_refused", "gate": exc.gate, "message": exc.message})
                print("[!] البوابة رفضت الانتقال — هذا سلوك مقصود.", file=sys.stderr)
                return 3
            except ValueError as exc:
                print(f"[!] {exc}", file=sys.stderr)
                return 2
            return 0
        if args.tcmd in ("execute", "verify"):
            target = "executed" if args.tcmd == "execute" else "verified"
            try:
                _print(tl.transition(args.task_id, target, reason=f"cli {args.tcmd}"))
            except KeyError:
                print("[!] task_id غير موجود.", file=sys.stderr)
                return 2
            except tl.TaskGateError as exc:
                _print({"error": "gate_refused", "gate": exc.gate, "message": exc.message})
                print("[!] البوابة رفضت التنفيذ — هذا سلوك مقصود.", file=sys.stderr)
                return 3
            return 0
        if args.tcmd == "report":
            import json as _json
            from pathlib import Path as _Path
            task = tl.get_task(args.task_id)
            if task is None:
                print("[!] task_id غير موجود.", file=sys.stderr)
                return 2
            path = task.get("execution_report_path")
            if not path or not _Path(path).exists():
                _print({"error": "no_execution_report",
                        "message": "المهمة لم تُنفذ بعد — لا تقرير أدلة"})
                return 1
            _print(_json.loads(_Path(path).read_text(encoding="utf-8")))
            return 0

    if args.command == "about":
        from geologia.about import banner
        print(banner(args.lang))
        return 0

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("[!] uvicorn غير مثبّت: pip install uvicorn", file=sys.stderr)
            return 2
        from geologia.about import banner
        print(banner("both"), file=sys.stderr)  # notice at service start
        uvicorn.run("geologia.api:app", host=args.host, port=args.port)
        return 0

    return 2  # unreachable: argparse rejects unknown commands


def _status_of(args) -> bool:
    from geologia.data_layer.validators import validate_file
    return validate_file(args.path, args.type)["status"] == "pass"


if __name__ == "__main__":
    raise SystemExit(main())
