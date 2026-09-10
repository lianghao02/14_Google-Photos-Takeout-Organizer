from __future__ import annotations
import argparse
from pathlib import Path
from .service import analyze
from .exporter import export
from .verifier import verify

from . import __version__

def main() -> None:
    parser = argparse.ArgumentParser(prog="gpto")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    a = commands.add_parser("analyze"); a.add_argument("inputs", nargs="+"); a.add_argument("--work", default="work")
    e = commands.add_parser("export"); e.add_argument("--manifest", required=True); e.add_argument("--output", required=True)
    v = commands.add_parser("verify"); v.add_argument("--manifest", required=True); v.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "analyze": print(analyze([Path(x) for x in args.inputs], Path(args.work))["summary"])
    elif args.command == "export": print(export(Path(args.manifest), Path(args.output))["summary"])
    else: print(verify(Path(args.manifest), Path(args.output)))
if __name__ == "__main__": main()
