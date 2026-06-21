import discord
from discord import app_commands
from discord.ext import commands
from main import (
    start_db, embeda, is_guild, is_guild_valid, get_expiretime, 
    make_expiretime, add_time, is_expired, normalize_link, DISCORD_CLIENT_ID
)
import uuid

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="등록", description="[서버 소유자] 라이센스를 등록합니다.")
    async def register(self, interaction: discord.Interaction, 라이센스_코드: str, 원하는링크: str):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(embed=embeda("error", "권한 부족", "서버 소유자만 등록할 수 있습니다."), ephemeral=True)

        link = normalize_link(원하는링크)
        if link is None:
            return await interaction.response.send_message(embed=embeda("error", "오류", "URL은 영문/숫자/-/_ 조합 64자 이하만 가능합니다."), ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT * FROM licenses WHERE key == ?;", (라이센스_코드,))
        key_info = cur.fetchone()
        
        if key_info is None:
            con.close()
            return await interaction.response.send_message(embed=embeda("error", "오류", "존재하지 않거나 이미 사용된 라이센스입니다."), ephemeral=True)

        cur.execute("DELETE FROM licenses WHERE key == ?;", (라이센스_코드,))
        con.commit()
        key_length = key_info[1]

        # 이미 등록된 서버 연장 처리
        if await is_guild(interaction.guild_id):
            cur.execute("SELECT * FROM guilds WHERE id == ?;", (interaction.guild_id,))
            guild_info = cur.fetchone()
            expire_date = guild_info[2]
            new_expiredate = make_expiretime(key_length) if is_expired(expire_date) else add_time(expire_date, key_length)
            
            cur.execute("UPDATE guilds SET expiredate = ? WHERE id == ?;", (new_expiredate, interaction.guild_id))
            con.commit()
            con.close()
            return await interaction.response.send_message(embed=embeda("success", "연장 성공", f"기간이 연장되었습니다.\n다음 만료일 : {new_expiredate}"), ephemeral=True)

        # 새 서버 등록
        try:
            # 다른 서버가 링크를 쓰고 있는지 확인
            cur.execute("SELECT * FROM guilds WHERE link == ?;", (link,))
            if cur.fetchone():
                con.close()
                return await interaction.response.send_message(embed=embeda("error", "오류", "이미 사용중인 링크 주소입니다."), ephemeral=True)

            new_expiredate = make_expiretime(key_length)
            recover_key = str(uuid.uuid4())[:8].upper()
            
            cur.execute("INSERT INTO guilds (id, token, expiredate, link) VALUES(?, ?, ?, ?);", 
                        (interaction.guild_id, recover_key, new_expiredate, link))
            con.commit()
            con.close()

            # 보안을 위해 나만 보기(ephemeral)로 복구키 전송 (DM보다 안전하고 확실함)
            await interaction.response.send_message(
                embed=embeda("success", "등록 성공", f"만료일: {new_expiredate}\n서버링크: /{link}\n\n**[중요] 복구 키:** `{recover_key}`\n이 키를 반드시 안전한 곳에 메모해두세요!"), 
                ephemeral=True
            )
        except Exception as e:
            print(f"등록 에러: {e}")
            await interaction.response.send_message("등록 중 오류가 발생했습니다.", ephemeral=True)

    @app_commands.command(name="정보", description="현재 서버의 라이센스 정보를 확인합니다.")
    async def info(self, interaction: discord.Interaction):
        if not await is_guild_valid(interaction.guild_id):
            return await interaction.response.send_message(embed=embeda("error", "오류", "라이센스가 등록되지 않았거나 만료되었습니다."), ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT * FROM guilds WHERE id == ?;", (interaction.guild_id,))
        guild_info = cur.fetchone()
        cur.execute("SELECT DISTINCT id FROM users WHERE guild_id == ?;", (interaction.guild_id,))
        users = cur.fetchall()
        con.close()

        await interaction.response.send_message(
            embed=embeda("success", "라이센스 정보", f"남은 기간: {get_expiretime(guild_info[2])} ({guild_info[2]})\n인증 유저 수: {len(users)}명\n커스텀 링크: /{guild_info[3]}")
        )

    @app_commands.command(name="인증", description="인증 버튼 임베드를 출력합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def auth_embed(self, interaction: discord.Interaction):
        # 봇의 OAuth 인증 링크 생성 (서버 ID를 state에 포함)
        auth_url = f"https://kb-restore.o-r.kr/join?state={interaction.guild_id}"
        
        embed = discord.Embed(title="✅ 서버 안전 인증", description="서버 입장을 위해 아래 링크를 클릭하여 인증을 완료해 주세요.", color=0x5C6CDF)
        embed.add_field(name="인증하기", value=f"[여기 클릭하여 인증 진행]({auth_url})")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="초대", description="봇 초대 링크를 확인합니다.")
    async def invite(self, interaction: discord.Interaction):
        link = f"https://discord.com/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
        await interaction.response.send_message(embed=embeda("success", "봇 초대", f"[봇을 초대하려면 여기 클릭!]({link})"), ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserCommands(bot))