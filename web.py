import os
import psycopg2
import requests
from flask import Flask, redirect, request
from main import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, api_endpoint

# 1. 앱을 먼저 정의합니다! (이게 위로 와야 합니다)
app = Flask(__name__)

# 환경변수 로드
DATABASE_URL = os.getenv("DATABASE_URL")
REDIRECT_URI = "https://kb-restore.o-r.kr/callback"

def init_db():
    if not DATABASE_URL:
        print("경고: DATABASE_URL 환경변수가 설정되지 않았습니다.")
        return
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            id BIGINT PRIMARY KEY,
            token TEXT,
            expiredate TEXT,
            link TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT,
            token TEXT,
            guild_id BIGINT,
            PRIMARY KEY (id, guild_id)
        );
    """)
    con.commit()
    con.close()
    print("PostgreSQL 테이블 초기화 완료!")

# 2. 앱이 정의된 이후에 경로(route)를 추가합니다.
@app.route("/")
def index():
    return "Bot Server is Running!"

@app.route("/join")
def join():
    guild_id = request.args.get("state")
    auth_url = f"{api_endpoint}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify+guilds.join&state={guild_id}"
    return redirect(auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    guild_id = request.args.get("state")
    if not code:
        return "인증 코드가 없습니다."

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    res = requests.post(f"{api_endpoint}/oauth2/token", data=data)
    token_data = res.json()

    if "access_token" not in token_data:
        return f"인증 실패: {token_data}"

    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    user_res = requests.get(f"{api_endpoint}/users/@me", headers=headers)
    user_id = user_res.json()["id"]

    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO users (id, token, guild_id) VALUES (%s, %s, %s)
        ON CONFLICT (id, guild_id) 
        DO UPDATE SET token = EXCLUDED.token;
    """, (int(user_id), token_data["refresh_token"], int(guild_id)))
    con.commit()
    con.close()
    return "인증이 완료되었습니다! 창을 닫아주세요."

if __name__ == "__main__":
    init_db()
    # 레일웨이가 PORT를 주면 그걸 쓰고, 없으면(로컬에서는) 8080을 씁니다.
    port = int(os.environ.get("PORT", 8080)) 
    app.run(host="0.0.0.0", port=port)