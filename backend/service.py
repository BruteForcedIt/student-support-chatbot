"""Document management (add, replace, delete, list, re-index) and staff accounts.
The API and the command-line tools both use this."""
import hashlib
import shutil
import uuid
from pathlib import Path

from . import auth, config, db, ingest, vectorstore, embeddings


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _validate(filename: str, data: bytes, category: str, source_url: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        raise ServiceError(f"File type '{ext or 'none'}' is not allowed. Use: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}.")
    if not data:
        raise ServiceError("The file is empty.")
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise ServiceError(f"File is larger than {config.MAX_UPLOAD_MB} MB.", 413)
    if category not in config.CATEGORIES:
        raise ServiceError(f"Category must be one of: {', '.join(config.CATEGORIES)}.")
    if source_url and not source_url.startswith(("http://", "https://")):
        raise ServiceError("Source link must start with http:// or https://")
    return ext


def stored_file(doc: dict) -> Path:
    """Where a document's file is now. Only the file name from stored_path is used (we always choose
    it: <doc_id>_v<n><ext>), so the data folder keeps working after the project folder is moved."""
    return config.UPLOAD_DIR / Path(doc["stored_path"]).name


def _archive(path: Path) -> None:
    if path.exists():
        config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(config.ARCHIVE_DIR / path.name))


def _row(doc_id: str):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    if not row:
        raise ServiceError("Document not found.", 404)
    return row


def add_document(data: bytes, filename: str, title: str, category: str, source_url: str, username: str) -> dict:
    if Path(filename).suffix.lower() == ".md":   # use the file's own header if the form left these empty
        meta = ingest.split_front_matter(data.decode("utf-8", errors="replace"))[0]
        title = (title or "").strip() or meta.get("title", "")
        source_url = (source_url or "").strip() or meta.get("source_url", "")
    ext = _validate(filename, data, category, (source_url or "").strip())
    source_url = (source_url or "").strip()
    title = (title or "").strip() or Path(filename).stem
    file_hash = hashlib.sha256(data).hexdigest()

    with db.connect() as conn:
        dup = conn.execute("SELECT title FROM documents WHERE file_hash=?", (file_hash,)).fetchone()
    if dup:
        raise ServiceError(f"This exact file is already uploaded as '{dup['title']}'.", 409)

    doc_id = uuid.uuid4().hex[:12]
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = config.UPLOAD_DIR / f"{doc_id}_v1{ext}"      # never use the uploaded name as a path
    path.write_bytes(data)
    try:
        chunk_count = ingest.index_document(doc_id, path, title, category, source_url, 1)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise ServiceError(str(exc), 422) from exc
    except Exception:
        path.unlink(missing_ok=True)
        vectorstore.delete_doc(doc_id)
        raise

    now = db.now_iso()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO documents(id,title,category,source_url,filename,stored_path,file_hash,version,chunk_count,"
            "uploaded_by,uploaded_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, title, category, source_url, Path(filename).name, str(path), file_hash, 1, chunk_count, username, now, now),
        )
    db.audit(username, "upload", doc_id, f"{title} ({chunk_count} chunks)")
    return public(get_document(doc_id))


def replace_document(doc_id: str, data: bytes, filename: str, username: str,
                     title: str | None = None, category: str | None = None, source_url: str | None = None) -> dict:
    """Replace a policy with a new version. Old chunks are swapped out, so students only ever see the new one."""
    old = _row(doc_id)
    title = (title or "").strip() or old["title"]
    category = category or old["category"]
    source_url = old["source_url"] if source_url is None else source_url.strip()
    ext = _validate(filename, data, category, source_url)
    file_hash = hashlib.sha256(data).hexdigest()
    if file_hash == old["file_hash"]:
        raise ServiceError("This is the same file that is already uploaded.", 409)

    version = old["version"] + 1
    path = config.UPLOAD_DIR / f"{doc_id}_v{version}{ext}"
    path.write_bytes(data)
    # index_document reads and embeds the new file BEFORE swapping the chunks, so if anything below fails
    # the old version stays live for students. Either way the half-saved new file is removed again.
    try:
        chunk_count = ingest.index_document(doc_id, path, title, category, source_url, version)
    except ValueError as exc:       # nothing was changed in the database
        path.unlink(missing_ok=True)
        raise ServiceError(str(exc), 422) from exc
    except Exception:               # e.g. the embedding model or vector database failed
        path.unlink(missing_ok=True)
        raise

    _archive(stored_file(old))
    with db.connect() as conn:
        conn.execute(
            "UPDATE documents SET title=?, category=?, source_url=?, filename=?, stored_path=?, file_hash=?, "
            "version=?, chunk_count=?, updated_at=? WHERE id=?",
            (title, category, source_url, Path(filename).name, str(path), file_hash, version, chunk_count, db.now_iso(), doc_id),
        )
    db.audit(username, "replace", doc_id, f"{title} -> v{version} ({chunk_count} chunks)")
    return public(get_document(doc_id))


def delete_document(doc_id: str, username: str) -> None:
    old = _row(doc_id)
    vectorstore.delete_doc(doc_id)
    _archive(stored_file(old))
    with db.connect() as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    db.audit(username, "delete", doc_id, old["title"])


def public(doc: dict) -> dict:
    """What the API shows admins: no server file paths or file hashes."""
    return {k: v for k, v in doc.items() if k not in ("stored_path", "file_hash")}


def get_document(doc_id: str) -> dict:
    return dict(_row(doc_id))


def list_documents() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def reindex_all(username: str) -> dict:
    """Rebuild every document's chunks from the stored files. Needed after changing the embedding model."""
    docs = list_documents()
    missing = [{"title": d["title"], "error": f"File not found: {stored_file(d).name} in {config.UPLOAD_DIR}"}
               for d in docs if not stored_file(d).exists()]
    if missing:     # stop before clearing anything, so students keep the current search index
        return {"reindexed": 0, "failed": missing}
    vectorstore.reset()
    done, failed = 0, []
    for doc in docs:
        try:
            n = ingest.index_document(doc["id"], stored_file(doc), doc["title"], doc["category"],
                                      doc["source_url"], doc["version"])
            with db.connect() as conn:
                conn.execute("UPDATE documents SET chunk_count=? WHERE id=?", (n, doc["id"]))
            done += 1
        except Exception as exc:
            failed.append({"title": doc["title"], "error": str(exc)})
    db.audit(username, "reindex", None, f"{done} ok, {len(failed)} failed")
    return {"reindexed": done, "failed": failed}


# ------------------------------------------------------------------ staff accounts
def list_users() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute("SELECT username, role, created_at FROM users ORDER BY role, lower(username)").fetchall()
    return [dict(r) for r in rows]


def add_user(username: str, password: str, role: str, by: str) -> dict:
    """Hub staff create an account, e.g. for a lecturer who will review answers."""
    try:
        auth.create_user(username, password, role)
    except ValueError as exc:
        raise ServiceError(str(exc), 409 if "already exists" in str(exc) else 400) from exc
    username = username.strip()
    db.audit(by, "add_user", None, f"{username} ({config.ROLES[role]})")
    return next(u for u in list_users() if u["username"] == username)


def remove_user(username: str, by: str) -> None:
    """Delete an account and sign it out everywhere. Nobody can remove their own account,
    so there is always at least one Hub staff account left."""
    if username.strip().lower() == by.lower():
        raise ServiceError("You can't remove your own account.", 409)
    with db.connect() as conn:
        row = conn.execute("SELECT id, username, role FROM users WHERE lower(username)=lower(?)",
                           (username.strip(),)).fetchone()
        if not row:
            raise ServiceError("Account not found.", 404)
        conn.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
        conn.execute("DELETE FROM users WHERE id=?", (row["id"],))
    db.audit(by, "remove_user", None, f"{row['username']} ({config.ROLES.get(row['role'], row['role'])})")


def stats() -> dict:
    docs = list_documents()
    stored = vectorstore.stored_embedding_model()
    with db.connect() as conn:
        votes = dict(conn.execute("SELECT rating, COUNT(*) FROM feedback GROUP BY rating").fetchall())
    return {
        "documents": len(docs),
        "chunks": vectorstore.count(),
        "embedding_model": embeddings.model_id(),
        "chat_model": config.LLM_MODEL,
        "needs_reindex": bool(stored and stored != embeddings.model_id()),
        "categories": config.CATEGORIES,
        "feedback_up": votes.get("up", 0),
        "feedback_down": votes.get("down", 0),
    }
