#!/usr/bin/env python3
# Free sample from NoPip Toolkit (16 zero-dependency Python scripts): https://aayush10shah-tech.github.io/nopip-toolkit/
# This one file is free to use, modify and share.
r"""bulk_rename.py - rename many files at once, safely.

Dry run by default: nothing changes until you add --apply.
Every applied run writes an undo log you can replay with --undo.

Examples
  # IMG_0042.jpg -> trip_0042.jpg
  python bulk_rename.py ./photos --match "IMG_(\d+)" --replace "trip_\1"

  # Number files in modified-date order: 2026-03-01_001.pdf, ...
  python bulk_rename.py ./scans --template "{date}_{n:03}{ext}" --sort mtime --apply

  # Swap spaces for dashes and lowercase everything
  python bulk_rename.py ./docs --match " " --replace "-" --lower --apply

  # Undo a run
  python bulk_rename.py --undo ./docs/.rename-undo-20261125-101500.json --apply

Template fields: {stem} {ext} {n} {date} {parent}
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

BAD_CHARS = set('<>:"/\\|?*')


def build_plan(folder, args):
    files = [p for p in folder.iterdir()
             if p.is_file() and not p.name.startswith(".rename-undo-")]
    if args.glob:
        files = [p for p in files if p.match(args.glob)]
    if args.sort == "mtime":
        files.sort(key=lambda p: p.stat().st_mtime)
    else:
        files.sort(key=lambda p: p.name.lower())

    pattern = re.compile(args.match) if args.match else None
    plan, n = [], args.start
    for p in files:
        if pattern:
            if not pattern.search(p.stem):
                continue
            name = pattern.sub(args.replace, p.stem) + p.suffix
        elif args.template:
            date = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
            try:
                name = args.template.format(stem=p.stem, ext=p.suffix, n=n,
                                            date=date, parent=folder.name)
            except (KeyError, IndexError, ValueError) as e:
                sys.exit(f"Bad template: {e}")
            n += 1
        else:
            name = p.name
        if args.lower:
            name = name.lower()
        if not name.strip() or BAD_CHARS & set(name):
            sys.exit(f"Refusing: {p.name!r} would become invalid name {name!r}")
        if name != p.name:
            plan.append((p, p.with_name(name)))
    return plan


def validate(plan):
    sources = [s for s, _ in plan]
    seen, problems = {}, []
    for src, dst in plan:
        key = os.path.normcase(str(dst))
        if key in seen:
            problems.append(f"{seen[key]} and {src.name} would both become {dst.name}")
        seen[key] = src.name
        if dst.exists() and not any(dst.samefile(s) for s in sources if s.exists()):
            problems.append(f"{dst.name} already exists (target of {src.name})")
    return problems


def execute(plan):
    # Two phases so swaps (a->b, b->a) and case-only renames work everywhere.
    staged = []
    for i, (src, dst) in enumerate(plan):
        tmp = src.with_name(f".bulkrename-{os.getpid()}-{i}{src.suffix}")
        src.rename(tmp)
        staged.append((tmp, dst))
    for tmp, dst in staged:
        tmp.rename(dst)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", type=Path)
    ap.add_argument("--match", help="regex searched in the name (extension excluded)")
    ap.add_argument("--replace", default="", help=r"replacement text; \1 inserts group 1")
    ap.add_argument("--template", help="new name, e.g. '{date}_{n:03}{ext}'")
    ap.add_argument("--glob", help="only touch files like this, e.g. '*.jpg'")
    ap.add_argument("--sort", choices=["name", "mtime"], default="name", help="order for {n}")
    ap.add_argument("--start", type=int, default=1, help="first value of {n}")
    ap.add_argument("--lower", action="store_true", help="lowercase the result")
    ap.add_argument("--undo", type=Path, help="replay an undo log")
    ap.add_argument("--apply", action="store_true", help="really rename (default: dry run)")
    args = ap.parse_args()

    if args.undo:
        entries = json.loads(args.undo.read_text(encoding="utf-8"))
        plan = [(Path(e["from"]), Path(e["to"])) for e in entries]
        missing = [str(s) for s, _ in plan if not s.exists()]
        if missing:
            sys.exit("Cannot undo, these files are gone:\n  " + "\n  ".join(missing))
    else:
        if not args.folder or not args.folder.is_dir():
            ap.error("give a folder (or --undo LOG)")
        if args.match and args.template:
            ap.error("use --match or --template, not both")
        if not (args.match or args.template or args.lower):
            ap.error("nothing to do: add --match, --template or --lower")
        plan = build_plan(args.folder, args)

    if not plan:
        print("Nothing to rename.")
        return
    for src, dst in plan:
        print(f"  {src.name}  ->  {dst.name}")
    problems = validate(plan)
    if problems:
        print("\nStopped, nothing renamed:")
        for p in problems:
            print("  !", p)
        sys.exit(1)
    if not args.apply:
        print(f"\nDry run: {len(plan)} file(s) would be renamed. Add --apply to do it.")
        return

    log = [{"from": str(d.absolute()), "to": str(s.absolute())} for s, d in plan]
    execute(plan)
    if not args.undo:
        stamp, i = f"{datetime.now():%Y%m%d-%H%M%S}", 1
        log_path = args.folder / f".rename-undo-{stamp}.json"
        while log_path.exists():
            log_path, i = args.folder / f".rename-undo-{stamp}-{i}.json", i + 1
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        print(f"\nRenamed {len(plan)} file(s). Undo with:\n  python {Path(__file__).name} --undo \"{log_path}\" --apply")
    else:
        print(f"\nRestored {len(plan)} file(s).")


if __name__ == "__main__":
    main()
