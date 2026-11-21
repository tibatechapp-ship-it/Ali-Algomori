# GEOLOGIA command-line interface (no extra dependencies).
# Usage:
#   geologia plan "طلب بالعربية أو English" [--lang ar|en] [--bbox X1 Y1 X2 Y2]
#   geologia domains
#   geologia engines [--domain DOMAIN]
#   geologia engine ENGINE_ID
#   geologia serve [--host HOST] [--port PORT]
# Or: python -m geologia ...
import argparse
import json
import sys
from typing import List, Optional

from geologia import __version__
from geologia.planner import UnknownDomainError, build_plan
from geologia.registry import get_engine, list_engines


def _print(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geologia",
        description="GEOLOGIA foundation CLI — registry + planner (plans only).",
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
    p_serve = sub.add_parser("serve", help="run the API locally (needs uvicorn)")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
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

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("[!] uvicorn غير مثبّت: pip install uvicorn", file=sys.stderr)
            return 2
        uvicorn.run("geologia.api:app", host=args.host, port=args.port)
        return 0

    return 2  # unreachable: argparse rejects unknown commands


if __name__ == "__main__":
    raise SystemExit(main())
