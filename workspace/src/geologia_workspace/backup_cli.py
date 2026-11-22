"""Command-line interface for offline GEOLOGIA application backups."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from geologia_workspace.application_backup import (
    create_application_backup,
    restore_application_backup,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="geologia-backup",
        description="Create or restore a self-contained offline GEOLOGIA data bundle.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="create a new backup directory")
    create.add_argument("destination", help="new backup directory; must not already exist")
    restore = commands.add_parser("restore", help="restore a backup into a new directory")
    restore.add_argument("backup_directory", help="existing verified backup directory")
    restore.add_argument("destination", help="new restore directory; must not already exist")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_application_backup(args.destination)
        else:
            result = restore_application_backup(args.backup_directory, args.destination)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
