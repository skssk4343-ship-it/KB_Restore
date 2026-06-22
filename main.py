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

from setting import (
    DATABASE_PATH, DISCORD_BOT_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET,
    api_endpoint, owner
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur

def init_db():
    con, cur = start_db()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER, token TEXT, expiredate TEXT, link TEXT,
            role_id INTEGER DEFAULT 0, log_webhook TEXT DEFAULT ''
        )
    """)
    cur.execute("CREATE TABLE IF NOT EXISTS licenses (key TEXT, day INTEGER)")
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER, token TEXT, guild_id INTEGER)")
    
    # 판매용 키 테이블 (키, 최대 인원수만 저장)
    cur.execute("CREATE TABLE IF NOT EXISTS sold_keys (key TEXT, max_users INTEGER)")
    
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_id ON guilds(id)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_guild ON users(id, guild_id)")
    
    try: cur.execute("ALTER TABLE sold_keys ADD COLUMN max_users INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE guilds ADD COLUMN role_id INTEGER DEFAULT 0")
    except: pass
    try: cur.execute("ALTER TABLE guilds ADD COLUMN log_webhook TEXT DEFAULT ''")
    except: pass

    con.commit()
    con.close()

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


# --- [수정됨] 복구키 입력 모달 ---
class KeyModal(discord.ui.Modal, title='복구 데이터 연동'):
    server_id_input = discord.ui.TextInput(
        label='데이터를 가져올 원본 서버 ID',
        placeholder='예: 123456789012345678',
        required=True
    )
    key_input = discord.ui.TextInput(
        label='발급받은 복구키(라이센스)',
        placeholder='예: Key-ABCD1234EFGH',
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        input_server_id = self.server_id_input.value.strip()
        input_key = self.key_input.value.strip()
        
        if not input_server_id.isdigit():
            return await interaction.response.send_message(embed=embeda("error", "입력 오류", "서버 ID는 숫자만 입력해야 합니다."), ephemeral=True)
            
        source_guild_id = int(input_server_id)

        con, cur = start_db()
        # 입력한 키가 유효한지 확인하고 인원 제한 수치를 가져옴
        cur.execute("SELECT max_users FROM sold_keys WHERE key == ?;", (input_key,))
        result = cur.fetchone()
        
        if not result:
            con.close()
            return await interaction.response.send_message(embed=embeda("error", "오류", "존재하지 않거나 이미 사용된 복구키입니다."), ephemeral=True)
            
        max_users = result[0]
        
        # 一회용 키이므로 검증 성공 즉시 DB에서 폐기
        cur.execute("DELETE FROM sold_keys WHERE key == ?;", (input_key,))
        con.commit()
        
        # 구매자가 입력한 서버 ID에서 유저 데이터를 지정된 인원수(LIMIT)만큼 가져옴
        cur.execute("SELECT DISTINCT id, token FROM users WHERE guild_id == ? LIMIT ?;", (source_guild_id, max_users))
        users = cur.fetchall()
        con.close()

        if len(users) == 0:
            return await interaction.response.send_message(embed=embeda("error", "데이터 없음", "해당 서버 ID에 백업된 유저 데이터가 존재하지 않습니다."), ephemeral=True)

        await interaction.response.send_message(
            embed=embeda("success", "복구 작업 시작", f"인증에 성공했습니다!\n원본 서버에서 **최대 {max_users}명** 초대를 시작합니다.\n(실제 대기 인원: {len(users)}명)"), 
            ephemeral=True
        )

        restored = 0
        for user_id, refresh_token_value in users:
            try:
                new_token = await refresh_token_func(refresh_token_value)
                if not new_token: continue

                added = await add_user(new_token["access_token"], interaction.guild_id, user_id)
                if added: restored += 1

                con, cur = start_db()
                cur.execute("UPDATE users SET token = ? WHERE token == ?;", (new_token["refresh_token"], refresh_token_value))
                cur.execute("INSERT OR IGNORE INTO users (id, token, guild_id) VALUES (?, ?, ?);", (user_id, new_token["refresh_token"], interaction.guild_id))
                con.commit()
                con.close()
            except: pass

        await interaction.channel.send(embed=embeda("success", "유저 복구 완료", f"<@{interaction.user.id}>님이 요청하신 데이터 복구가 완료되었습니다.\n\n▶ 성공 인원: **{restored}명**\n▶ 상품 최대 제한: **{max_users}명**"))


class RecoveryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label='복구봇 사용하기', style=discord.ButtonStyle.secondary, custom_id='persistent_recovery_button')
    async def use_key_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(KeyModal())


class RefreshView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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

        await interaction.response.edit_message(embed=embed, view=self)


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        init_db()
        self.add_view(RecoveryView())
        self.add_view(RefreshView())
        
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