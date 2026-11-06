"""All settings in one place. Override any of them with environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
ARCHIVE_DIR = DATA_DIR / "archive"        # old versions / deleted files are moved here
CHROMA_DIR = DATA_DIR / "chroma"          # the vector database lives here
DB_PATH = DATA_DIR / "app.db"             # SQLite: admin users, document list, audit log
FRONTEND_DIR = BASE_DIR / "frontend"

# ---- Chat model (LM Studio's local server speaks the OpenAI format) ----
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")      # dummy value, LM Studio ignores it
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.5-9b")    # copy the exact name from LM Studio
NO_THINK = os.getenv("NO_THINK", "true").lower() == "true"  # ask Qwen3 to skip its reasoning text
# Sent as "reasoning_effort" with every request. "none" stops 'thinking' models (Qwen3.5 in LM Studio 0.4+)
# spending the whole answer length on hidden reasoning, which leaves the reply empty.
# Set it to an empty value if your model server rejects the setting.
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "none")

# Optional safety model (e.g. Llama Guard 3 1B loaded in LM Studio). Empty = off.
GUARD_MODEL = os.getenv("GUARD_MODEL", "")

# ---- Embeddings (turn text into numbers) ----
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence-transformers")  # or "hash" (tests only)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")  # multilingual: English, Malay, Chinese...

# ---- Retrieval ----
TOP_K = int(os.getenv("TOP_K", "5"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.55"))   # below this = "not relevant". Tuned with eval/run_eval.py against
# unm-kb/ (4 Nov 2026, 53 questions: lowest answerable 0.565, highest unanswerable 0.542). Re-run after adding documents.
KEYWORD_SEARCH = os.getenv("KEYWORD_SEARCH", "true").lower() == "true"   # also search by exact words (names, codes)
KEYWORD_MAX_SHARE = float(os.getenv("KEYWORD_MAX_SHARE", "0.1"))   # a word in more than 10% of chunks is too common to count
KEYWORD_MIN_SCORE = float(os.getenv("KEYWORD_MIN_SCORE", "0.3"))  # meaning score a keyword match still needs
QUERY_REWRITE = os.getenv("QUERY_REWRITE", "true").lower() == "true"   # weak search: model rewords the question, search again
REWRITE_BELOW = float(os.getenv("REWRITE_BELOW", "0.6"))   # "weak" = best meaning score under this (a bit above MIN_SCORE)
CHUNK_WORDS = int(os.getenv("CHUNK_WORDS", "200"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))

# ---- Uploads ----
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
CATEGORIES = ["general", "academic", "modules", "finance", "documents", "campus"]  # match the sidebar tiles

# ---- Chat ----
MAX_MESSAGE_CHARS = 1000
MAX_HISTORY_TURNS = 6
LANGUAGES = {"en": "English", "ms": "Bahasa Melayu", "zh": "Simplified Chinese"}

# ---- Admin login ----
# Two kinds of staff account. Lecturers ("reviewer") can only use the Peer review tab.
ROLES = {"admin": "Hub staff", "reviewer": "Lecturer"}
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "8"))
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 5
LOGIN_RATE_LIMIT_PER_MIN = int(os.getenv("LOGIN_RATE_LIMIT_PER_MIN", "10"))   # sign-in attempts per minute per IP. 0 = off

# ---- Web security (see backend/security.py and README "Security") ----
# Websites (scheme://host:port) whose pages may call the API from the browser. The pages served by this
# server (/app/...) and the widget's side panel are on the same address, so they need no entry here.
# The localhost entries are for local testing (port 8000 and VS Code Live Server on 5500).
# BEFORE LAUNCH: replace them with the real UNM site address, e.g. "https://www.nottingham.edu.my".
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500",
).split(",") if o.strip()]
# Sites allowed to show the student chat page inside a frame (the side-panel widget). Every other page
# (admin page, API) can never be framed. The localhost:5500 entries are only for the VS Code Live Server
# demo pages: REMOVE THEM BEFORE LAUNCH.
FRAME_ANCESTORS = os.getenv(
    "FRAME_ANCESTORS",
    "'self' https://*.nottingham.edu.my https://*.nottingham.ac.uk http://localhost:5500 http://127.0.0.1:5500",
)
# true = the browser only reports Content-Security-Policy problems in its console instead of blocking.
# Useful for a short test after changing the pages; keep it false normally.
CSP_REPORT_ONLY = os.getenv("CSP_REPORT_ONLY", "false").lower() == "true"
MAX_JSON_KB = int(os.getenv("MAX_JSON_KB", "64"))      # largest request body for everything except uploads
# Show the automatic API pages (/docs, /redoc, /openapi.json). Off by default: they list every endpoint.
API_DOCS = os.getenv("API_DOCS", "false").lower() == "true"
# Most addresses / usernames remembered by the rate limits and the login lockout, so they cannot fill memory.
MAX_TRACKED_CLIENTS = int(os.getenv("MAX_TRACKED_CLIENTS", "10000"))

# ---- Usage metrics and abuse protection ----
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))   # chat messages per minute per browser/IP. 0 = off
# Store the text of questions the bot could NOT answer, so staff can see what documents are missing.
# Off by default: only switch on after agreeing it with the Hub (it is the only place message text is kept).
LOG_UNANSWERED = os.getenv("LOG_UNANSWERED", "false").lower() == "true"
ETHICS_DIR = DATA_DIR / "ethics"          # ethics test reports
# Release check: the overall ethics pass rate needed before release (0.9 = 90%). AGREE THIS WITH THE HUB.
ETHICS_PASS_MARK = float(os.getenv("ETHICS_PASS_MARK", "0.9"))

# ---- Contact details used in the distress message. CONFIRM THESE WITH THE HUB STAFF. ----
WELLBEING_PHONE = os.getenv("WELLBEING_PHONE", "+603 8924 8060")
WELLBEING_EMAIL = os.getenv("WELLBEING_EMAIL", "WellbeingandLearning@nottingham.edu.my")
WELLBEING_HOTLINE = os.getenv("WELLBEING_HOTLINE", "019-266 0691")   # 24/7, from the UNM anti-harassment page
SECURITY_HOTLINE = os.getenv("SECURITY_HOTLINE", "03-8924 8777")     # 24/7 campus security
EMERGENCY_NUMBER = "999"   # Malaysia's emergency number
