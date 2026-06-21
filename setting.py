import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def _load_dotenv(path=ENV_PATH):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _required(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} 환경변수가 필요합니다. .env 파일을 확인하세요.")
    return value


def _optional_int(name, default=0):
    value = os.getenv(name, "").strip()
    return int(value) if value else default


_load_dotenv()

api_endpoint = os.getenv("DISCORD_API_ENDPOINT", "https://discord.com/api/v9")
owner = _optional_int("OWNER_ID")

DISCORD_BOT_TOKEN = _required("DISCORD_BOT_TOKEN")
DISCORD_CLIENT_ID = _required("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = _required("DISCORD_CLIENT_SECRET")
OAUTH_REDIRECT_URI = _required("OAUTH_REDIRECT_URI")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "database.db"))
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", os.urandom(32).hex())
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "80"))
