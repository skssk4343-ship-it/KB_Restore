import discord
from discord.ext import commands
import sqlite3, requests, asyncio
from setting import DISCORD_BOT_TOKEN, DATABASE_PATH, api_endpoint, owner

# 봇 설정
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# 접두사를 '.'으로 설정
bot = commands.Bot(command_prefix=".", intents=intents)

# --- 공통 함수 (다른 파일에서 import 하여 사용) ---
def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur

def embeda(embedtype, embedtitle, description):
    return discord.Embed(color=0x5C6CDF, title=embedtitle, description=description)

# ... (기타 refresh_token, add_user, getguild, is_guild_valid 등 기존 함수들 그대로 유지) ...

@bot.event
async def on_ready():
    print(f"로그인 완료: {bot.user}")
    # Cog 로드
    await bot.load_extension("admin")
    await bot.load_extension("user")
    
    while True:
        await bot.change_presence(activity=discord.Game(f"링크복구봇 | {len(bot.guilds)}서버 사용중"))
        await asyncio.sleep(10)

bot.run(DISCORD_BOT_TOKEN)