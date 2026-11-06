import os
import tempfile

# Must run BEFORE the backend is imported: use a throwaway data folder and the fake test embedder.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="chatbot-test-")
os.environ["EMBEDDING_BACKEND"] = "hash"
os.environ["MIN_SCORE"] = "0.2"
os.environ["GUARD_MODEL"] = ""
os.environ["QUERY_REWRITE"] = "false"   # the rewrite test switches it on itself
os.environ["RATE_LIMIT_PER_MIN"] = "1000"   # the rate-limit test lowers this itself
os.environ["LOGIN_RATE_LIMIT_PER_MIN"] = "1000"   # the login rate-limit test lowers this itself
