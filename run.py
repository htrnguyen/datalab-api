"""CLI entry for Datalab accurate + infographic refinement."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from app.pipeline import process_image_file, process_image_files


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(
        description="Datalab accurate OCR + infographic line split",
    )
    parser.add_argument(
        "images",
        nargs="+",
        help="Image file paths",
    )
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help="Skip infographic refinement",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write JSON to this file (single image only)",
    )
    args = parser.parse_args()

    if len(args.images) == 1:
        result = process_image_file(
            args.images[0],
            refine=not args.no_refine,
        )
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text + "\n")
        return

    results = process_image_files(
        args.images,
        refine=not args.no_refine,
    )
    out_obj = {"results": results}
    text = json.dumps(out_obj, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
