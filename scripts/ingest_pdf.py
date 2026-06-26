from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings
from app.services.search_service import ensure_search_index, ingest_file_to_knowledge_base


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a local knowledge file into Azure AI Search.")
    parser.add_argument(
        "--file",
        default=get_settings().default_knowledge_file,
        help="Absolute path to a PDF, DOCX, PPTX, XLSX, TXT, MD, or CSV file.",
    )
    parser.add_argument("--title", default=None, help="Optional display title stored in the index.")
    args = parser.parse_args()

    if not args.file:
        raise SystemExit("Provide --file or set DEFAULT_KNOWLEDGE_FILE in .env.")

    result = {
        "index": ensure_search_index(),
        "ingestion": ingest_file_to_knowledge_base(args.file, args.title),
    }
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False, indent=2, default=str).encode("utf-8"))


if __name__ == "__main__":
    main()
