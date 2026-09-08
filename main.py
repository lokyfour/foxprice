"""CLI entry point for Foxprice.

Commands:
  run (default): load parts, load pricing tiers from CSV,
    run orchestrator, save Excel report.
  new-adapter NAME: scaffold a new adapter file.
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from loguru import logger

from foxprice.core.orchestrator import run as orchestrator_run
from foxprice.core.pricing import PricingEngine
from foxprice.core.reporter import Reporter

# Register your adapters here
ADAPTERS: list = []


def load_parts(path: str) -> list[str]:
    p = Path(path)
    parts: list[str] = []

    if p.suffix == ".csv":
        with p.open(newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
        if not rows:
            return parts
        header = [c.strip().lower() for c in rows[0]]
        if "part_number" in header:
            col = header.index("part_number")
            data_rows = rows[1:]
        else:
            col = 0
            data_rows = rows
        for row in data_rows:
            if not row:
                continue
            value = row[col].strip()
            if not value or value.startswith("#"):
                continue
            parts.append(value)
    else:
        with p.open() as f:
            for line in f:
                value = line.strip()
                if not value or value.startswith("#"):
                    continue
                parts.append(value)

    return parts


def load_tiers_from_csv(path: str) -> PricingEngine:
    p = Path(path)
    if not p.exists():
        logger.error(f"pricing tiers file not found: {path}")
        sys.exit(1)

    rows: list[tuple] = []
    with p.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                (
                    row["price_from"],
                    row["price_to"],
                    row["markup_pct"],
                    int(row["min_order_qty"]),
                )
            )

    return PricingEngine.from_rows(rows)


_ADAPTER_TEMPLATE = '''"""Adapter for {name}."""

from playwright.async_api import BrowserContext

from foxprice.core.base_adapter import BaseAdapter
from foxprice.core.models import ErrorResult, PriceOffer


class {class_name}(BaseAdapter):
    SUPPLIER_NAME = "{name}"

    async def login(self, context: BrowserContext) -> None:
        # TODO: implement login flow for {name}
        raise NotImplementedError

    async def fetch_offers(
        self, context: BrowserContext, part_number: str
    ) -> tuple[list[PriceOffer], list[ErrorResult]]:
        # TODO: implement search + parsing for {name}
        raise NotImplementedError
'''


def scaffold_adapter(name: str) -> None:
    path = Path("foxprice") / "adapters" / f"{name}.py"
    if path.exists():
        logger.error(f"adapter already exists: {path}")
        sys.exit(1)

    class_name = name.title().replace("-", "").replace("_", "") + "Adapter"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_ADAPTER_TEMPLATE.format(name=name, class_name=class_name))
    logger.info(f"scaffold created: {path}")


async def _run_command(args: argparse.Namespace) -> None:
    parts = load_parts(args.input)
    engine = load_tiers_from_csv(args.tiers)

    known_names = {a.SUPPLIER_NAME for a in ADAPTERS}
    skip_set = set()
    for name in args.skip:
        if name not in known_names:
            logger.warning(f"unknown adapter in --skip, ignoring: {name}")
            continue
        skip_set.add(name)

    adapters = [a for a in ADAPTERS if a.SUPPLIER_NAME not in skip_set]
    if not adapters:
        logger.error("no adapters to run after filtering")
        sys.exit(1)

    if args.dry_run:
        logger.info(f"dry-run: {len(parts)} parts, {len(adapters)} adapters — exiting")
        return

    priced, errors, summary = await orchestrator_run(
        adapters, parts, engine, parallel=args.parallel
    )
    Reporter(args.output).generate(priced, errors, summary)

    logger.info(
        f"run {summary.run_id}: found={summary.parts_found} "
        f"errors={summary.errors} duration={summary.duration_sec:.1f}s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Foxprice CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the pricing scrape")
    run_parser.add_argument("--input", type=str, default="parts.txt")
    run_parser.add_argument("--tiers", type=str, default="pricing_tiers.csv")
    run_parser.add_argument("--output", type=str, default="output")
    run_parser.add_argument("--skip", type=str, nargs="*", default=[])
    run_parser.add_argument("--parallel", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")

    new_adapter_parser = subparsers.add_parser("new-adapter", help="Scaffold a new adapter file")
    new_adapter_parser.add_argument("name", type=str)

    # No subcommand given defaults to "run" so `foxprice --input x.txt`
    # works the same as `foxprice run --input x.txt`. Checked against
    # subparsers.choices (not a hardcoded list) so new subcommands don't
    # need this logic updated. A two-pass parse_args() reparse doesn't
    # work here: with no subcommand, flags like --input aren't defined
    # on the top-level parser, so parsing them fails before `command`
    # can even be inspected.
    argv = sys.argv[1:]
    if not argv or argv[0] not in (*subparsers.choices, "-h", "--help"):
        argv = ["run", *argv]

    args = parser.parse_args(argv)

    if args.command == "new-adapter":
        scaffold_adapter(args.name)
        return

    asyncio.run(_run_command(args))


if __name__ == "__main__":
    main()
