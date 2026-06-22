from flask import Flask, request, redirect
import requests
import sqlite3
from main import DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, api_endpoint, DATABASE_PATH

app = Flask(__name__)

# [수정됨] 콜백 주소는 반드시 /callback 이어야 합니다.
REDIRECT_URI = "https://kb-restore.o-r.kr/callback"

@app.route('/join')
def join():
    guild_id = request.args.get('state')
    # 디스코드 인증 페이지로 유저를 보냄 (이때 리다이렉트 주소를 /callback으로 전달)
    auth_url = f"{api_endpoint}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify+guilds.join&state={guild_id}"
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    guild_id = request.args.get('state')
    
    if not code:
        return "인증 코드가 없습니다. 다시 시도해주세요."
        
    data = {
        "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI
    }
    
    # 토큰 교환
    res = requests.post(f"{api_endpoint}/oauth2/token", data=data)
    token_data = res.json()
    
    if "access_token" not in token_data:
        return f"인증 실패: {token_data}"
    
    # 유저 정보 가져오기
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    user_res = requests.get(f"{api_endpoint}/users/@me", headers=headers)
    user_id = user_res.json()['id']
    
    # DB 저장
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO users (id, token, guild_id) VALUES (?, ?, ?)", 
                (user_id, token_data['refresh_token'], guild_id))
    con.commit()
    con.close()
    
    return "인증이 완료되었습니다! 창을 닫아주세요."

if __name__ == '__main__':
    # 80번 포트는 관리자 권한이 필요할 수 있습니다. 
    # 서버 실행 시 'sudo python3 web.py' 명령어를 사용하세요.
    app.run(host='0.0.0.0', port=80)