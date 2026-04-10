import argparse
from dataclasses import dataclass
from pathlib import Path

from benchmarkdown.__version__ import __version__


@dataclass
class Config:
    inputs: list[Path]
    output_path: Path | None

def parse_commandline_args() -> Config:
    parser = argparse.ArgumentParser(
        prog="benchmarkdown",
        description="Generates a markdown report from Bechcomp results",
        usage="%(prog)s [OPTION ...] PATH...",
        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=80)
    )

    parser.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        metavar="PATH",
        help="path to the baseline macrobenchmark report directory or file",
    )

    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    parser.add_argument(
        "-o",
        "--out",
        dest="out",
        type=Path,
        metavar="OUT",
        help="path to output file"
    )

    args = parser.parse_args()

    return Config(
        inputs=args.inputs,
        output_path=args.out,
    )
