import asyncio
import datetime
import sqlite3
import uuid
from datetime import timedelta
import discord
from discord.ext import commands
import requests
import string
import random
import os

# setting.py에서 설정값 로드
from setting import (
    DATABASE_PATH, DISCORD_BOT_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    api_endpoint, owner
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# --- 데이터베이스 연결 함수 ---
def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur

# --- 데이터베이스 테이블 및 인덱스 초기화 ---
def init_db():
    con, cur = start_db()
    # guilds: 서버 라이센스(기간제 구독) 정보
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER, token TEXT, expiredate TEXT, link TEXT,
            role_id INTEGER DEFAULT 0, log_webhook TEXT DEFAULT ''
        )
    """)
    # licenses: 생성된 서버 구독용 라이센스 코드 키
    cur.execute("CREATE TABLE IF NOT EXISTS licenses (key TEXT, day INTEGER)")
    # users: 웹 인증을 통해 수집된 유저들의 리프레시 토큰 정보
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER, token TEXT, guild_id INTEGER)")
    
    # sold_keys: [추가됨] 판매용 일회성 복구키 (키, DB를 가져올 원본서버 ID, 최대 복구 인원 제한)
    cur.execute("CREATE TABLE IF NOT EXISTS sold_keys (key TEXT, source_guild INTEGER, max_users INTEGER)")
    
    # 고유 인덱스 설정 (중복 방지)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_id ON guilds(id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_guild ON users(id, guild_id)")
    
    # 이전 DB 버전을 고려한 예외 컬럼 추가 처리
    try: cur.execute("ALTER TABLE sold_keys ADD COLUMN max_users INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE guilds ADD COLUMN role_id INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE guilds ADD COLUMN log_webhook TEXT DEFAULT ''")
    except: pass

    con.commit()
    con.close()

# --- 유틸리티 기능 함수 ---
def bot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}

def embeda(embedtype, embedtitle, description):
    color = 0x5C6CDF if embedtype == "success" else 0xFF0000
    return discord.Embed(color=color, title=embedtitle, description=description)

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

async def request_with_rate_limit(method, url, **kwargs):
    while True:
        response = await asyncio.to_thread(method, url, **kwargs)
        if response.status_code != 429: return response
        try: retry_after = response.json().get("retry_after", 1)
        except ValueError: retry_after = 1
        await asyncio.sleep(float(retry_after) + 2)

async def refresh_token_func(refresh_token_value):
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

async def is_guild_valid(guild_id):
    con, cur = start_db()
    cur.execute("SELECT * FROM guilds WHERE id == ?;", (guild_id,))
    guild_info = cur.fetchone()
    con.close()
    return guild_info is not None and not is_expired(guild_info[2])

def generate_random_string(length):
    letters_and_digits = string.ascii_letters + string.digits
    return ''.join(random.choice(letters_and_digits) for i in range(length))


# --- [UI 기능] 복구키 입력 모달창 대화상자 ---
class KeyModal(discord.ui.Modal, title='복구키 라이센스 사용'):
    key_input = discord.ui.TextInput(
        label='발급받은 복구키를 입력해주세요.',
        placeholder='예: Key-ABCD1234EFGH5678',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        input_key = self.key_input.value.strip()
        con, cur = start_db()
        
        # 입력한 복구키가 유효한지 확인하고, 연동된 백업 서버ID와 차등 지급할 인원 제한 수치를 가져옴
        cur.execute("SELECT source_guild, max_users FROM sold_keys WHERE key == ?;", (input_key,))
        result = cur.fetchone()
        
        if not result:
            con.close()
            return await interaction.response.send_message(embed=embeda("error", "오류", "존재하지 않거나 이미 사용된 복구키입니다."), ephemeral=True)
            
        source_guild_id = result[0]
        max_users = result[1]
        
        # 一회용 키이므로 검증 성공 즉시 DB에서 폐기(삭제) 처리
        cur.execute("DELETE FROM sold_keys WHERE key == ?;", (input_key,))
        con.commit()
        
        # 해당 백업서버의 유저 데이터를 지정된 인원수(LIMIT max_users)만큼 가져옴
        cur.execute("SELECT DISTINCT id, token FROM users WHERE guild_id == ? LIMIT ?;", (source_guild_id, max_users))
        users = cur.fetchall()
        con.close()

        await interaction.response.send_message(
            embed=embeda("success", "복구 작업 시작", f"복구키 인증에 성공했습니다!\n선택하신 상품 제한에 따라 **최대 {max_users}명** 초대를 시작합니다.\n(현재 대기 인원: {len(users)}명)"), 
            ephemeral=True
        )

        restored = 0
        for user_id, refresh_token_value in users:
            try:
                new_token = await refresh_token_func(refresh_token_value)
                if not new_token: continue

                # 버튼을 클릭한 현재 서버(interaction.guild_id)로 강제 초대 시도
                added = await add_user(new_token["access_token"], interaction.guild_id, user_id)
                if added: restored += 1

                # 리프레시 토큰 최신화 작업 및 현재 서버 명단에 추가 기록
                con, cur = start_db()
                cur.execute("UPDATE users SET token = ? WHERE token == ?;", (new_token["refresh_token"], refresh_token_value))
                cur.execute("INSERT OR IGNORE INTO users (id, token, guild_id) VALUES (?, ?, ?);", (user_id, new_token["refresh_token"], interaction.guild_id))
                con.commit()
                con.close()
            except: pass

        # 채널에 최종 완료 알림 전송
        await interaction.channel.send(embed=embeda("success", "유저 복구 완료", f"<@{interaction.user.id}>님이 요청하신 데이터 복구가 완료되었습니다.\n\n▶ 성공 인원: **{restored}명**\n▶ 상품 최대 제한: **{max_users}명**"))


# --- [UI 기능] 복구 자동화 임베드용 버튼 뷰 ---
class RecoveryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 봇이 꺼져도 꺼지지 않는 상시 지속 설정

    @discord.ui.button(label='복구봇 사용하기', style=discord.ButtonStyle.secondary, custom_id='persistent_recovery_button')
    async def use_key_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 버튼 클릭 시 복구키 입력 모달을 띄워줌
        await interaction.response.send_modal(KeyModal())


# --- [UI 기능] 실시간 인원 확인 임베드용 새로고침 버튼 뷰 ---
class RefreshView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # 상시 지속 설정

    @discord.ui.button(label='인원 새로고침', style=discord.ButtonStyle.secondary, custom_id='persistent_refresh_button')
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        con, cur = start_db()
        cur.execute("SELECT DISTINCT id FROM users WHERE guild_id == ?;", (interaction.guild_id,))
        users = cur.fetchall()
        con.close()

        now = datetime.datetime.now().strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
        
        embed = discord.Embed(title="인원 새로고침", description="인원 새로고침을 하려면 아래 버튼을 눌러주세요.", color=0x2b2d31)
        embed.add_field(name="", value=f"```\n예상복구인원 {len(users)} 명 입니다.\n```", inline=False)
        embed.set_footer(text=f"기준 시각: {now}")

        # 기존 메시지를 실시간 인원 정보로 업데이트 편집
        await interaction.response.edit_message(embed=embed, view=self)


# --- 메인 봇 시스템 정의 ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_db()
        # 중요: 상시 작동형 뷰(버튼)를 봇 내부에 영구 등록
        self.add_view(RecoveryView())
        self.add_view(RefreshView())
        
        # 명령어 파일(Cogs) 로드
        await self.load_extension("admin")
        await self.load_extension("user")
        await self.tree.sync()
        print("[시스템] 슬래시 명령어 동기화 및 버튼 컨트롤러 활성화 완료.")

bot = MyBot()

@bot.event
async def on_ready():
    print(f"[로그인 완료] 구동 중인 계정: {bot.user}")
    while True:
        await bot.change_presence(activity=discord.Game(f"링크복구봇 | {len(bot.guilds)}개 서버 관리 중"), status=discord.Status.online)
        await asyncio.sleep(10)

# 요구사항: [!인원메시지생성] 일반 접두사 관리자 명령어
@bot.command(name="인원메시지생성")
@commands.has_permissions(administrator=True)
async def create_refresh_msg(ctx):
    con, cur = start_db()
    cur.execute("SELECT DISTINCT id FROM users WHERE guild_id == ?;", (ctx.guild.id,))
    users = cur.fetchall()
    con.close()

    now = datetime.datetime.now().strftime("%Y년 %m월 %d일 %p %I:%M").replace("AM", "오전").replace("PM", "오후")
    
    embed = discord.Embed(title="인원 새로고침", description="인원 새로고침을 하려면 아래 버튼을 눌러주세요.", color=0x2b2d31)
    embed.add_field(name="", value=f"```\n예상복구인원 {len(users)} 명 입니다.\n```", inline=False)
    embed.set_footer(text=f"기준 시각: {now}")

    await ctx.send(embed=embed, view=RefreshView())

if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)