import os
import psycopg2
import requests
from flask import Flask, redirect, request
from main import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, api_endpoint

app = Flask(__name__)

# 레일웨이가 제공하는 내부 PostgreSQL 주소를 환경변수에서 자동으로 가져옵니다.
DATABASE_URL = os.getenv("DATABASE_URL")

# 디스코드 개발자 포털에 등록한 콜백 주소와 완벽하게 일치해야 합니다.
REDIRECT_URI = "https://kb-restore.o-r.kr/join"


def init_db():
    """서버가 시작될 때 데이터베이스에 테이블이 없으면 자동으로 생성해 주는 기능입니다."""
    if not DATABASE_URL:
        print("경고: DATABASE_URL 환경변수가 설정되지 않았습니다.")
        return
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()

    # 1. guilds 테이블 생성
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            id BIGINT PRIMARY KEY,
            token TEXT,
            expiredate TEXT,
            link TEXT
        );
    """
    )

    # 2. users 테이블 생성 (기존 SQLite의 복합 UNIQUE 설정을 PRIMARY KEY로 이주)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGINT,
            token TEXT,
            guild_id BIGINT,
            PRIMARY KEY (id, guild_id)
        );
    """
    )
    con.commit()
    con.close()
    print("PostgreSQL 테이블 초기화 완료!")


@app.route("/join")
def join():
    guild_id = request.args.get("state")
    auth_url = f"{api_endpoint}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify+guilds.join&state={guild_id}"
    return redirect(auth_url)


@app.route("/callback")  # 만약 디스코드 포털 리다이렉트 주소가 /callback 이면 여기로 들어옵니다.
def callback():
    code = request.args.get("code")
    guild_id = request.args.get("state")

    if not code:
        return "인증 코드가 없습니다. 다시 시도해주세요."

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }

    # 토큰 교환
    res = requests.post(f"{api_endpoint}/oauth2/token", data=data)
    token_data = res.json()

    if "access_token" not in token_data:
        return f"인증 실패: {token_data}"

    # 유저 정보 가져오기
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    user_res = requests.get(f"{api_endpoint}/users/@me", headers=headers)
    user_id = user_res.json()["id"]

    # DB 저장 (PostgreSQL Upsert 문법 적용)
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO users (id, token, guild_id) VALUES (%s, %s, %s)
        ON CONFLICT (id, guild_id) 
        DO UPDATE SET token = EXCLUDED.token;
    """,
        (int(user_id), token_data["refresh_token"], int(guild_id)),
    )
    con.commit()
    con.close()

    return "인증이 완료되었습니다! 창을 닫아주세요."


if __name__ == "__main__":
    init_db()  # 서버 켜질 때 테이블 자동 생성 실행

    # 레일웨이 포트 바인딩 오류를 방지하기 위해 환경변수 PORT를 사용합니다.
    port = int(os.getenv("PORT", 80))
    app.run(host="0.0.0.0", port=port)