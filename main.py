import asyncio
import datetime
import sqlite3
import uuid
from datetime import timedelta

import discord
import requests

import randomstring
from setting import (
    DATABASE_PATH,
    DISCORD_BOT_TOKEN,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    api_endpoint,
    owner,
)


intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)


def start_db():
    con = sqlite3.connect(DATABASE_PATH)
    cur = con.cursor()
    return con, cur


def init_db():
    con, cur = start_db()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER,
            token TEXT,
            expiredate TEXT,
            link TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT,
            day INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER,
            token TEXT,
            guild_id INTEGER
        )
        """
    )
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_licenses_key ON licenses(key)")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_id ON guilds(id)")
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_guilds_link
        ON guilds(link)
        WHERE link IS NOT NULL AND link != ''
        """
    )
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_guild ON users(id, guild_id)")
    con.commit()
    con.close()


def bot_headers():
    return {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}


def get_expiretime(time):
    server_time = datetime.datetime.now()
    expire_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
    if (expire_time - server_time).total_seconds() <= 0:
        return False

    how_long = expire_time - server_time
    days = how_long.days
    hours = how_long.seconds // 3600
    minutes = how_long.seconds // 60 - hours * 60
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


def embeda(embedtype, embedtitle, description):
    color = 0x5C6CDF
    return discord.Embed(color=color, title=embedtitle, description=description)


async def request_with_rate_limit(method, url, **kwargs):
    while True:
        response = await asyncio.to_thread(method, url, **kwargs)
        if response.status_code != 429:
            return response

        try:
            retry_after = response.json().get("retry_after", 1)
        except ValueError:
            retry_after = 1
        await asyncio.sleep(float(retry_after) + 2)


async def refresh_token(refresh_token_value):
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = await request_with_rate_limit(
        requests.post,
        f"{api_endpoint}/oauth2/token",
        data=data,
        headers=headers,
        timeout=15,
    )

    try:
        result = response.json()
    except ValueError:
        return False

    return False if "error" in result else result


async def add_user(access_token, guild_id, user_id):
    response = await request_with_rate_limit(
        requests.put,
        f"{api_endpoint}/guilds/{guild_id}/members/{user_id}",
        json={"access_token": access_token},
        headers=bot_headers(),
        timeout=15,
    )
    return response.status_code in (201, 204)


async def getguild(guild_id):
    response = await asyncio.to_thread(
        requests.get,
        f"{api_endpoint}/guilds/{guild_id}",
        headers=bot_headers(),
        timeout=15,
    )
    try:
        return response.json()
    except ValueError:
        return {}


async def is_guild(guild_id):
    con, cur = start_db()
    cur.execute("SELECT * FROM guilds WHERE id == ?;", (guild_id,))
    res = cur.fetchone()
    con.close()
    return res is not None


async def is_guild_valid(guild_id):
    if not str(guild_id).isdigit():
        return False
    if not await is_guild(guild_id):
        return False

    con, cur = start_db()
    cur.execute("SELECT * FROM guilds WHERE id == ?;", (guild_id,))
    guild_info = cur.fetchone()
    con.close()
    return guild_info is not None and not is_expired(guild_info[2])


def is_owner(message):
    return owner and message.author.id == owner


def can_manage_server(message):
    if message.guild is None:
        return False
    return message.author.id == message.guild.owner_id or is_owner(message)


async def ask_dm(message, prompt, timeout=60):
    def check(reply):
        return isinstance(reply.channel, discord.channel.DMChannel) and reply.author.id == message.author.id

    await message.author.send(embed=discord.Embed(title="SinLinkBackup", description=prompt, color=0x5C6CDF))
    await message.channel.send(embed=embeda("success", "SinLinkBackup", "DM을 확인해 주세요."))
    return await client.wait_for("message", timeout=timeout, check=check)


def normalize_link(link):
    link = link.strip().strip("/")
    if not link or len(link) > 64:
        return None
    if not all(ch.isalnum() or ch in ("-", "_") for ch in link):
        return None
    return link


@client.event
async def on_ready():
    init_db()
    invite = (
        "https://discord.com/oauth2/authorize"
        f"?client_id={client.user.id}&permissions=0&scope=bot"
    )
    print(f"Login: {client.user}\nInvite Link: {invite}")
    while True:
        await client.change_presence(
            activity=discord.Game(f"링크복구봇 | {len(client.guilds)}서버 사용중"),
            status=discord.Status.online,
        )
        await asyncio.sleep(10)


@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.startswith(".생성"):
        if not is_owner(message):
            await message.channel.send(embed=embeda("error", "생성 실패", "봇 소유자만 사용할 수 있습니다."))
            return

        parts = message.content.split()
        if len(parts) != 3:
            await message.channel.send("사용법: .생성 (갯수) (일수)")
            return

        try:
            amount = int(parts[1])
            license_length = int(parts[2])
        except ValueError:
            await message.channel.send("갯수와 기간은 숫자로 입력해주세요.")
            return

        if not 1 <= amount <= 30:
            await message.channel.send("라이센스는 한 번에 1개부터 30개까지만 생성할 수 있습니다.")
            return
        if license_length <= 0:
            await message.channel.send("기간은 1일 이상이어야 합니다.")
            return

        con, cur = start_db()
        generated_key = []
        for _ in range(amount):
            key = "SinRestore-" + randomstring.pick(20)
            generated_key.append(key)
            cur.execute("INSERT INTO licenses VALUES(?, ?);", (key, license_length))
        con.commit()
        con.close()

        await message.channel.send(embed=embeda("success", "생성 성공", "DM을 확인해주세요."))
        await message.author.send("\n".join(generated_key))
        return

    if message.content == ".명령어":
        embed = discord.Embed(
            title="SinLinkBackup",
            description=(
                ".생성 (갯수) (몇일) : 라이센스를 생성합니다.\n"
                ".링크 : URL을 수정합니다.\n"
                ".등록 (코드) : 라이센스를 등록합니다.\n"
                ".정보 : 라이센스 기간, 인증 유저 수, 서버초대URL을 표시합니다.\n"
                ".복구 (복구키) : 유저 복구를 진행합니다."
            ),
            color=0x5C6CDF,
        )
        await message.channel.send(embed=embed)
        return

    if message.content == ".초대":
        embed = discord.Embed(
            title="SinLinkBackup봇 초대",
            description=(
                "[봇을 초대하려면 여기 클릭!]"
                f"(https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions=0&scope=bot)"
            ),
            color=0x5C6CDF,
        )
        await message.channel.send(embed=embed)
        return

    if message.guild is None:
        return

    if message.content.startswith(".등록 "):
        if not can_manage_server(message):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "서버 소유자만 등록할 수 있습니다."))
            return

        parts = message.content.split()
        if len(parts) != 2:
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "사용법: .등록 (라이센스코드)"))
            return

        license_number = parts[1]
        con, cur = start_db()
        cur.execute("SELECT * FROM licenses WHERE key == ?;", (license_number,))
        key_info = cur.fetchone()
        if key_info is None:
            con.close()
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "라이센스가 존재하지 않습니다."))
            return

        cur.execute("DELETE FROM licenses WHERE key == ?;", (license_number,))
        con.commit()
        con.close()
        key_length = key_info[1]

        if await is_guild(message.guild.id):
            con, cur = start_db()
            cur.execute("SELECT * FROM guilds WHERE id == ?;", (message.guild.id,))
            guild_info = cur.fetchone()
            expire_date = guild_info[2]
            new_expiredate = make_expiretime(key_length) if is_expired(expire_date) else add_time(expire_date, key_length)
            cur.execute("UPDATE guilds SET expiredate = ? WHERE id == ?;", (new_expiredate, message.guild.id))
            con.commit()
            con.close()
            await message.channel.send(embed=embeda("success", "SinLinkBackup", "기간이 연장되었습니다.\n다음 만료일 : " + new_expiredate))
            return

        try:
            new_expiredate = make_expiretime(key_length)
            recover_key = str(uuid.uuid4())[:8].upper()
            con, cur = start_db()
            cur.execute("INSERT INTO guilds VALUES(?, ?, ?, ?);", (message.guild.id, recover_key, new_expiredate, ""))
            con.commit()
            con.close()

            reply = await ask_dm(message, "URL을 입력해주세요. ( /URL < 이부분 )")
            link = normalize_link(reply.content)
            if link is None:
                await message.author.send(embed=embeda("error", "SinLinkBackup", "URL은 영문/숫자/-/_ 조합으로 64자 이하만 가능합니다."))
                return

            con, cur = start_db()
            cur.execute("SELECT * FROM guilds WHERE link == ?;", (link,))
            find = cur.fetchone()
            if find:
                con.close()
                await message.author.send(embed=embeda("error", "SinLinkBackup", "이미 사용중인 링크입니다. .링크 명령어로 다시 등록해 주세요."))
                return

            cur.execute("UPDATE guilds SET link = ? WHERE id == ?;", (link, message.guild.id))
            con.commit()
            con.close()

            await message.channel.send(
                embed=embeda(
                    "success",
                    "SinLinkBackup",
                    "라이센스가 성공적으로 등록되었습니다.\n"
                    f"만료일 : {new_expiredate}\n서버링크 : /{link}\nDM으로 복구키가 전송되었습니다.",
                )
            )
            await message.author.send(
                embed=embeda(
                    "success",
                    "SinLinkBackup",
                    f"복구 키 : `{recover_key}`\n복구키를 잃어버리지 않도록 잘 보관해주세요.",
                )
            )
        except Exception as exc:
            print(f"registration failed: {type(exc).__name__}")
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "DM이 차단되었거나 권한이 부족합니다."))
        return

    if message.content == ".링크":
        if not message.author.guild_permissions.administrator:
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "당신은 서버에 관리자 권한이 없습니다."))
            return
        if not await is_guild(message.guild.id):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "라이센스가 등록되어 있지 않습니다."))
            return

        try:
            reply = await ask_dm(message, "URL을 입력해주세요. ( /URL < 이부분 )")
            link = normalize_link(reply.content)
            if link is None:
                await message.author.send(embed=embeda("error", "SinLinkBackup", "URL은 영문/숫자/-/_ 조합으로 64자 이하만 가능합니다."))
                return

            con, cur = start_db()
            cur.execute("SELECT * FROM guilds WHERE link == ? AND id != ?;", (link, message.guild.id))
            exists = cur.fetchone()
            if exists:
                con.close()
                await message.author.send(embed=embeda("error", "SinLinkBackup", "이미 사용중인 링크입니다. 다시 등록해 주세요."))
                return

            cur.execute("UPDATE guilds SET link = ? WHERE id == ?;", (link, message.guild.id))
            con.commit()
            con.close()
            await message.author.send(embed=embeda("success", "SinLinkBackup", f"/{link}"))
        except Exception as exc:
            print(f"link update failed: {type(exc).__name__}")
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "DM이 차단되었거나 권한이 부족합니다."))
        return

    if message.content == ".정보":
        if not await is_guild_valid(message.guild.id):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "라이센스가 유효하지 않습니다."))
            return

        con, cur = start_db()
        cur.execute("SELECT * FROM guilds WHERE id == ?;", (message.guild.id,))
        guild_info = cur.fetchone()
        cur.execute("SELECT DISTINCT id FROM users WHERE guild_id == ?;", (message.guild.id,))
        users = cur.fetchall()
        con.close()

        await message.channel.send(
            embed=embeda(
                "success",
                "SinLinkBackup",
                f"{get_expiretime(guild_info[2])} ( {guild_info[2]} ) 남음\n"
                f"인증 유저 수 : {len(users)}\n서버 링크 : /{guild_info[3]}",
            )
        )
        return

    if message.content.startswith(".복구 "):
        if not is_owner(message):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "봇 소유자만 복구할 수 있습니다."))
            return
        if await is_guild_valid(message.guild.id):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "라이센스를 등록하기 전에 복구를 진행해주세요."))
            return

        parts = message.content.split()
        if len(parts) != 2:
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "사용법: .복구 (복구키)"))
            return

        recover_key = parts[1]
        con, cur = start_db()
        cur.execute("SELECT * FROM guilds WHERE token == ?;", (recover_key,))
        token_result = cur.fetchone()
        con.close()

        if token_result is None:
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "복구 키가 틀렸습니다."))
            return
        if not await is_guild_valid(token_result[0]):
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "복구 키가 만료되었습니다."))
            return
        if not (await message.guild.fetch_member(client.user.id)).guild_permissions.administrator:
            await message.channel.send(embed=embeda("error", "SinLinkBackup", "봇에게 관리자 권한이 필요합니다."))
            return

        con, cur = start_db()
        cur.execute("SELECT DISTINCT id, token FROM users WHERE guild_id == ?;", (token_result[0],))
        users = cur.fetchall()
        con.close()

        await message.channel.send(embed=embeda("success", "SinLinkBackup", f"복구 중입니다. 잠시만 기다려주세요.(예상복구인원 : {len(users)})"))

        restored = 0
        for user_id, refresh_token_value in users:
            try:
                new_token = await refresh_token(refresh_token_value)
                if not new_token:
                    continue

                added = await add_user(new_token["access_token"], message.guild.id, user_id)
                if added:
                    restored += 1

                con, cur = start_db()
                cur.execute("UPDATE users SET token = ? WHERE token == ?;", (new_token["refresh_token"], refresh_token_value))
                con.commit()
                con.close()
            except Exception as exc:
                print(f"restore skipped user {user_id}: {type(exc).__name__}")

        con, cur = start_db()
        cur.execute("UPDATE users SET guild_id = ? WHERE guild_id == ?;", (message.guild.id, token_result[0]))
        cur.execute("UPDATE guilds SET id = ? WHERE id == ?;", (message.guild.id, token_result[0]))
        con.commit()
        con.close()

        await message.channel.send(embed=embeda("success", "SinLinkBackup", f"복구가 완료되었습니다. 성공: {restored}/{len(users)}"))


client.run(DISCORD_BOT_TOKEN)
