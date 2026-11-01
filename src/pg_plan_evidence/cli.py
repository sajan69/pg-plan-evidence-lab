"""Offline commands. Error messages do not repeat input values or paths."""
import argparse
import os
import sys
from . import __version__
from .analysis import compare, inspect
from .contract import EvidenceError
from .io import read, write


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline PostgreSQL plan evidence")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("inspect")
    one.add_argument("plan")
    one.add_argument("--manifest", required=True)
    one.add_argument("--out", required=True)
    two = sub.add_parser("compare")
    two.add_argument("left")
    two.add_argument("right")
    two.add_argument("--left-manifest", required=True)
    two.add_argument("--right-manifest", required=True)
    two.add_argument("--out", required=True)
    for command in (one, two):
        command.add_argument("--format", choices=("json", "csv", "html"), default="json")
    args = parser.parse_args(argv)
    try:
        if os.path.lexists(args.out):
            raise EvidenceError("output_exists")
        def capture(plan, context):
            return inspect(read(plan, 2 * 1024 * 1024), read(context, 16384))
        if args.command == "inspect":
            result = capture(args.plan, args.manifest)
        else:
            result = compare(capture(args.left, args.left_manifest),
                             capture(args.right, args.right_manifest))
        write(args.out, result, args.format)
        print("written")
        return 0
    except EvidenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
    except OSError:
        print("error: file_operation", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
