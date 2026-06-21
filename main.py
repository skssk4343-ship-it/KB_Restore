import asyncio
import datetime
import sqlite3
import uuid
from datetime import timedelta
import discord
from discord.ext import commands
import requests

# randomstring 모듈 대신 파이썬 내장 모듈 사용 (안정성 향상)
import string
import random

from setting import (
    DATABASE_PATH, DISCORD_BOT_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    api_endpoint, owner,
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# 슬래시 명령어 위주로 사용할 것이므로 prefix는 안 쓰이는 문자로 설정
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 공통 데이터베이스 및 유틸리티 함수 ---
def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur

def init_db():
    con, cur = start_db()
    # 테이블 생성 (새로 추가된 컬럼 포함: role_id, log_webhook)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER, token TEXT, expiredate TEXT, link TEXT,
            role_id INTEGER DEFAULT 0, log_webhook TEXT DEFAULT ''
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS licenses (key TEXT, day INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER, token TEXT, guild_id INTEGER)")
    
    # 인덱스 생성
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_id ON guilds(id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_guild ON users(id, guild_id)")
    
    # 만약 기존 guilds 테이블에 새 컬럼이 없다면 추가 (에러 무시)
    try: cur.execute("ALTER TABLE guilds ADD COLUMN role_id INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try: cur.execute("ALTER TABLE guilds ADD COLUMN log_webhook TEXT DEFAULT ''")
    except sqlite3.OperationalError: pass

    con.commit()
    con.close()

def bot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

def embeda(embedtype, embedtitle, description):
    color = 0x5C6CDF if embedtype == "success" else 0xFF0000
    return discord.Embed(color=color, title=embedtitle, description=description)

# 시간 관련 함수
def get_expiretime(time):
    server_time = datetime.datetime.now()
    expire_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
    if (expire_time - server_time).total_seconds() <= 0: return False
    how_long = expire_time - server_time
    days = how_long.days
    hours = how_long.seconds // 3600
    minutes = (how_long.seconds // 60) - (hours * 60)
    return f"{round(days)}일 {round(hours)}시간 {round(minutes)}분"

def make_expiretime(days):
    server_time = datetime.datetime.now()
    return (server_time + timedelta(days=days)).strftime("%Y-%m-%d %H:%M")

def add_time(now_days, add_days):
    expire_time = datetime.datetime.strptime(now_days, "%Y-%m-%d %H:%M")
    return (expire_time + timedelta(days=add_days)).strftime("%Y-%m-%d %H:%M")

def is_expired(time):
    server_time = datetime.datetime.now()
    expire_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
    return (expire_time - server_time).total_seconds() <= 0

# 디스코드 API 관련 함수
async def request_with_rate_limit(method, url, **kwargs):
    while True:
        response = await asyncio.to_thread(method, url, **kwargs)
        if response.status_code != 429: return response
        try: retry_after = response.json().get("retry_after", 1)
        except ValueError: retry_after = 1
        await asyncio.sleep(float(retry_after) + 2)

async def refresh_token(refresh_token_value):
    data = {
        "client_id": DISCORD_CLIENT_ID, "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "refresh_token", "refresh_token": refresh_token_value,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = await request_with_rate_limit(requests.post, f"{api_endpoint}/oauth2/token", data=data, headers=headers, timeout=15)
    try: result = response.json()
    except ValueError: return False
    return False if "error" in result else result

async def add_user(access_token, guild_id, user_id):
    response = await request_with_rate_limit(
        requests.put, f"{api_endpoint}/guilds/{guild_id}/members/{user_id}",
        json={"access_token": access_token}, headers=bot_headers(), timeout=15
    )
    return response.status_code in (201, 204)

async def is_guild(guild_id):
    con, cur = start_db()
    cur.execute("SELECT * FROM guilds WHERE id == ?;", (guild_id,))
    res = cur.fetchone()
    con.close()
    return res is not None

async def is_guild_valid(guild_id):
    if not await is_guild(guild_id): return False
    con, cur = start_db()
    cur.execute("SELECT * FROM guilds WHERE id == ?;", (guild_id,))
    guild_info = cur.fetchone()
    con.close()
    return guild_info is not None and not is_expired(guild_info[2])

def normalize_link(link):
    link = link.strip().strip("/")
    if not link or len(link) > 64: return None
    if not all(ch.isalnum() or ch in ("-", "_") for ch in link): return None
    return link

def generate_random_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(letters_and_digits) for i in range(length))

# --- 봇 이벤트 ---
@bot.event
async def on_ready():
    init_db()
    print(f"Login: {bot.user}")
    
    # 모듈 로드 (Cogs)
    await bot.load_extension("admin")
    await bot.load_extension("user")
    
    # 슬래시 명령어 서버 동기화
    await bot.tree.sync()
    print("슬래시 명령어 동기화 완료")
    
    while True:
        await bot.change_presence(
            activity=discord.Game(f"링크복구봇 | {len(bot.guilds)}서버 사용중"),
            status=discord.Status.online,
        )
        await asyncio.sleep(10)

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)