import os
from flask import Flask, request, redirect
import requests
import psycopg2  # 내 컴퓨터에선 에러 나도 괜찮습니다. 레일웨이가 설치해 줍니다!
from main import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, api_endpoint

app = Flask(__name__)

# 레일웨이가 제공하는 PostgreSQL 주소를 환경변수에서 자동으로 가져옵니다.
DATABASE_URL = os.getenv("DATABASE_URL")

# 디스코드 개발자 포털에 등록한 콜백 주소
REDIRECT_URI = "https://kb-restore.o-r.kr/callback"


def init_db():
    """서버가 켜질 때 PostgreSQL에 테이블이 없으면 자동으로 만들어주는 함수입니다."""
    if not DATABASE_URL:
        print("경고: DATABASE_URL 환경변수가 설정되지 않았습니다.")
        return
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    # 디스코드 ID는 숫자가 매우 길기 때문에 VARCHAR(50)로 저장하는 것이 안전합니다.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(50),
            token TEXT,
            guild_id VARCHAR(50),
            PRIMARY KEY (id, guild_id)
        );
    """
    )
    con.commit()
    con.close()


@app.route("/join")
def join():
    guild_id = request.args.get("state")
    auth_url = f"{api_endpoint}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify+guilds.join&state={guild_id}"
    return redirect(auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    guild_id = request.args.get('state')

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

    # DB 저장 (PostgreSQL 전용 Upsert 문법으로 교체 완료)
    con = psycopg2.connect(DATABASE_URL)
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO users (id, token, guild_id) VALUES (%s, %s, %s)
        ON CONFLICT (id, guild_id) 
        DO UPDATE SET token = EXCLUDED.token;
    """,
        (str(user_id), token_data["refresh_token"], str(guild_id)),
    )
    con.commit()
    con.close()

    return "인증이 완료되었습니다! 창을 닫아주세요."


if __name__ == "__main__":
    init_db()  # 데이터베이스 테이블 초기화 실행

    # [중요] 레일웨이는 내부적으로 무작위 포트를 배정하므로 os.getenv('PORT') 설정이 필수입니다.
    port = int(os.getenv("PORT", 80))
    app.run(host="0.0.0.0", port=port)