"""Bulk-load a folder of files into the knowledge base.

    python -m backend.ingest_folder ./unm-kb     (Markdown files keep their own title, link and category)
    python -m backend.ingest_folder ./docs --category general

.txt files in your scraped format (line 1 = title, line 2 = page URL, rest = text) are understood.
PDF, Word and Markdown files are loaded as they are, with the file name as the title."""
import argparse
from pathlib import Path

from . import config, db, ingest, service


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--category", default=None, choices=config.CATEGORIES,
                        help="force one category; otherwise a .md file's own category is used (default general)")
    args = parser.parse_args()
    db.init()

    for path in sorted(Path(args.folder).iterdir()):
        ext = path.suffix.lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            continue
        title, url, data, name = path.stem.replace("-", " "), "", path.read_bytes(), path.name
        category = args.category or "general"
        if ext == ".txt":
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if len(lines) >= 3 and lines[1].strip().startswith("http"):
                title, url = lines[0].strip(), lines[1].strip()
                data = "\n".join(lines[2:]).encode("utf-8")
        if ext == ".md":
            meta = ingest.split_front_matter(data.decode("utf-8", errors="replace"))[0]
            title, url = meta.get("title", title), meta.get("source_url", url)
            if not args.category and meta.get("category") in config.CATEGORIES:
                category = meta["category"]
        try:
            doc = service.add_document(data, name, title, category, url, "bulk-import")
            print(f"added    {doc['title']}  ({doc['chunk_count']} chunks)")
        except service.ServiceError as exc:
            print(f"skipped  {path.name}: {exc.message}")


if __name__ == "__main__":
    main()
