import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 1. 로컬 환경(.env 파일)이 존재할 때만 읽어오기
def load_local_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # os.environ.setdefault는 이미 설정된 환경변수(Railway 등)가 있다면 덮어쓰지 않습니다.
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

# 2. 전역적으로 사용할 헬퍼 함수 (모듈 수준에 배치)
def _required(name):
    value = os.getenv(name)
    if not value or not value.strip():
        raise RuntimeError(f"{name} 환경변수가 설정되지 않았습니다. Railway Variables 설정을 확인하세요.")
    return value.strip()

def _optional_int(name, default=0):
    value = os.getenv(name)
    return int(value) if value and value.strip().isdigit() else default

# --- 실행부 ---
load_local_env()

# 변수 설정
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