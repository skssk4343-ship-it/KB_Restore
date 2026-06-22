import discord
from discord import app_commands
from discord.ext import commands
import uuid
from main import (
    start_db, embeda, is_guild_valid, get_expiretime, 
    make_expiretime, add_time, is_expired, DISCORD_CLIENT_ID
)

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="등록", description="복구봇 라이센스 코드를 사용해 이 서버의 이용 기간을 등록하거나 연장합니다.")
    async def register(self, interaction: discord.Interaction, 라이센스_코드: str, 원하는링크: str):
        if interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(embed=embeda("error", "권한 부족", "서버 소유자(서버장)만 라이센스 등록이 가능합니다."), ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT day FROM licenses WHERE key == ?;", (라이센스_코드,))
        key_info = cur.fetchone()
        
        if not key_info:
            con.close()
            return await interaction.response.send_message(embed=embeda("error", "검증 실패", "유효하지 않거나 이미 사용 처리된 라이센스 코드입니다."), ephemeral=True)

        cur.execute("DELETE FROM licenses WHERE key == ?;", (라이센스_코드,))
        con.commit()
        key_length = key_info[0]

        cur.execute("SELECT expiredate FROM guilds WHERE id == ?;", (interaction.guild_id,))
        guild_info = cur.fetchone()

        # 기간 연장인 경우
        if guild_info:
            expire_date = guild_info[0]
            new_expiredate = make_expiretime(key_length) if is_expired(expire_date) else add_time(expire_date, key_length)
            cur.execute("UPDATE guilds SET expiredate = ? WHERE id == ?;", (new_expiredate, interaction.guild_id))
            con.commit()
            con.close()
            return await interaction.response.send_message(embed=embeda("success", "기간 연장 성공", f"라이센스가 성공적으로 연장되었습니다.\n📅 새로운 만료일: {new_expiredate}"), ephemeral=True)

        # 신규 등록인 경우
        new_expiredate = make_expiretime(key_length)
        recover_key = str(uuid.uuid4())[:8].upper() # 해당 서버만의 고유 자체 복구키 생성
        
        cur.execute("INSERT INTO guilds (id, token, expiredate, link) VALUES(?, ?, ?, ?);", 
                    (interaction.guild_id, recover_key, new_expiredate, 원하는링크))
        con.commit()
        con.close()

        await interaction.response.send_message(embed=embeda("success", "서버 등록 성공", f"정상적으로 등록되었습니다.\n📅 만료 일시: {new_expiredate}\n🔗 연동 도메인 주소: /{원하는링크}\n🔑 서버 고유 자체 백업키: `{recover_key}`"), ephemeral=True)

    @app_commands.command(name="정보", description="현재 이 서버에 연동된 라이센스 상세 정보 및 인증인원을 확인합니다.")
    async def info(self, interaction: discord.Interaction):
        if not await is_guild_valid(interaction.guild_id):
            return await interaction.response.send_message(embed=embeda("error", "만료됨", "이 서버는 라이센스가 만료되었거나 등록되지 않은 상태입니다."), ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT expiredate, link FROM guilds WHERE id == ?;", (interaction.guild_id,))
        guild_info = cur.fetchone()
        cur.execute("SELECT DISTINCT id FROM users WHERE guild_id == ?;", (interaction.guild_id,))
        users = cur.fetchall()
        con.close()

        await interaction.response.send_message(embed=embeda("success", "라이센스 서버 정보", f"⏳ 남은 구독 기간: {get_expiretime(guild_info[0])}\n👥 현재 인증 완료된 유저 수: {len(users)}명\n🌐 연결된 웹 링크 커스텀 경로: /{guild_info[1]}"))

    @app_commands.command(name="인증", description="유저들이 디스코드 계정을 연동할 수 있는 인증 임베드 패널을 생성합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def auth_embed(self, interaction: discord.Interaction):
        auth_url = f"https://kb-restore.o-r.kr/join?state={interaction.guild_id}"
        embed = discord.Embed(title="✅ 서버 유저 인증 시스템", description="서버의 모든 기능을 안전하게 이용하시려면 아래 버튼을 눌러 본인 인증을 진행해 주세요.", color=0x5C6CDF)
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="인증하기", url=auth_url, style=discord.ButtonStyle.link))
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("정상적으로 인증 임베드 패널을 전송했습니다.", ephemeral=True)

    @app_commands.command(name="역할", description="유저가 웹 페이지에서 인증을 성공적으로 마치면 자동으로 자동 지급할 역할을 지정합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_role(self, interaction: discord.Interaction, 역할: discord.Role):
        con, cur = start_db()
        cur.execute("UPDATE guilds SET role_id = ? WHERE id = ?;", (역할.id, interaction.guild_id))
        con.commit()
        con.close()
        await interaction.response.send_message(embed=embeda("success", "역할 연동 완료", f"이제 인증이 완료된 유저에게 {역할.mention} 역할이 자동 부여됩니다."), ephemeral=True)

    @app_commands.command(name="로그웹훅", description="인증이 성공될 때마다 실시간 로그 알림을 받아볼 디스코드 웹훅 주소를 설정합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_webhook(self, interaction: discord.Interaction, 웹훅주소: str):
        con, cur = start_db()
        cur.execute("UPDATE guilds SET log_webhook = ? WHERE id = ?;", (웹훅주소, interaction.guild_id))
        con.commit()
        con.close()
        await interaction.response.send_message(embed=embeda("success", "웹훅 설정 완료", "인증 로그 감지용 웹훅 채널이 성공적으로 연동되었습니다."), ephemeral=True)

    @app_commands.command(name="웹훅보기", description="현재 서버에 저장된 인증 로그용 웹훅 주소를 확인합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_webhook(self, interaction: discord.Interaction):
        con, cur = start_db()
        cur.execute("SELECT log_webhook FROM guilds WHERE id = ?;", (interaction.guild_id,))
        result = cur.fetchone()
        con.close()
        
        webhook = result[0] if result and result[0] else "설정된 웹훅 주소가 존재하지 않습니다."
        await interaction.response.send_message(f"**현재 설정된 알림 로그 웹훅:**\n`{webhook}`", ephemeral=True)

    @app_commands.command(name="복구키사용", description="[수동 방식] 구매하신 1회성 인원수 차등 복구키를 수동으로 입력하여 사용합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def use_recovery_key(self, interaction: discord.Interaction, 복구키: str):
        from main import KeyModal
        modal = KeyModal()
        modal.key_input.default = 복구키
        await interaction.response.send_modal(modal)

    @app_commands.command(name="복구", description="서버장 고유의 자체 백업키를 활용하여 기존 원본 데이터를 복구합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def restore_server(self, interaction: discord.Interaction, 서버토큰: str):
        await interaction.response.send_message("자체 서버 백업 복구 세션이 백그라운드에서 구동됩니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(UserCommands(bot))