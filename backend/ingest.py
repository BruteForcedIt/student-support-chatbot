"""Read an uploaded file, cut it into chunks, embed them and store them in the vector database."""
import re
from pathlib import Path

from . import config, embeddings, vectorstore

_CJK = re.compile(r"[\u4e00-\u9fff]")
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    """Read a simple '---' header (title, source_url, category) from a Markdown file."""
    match = _FRONT.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return meta, text[match.end():]


def _length(text: str) -> int:
    """Rough size: words, counting each Chinese character as one word."""
    return len(_CJK.findall(text)) + len(_CJK.sub(" ", text).split())


def extract_sections(path: Path) -> list[tuple[int, str]]:
    """Return [(page_number, text)]. page_number is 0 when the format has no pages."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        sections = [(i + 1, (page.extract_text() or "").strip()) for i, page in enumerate(reader.pages)]
    elif ext == ".docx":
        import docx

        document = docx.Document(str(path))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                lines.append(" | ".join(cell.text.strip() for cell in row.cells))
        sections = [(0, "\n".join(lines))]
    elif ext in (".txt", ".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if ext == ".md":
            text = split_front_matter(text)[1]
        sections = [(0, text)]
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    sections = [(page, text) for page, text in sections if text.strip()]
    if sum(len(t) for _, t in sections) < 20:
        raise ValueError("No readable text found. Scanned PDFs need OCR first - upload a text-based file.")
    return sections


_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


def split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split Markdown text at its headings. Returns [(heading, body)], where heading is like
    "Living in halls" or "Fees > Paying rent". Text with no headings comes back as [("", text)]."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    path: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            level = len(match.group(1))
            if level == 1:          # the document title: already added to every chunk's search text
                path = []
            else:
                path = path[:level - 2] + [match.group(2)]
            sections.append((" > ".join(path), []))
        else:
            sections[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "\n".join(lines).strip()]


_TABLE_ROW = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def flatten_tables(text: str) -> str:
    """Rewrite Markdown table rows as plain lines that name each column, e.g. "| J2 Mabul | 019-203 1853 |"
    under the header "| Hall | Phone |" becomes "Hall: J2 Mabul; Phone: 019-203 1853". A small chat
    model reads these far more reliably than a long grid, and each line still makes sense on its own."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        header = _TABLE_ROW.match(lines[i])
        if header and i + 1 < len(lines) and _TABLE_RULE.match(lines[i + 1]):
            names = [c.strip() for c in header.group(1).split("|")]
            i += 2
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                cells = [c.strip() for c in _TABLE_ROW.match(lines[i]).group(1).split("|")]
                out.append("; ".join(f"{n}: {c}" if n else c for n, c in zip(names, cells) if c))
                i += 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)


def chunk_sections(text: str) -> list[str]:
    """Chunk each heading's section on its own and start every chunk with its heading, so a piece
    such as the second half of a phone-number table still says what the numbers are for."""
    chunks = []
    for heading, body in split_by_headings(flatten_tables(text)):
        for piece in chunk_text(body):
            chunks.append(f"{heading}\n{piece}" if heading else piece)
    return chunks


def chunk_text(text: str, max_words: int = config.CHUNK_WORDS, overlap: int = config.CHUNK_OVERLAP_WORDS) -> list[str]:
    """Cut text into pieces of about max_words words, keeping paragraphs together,
    with a small overlap so an answer that sits on a boundary is not lost."""
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    units: list[str] = []
    for para in paragraphs:
        words = para.split()
        if _length(para) <= max_words or len(words) <= 1:
            units.append(para)
        else:  # one very long paragraph: split it into overlapping windows
            step = max(1, max_words - overlap)
            for i in range(0, len(words), step):
                units.append(" ".join(words[i:i + max_words]))
                if i + max_words >= len(words):
                    break

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for unit in units:
        unit_size = _length(unit)
        if current and size + unit_size > max_words:
            chunks.append("\n".join(current))
            tail = " ".join(" ".join(current).split()[-overlap:]) if overlap else ""
            current, size = ([tail] if tail else []), _length(tail)
        current.append(unit)
        size += unit_size
    if current:
        chunks.append("\n".join(current))
    return chunks


def index_document(doc_id: str, path: Path, title: str, category: str, source_url: str, version: int) -> int:
    """(Re)build the stored chunks for one document. Returns the number of chunks.

    Safe order: read + embed first (can fail), THEN swap out the old chunks (fast),
    so a failed upload never destroys the version students are already using."""
    try:
        sections = extract_sections(path)
    except ValueError:
        raise
    except Exception as exc:      # a damaged or unusual PDF/DOCX makes the reader library crash
        raise ValueError("This file could not be read. Check that it opens normally, "
                         "or save it again as PDF, DOCX, TXT or MD.") from exc
    chunks = [{"text": chunk, "page": page} for page, text in sections for chunk in chunk_sections(text)]
    vectors = embeddings.embed([f"{title}\n{c['text']}" for c in chunks])  # title helps the match
    vectorstore.delete_doc(doc_id)
    vectorstore.add_chunks(
        doc_id, chunks, vectors,
        {"title": title, "category": category, "source_url": source_url or "", "version": version},
    )
    return len(chunks)
