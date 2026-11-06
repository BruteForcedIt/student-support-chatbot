"""Tests for how passages are found: chunks keep their headings, keyword search catches names the
meaning search misses, and a weak search is reworded by the model and tried again. Fake chat model."""
import pytest
from fastapi.testclient import TestClient

from backend import auth, config, ingest, keyword_search, llm, rag
from backend.main import app

PASSWORD = "correct-horse-battery"
HALLS = ("---\ntitle: Hall Guide\ncategory: campus\n---\n# Hall Guide\n"
         "## Living in halls\n- Maintenance problems: report them through MaintainX.\n"
         "## After-hours emergencies: hall tutors\n| Hall | Phone |\n|---|---|\n"
         "| J1 Sipadan | 019-000 0001 |\n| J2 Mabul | 019-000 0002 |\n")
OTHER = "Students pay tuition fees by online banking or card through the student portal. " * 3


@pytest.fixture(scope="module")
def headers():
    with TestClient(app) as c:
        try:
            auth.create_user("erin", PASSWORD)
        except ValueError:
            pass
        h = {"Authorization": f"Bearer {c.post('/admin/login', json={'username': 'erin', 'password': PASSWORD}).json()['token']}"}
        ids = [c.post("/admin/documents", headers=h, data={"category": cat},
                      files={"file": (name, body.encode(), "text/plain")}).json()["id"]
               for name, body, cat in (("halls.md", HALLS, "campus"), ("fees.txt", OTHER, "finance"))]
        yield c, h
        for doc_id in ids:
            c.delete(f"/admin/documents/{doc_id}", headers=h)


def test_every_chunk_starts_with_its_heading():
    rows = "\n".join(f"| J{i} Hall | 019-{i:07d} |" for i in range(300))
    text = f"# Title\nIntro line.\n## Hall tutors\n| Hall | Phone |\n|---|---|\n{rows}"
    chunks = ingest.chunk_sections(text)
    assert chunks[0] == "Intro line."
    assert len(chunks) > 2 and all(c.startswith("Hall tutors\n") for c in chunks[1:])   # table split, label kept
    assert "Hall: J2 Hall; Phone: 019-0000002" in chunks[1]           # each row names its columns
    assert ingest.split_by_headings("no headings here") == [("", "no headings here")]


def test_keyword_search_finds_rare_names_but_ignores_common_words(headers):
    hits = keyword_search.search("hall tutor for mabul hall", 5)
    assert hits and "J2 Mabul" in hits[0]["text"]
    assert keyword_search.search("what is the", 5) == []           # only stopwords
    assert keyword_search.search("zebra crossing", 5) == []        # words in no document
    assert keyword_search.tokens("Tutors 宿舍费") == ["tutor", "宿舍", "舍费"]


def test_keyword_match_reaches_the_model_when_meaning_score_is_low(headers, monkeypatch):
    client, _ = headers
    monkeypatch.setattr(config, "MIN_SCORE", 0.99)             # meaning search alone finds nothing
    monkeypatch.setattr(config, "KEYWORD_MIN_SCORE", -1.0)
    monkeypatch.setattr(llm, "chat", lambda m, **kw: "Call 019-000 0002 [1].")
    body = client.post("/chat", json={"message": "hall tutor for mabul hall"}).json()
    assert body["answered"] and body["sources"][0]["title"] == "Hall Guide"


def test_weak_search_is_reworded_by_the_model_and_tried_again(headers, monkeypatch):
    client, _ = headers
    monkeypatch.setattr(config, "QUERY_REWRITE", True)
    monkeypatch.setattr(config, "MIN_SCORE", 0.99)
    monkeypatch.setattr(config, "KEYWORD_MIN_SCORE", -1.0)
    calls = []

    def fake_chat(messages, **kw):
        calls.append(messages)
        if messages[0]["content"] == rag.REWRITE_PROMPT:
            return "hall maintenance problem MaintainX"
        return "Report it through MaintainX [1]."
    monkeypatch.setattr(llm, "chat", fake_chat)
    body = client.post("/chat", json={"message": "my toilet is leaking in the hostel"}).json()
    assert body["answered"] and "MaintainX" in body["reply"]
    assert calls[0][1]["content"] == "my toilet is leaking in the hostel"     # rewrite saw the message only
    assert "SOURCES" not in calls[0][1]["content"]


def test_reword_failure_falls_back_quietly(headers, monkeypatch):
    client, _ = headers
    monkeypatch.setattr(config, "QUERY_REWRITE", True)
    monkeypatch.setattr(config, "MIN_SCORE", 0.99)
    monkeypatch.setattr(config, "KEYWORD_SEARCH", False)

    def down(*a, **k):
        raise ConnectionError("LM Studio is off")
    monkeypatch.setattr(llm, "chat", down)
    body = client.post("/chat", json={"message": "completely unrelated words"}).json()
    assert body["answered"] is False and "don't have" in body["reply"]


def test_rebuild_works_after_the_project_folder_moves(headers):
    from backend import db, service, vectorstore
    with db.connect() as conn:      # paths saved before the folder was moved
        conn.execute("UPDATE documents SET stored_path = '/old/place/data/uploads/' || id || '_v1' || "
                     "CASE WHEN filename LIKE '%.md' THEN '.md' ELSE '.txt' END")
    result = service.reindex_all("erin")
    assert result["failed"] == [] and result["reindexed"] >= 2
    assert keyword_search.search("mabul", 5)                       # passages are back


def test_rebuild_with_a_missing_file_keeps_the_current_index(headers):
    from backend import db, service, vectorstore
    before = vectorstore.count()
    with db.connect() as conn:
        conn.execute("UPDATE documents SET stored_path = '/nowhere/gone_v1.txt' WHERE filename = 'fees.txt'")
    result = service.reindex_all("erin")
    assert result["reindexed"] == 0 and "File not found" in result["failed"][0]["error"]
    assert vectorstore.count() == before                            # nothing was cleared
