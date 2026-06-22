import discord
from discord import app_commands
from discord.ext import commands
from main import start_db, embeda, generate_random_string, RecoveryView, owner

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_bot_owner(self, user_id):
        return owner and user_id == owner

    @app_commands.command(name="생성", description="[최고관리자] 일반 복구봇 서버 기간제 구독권을 생성합니다.")
    async def create_license(self, interaction: discord.Interaction, 갯수: int, 일수: int):
        if not self.is_bot_owner(interaction.user.id):
            return await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)

        con, cur = start_db()
        keys = []
        for _ in range(갯수):
            key = "SinRestore-" + generate_random_string(20)
            keys.append(key)
            cur.execute("INSERT INTO licenses (key, day) VALUES (?, ?);", (key, 일수))
        con.commit()
        con.close()
        
        await interaction.response.send_message(f"✅ 일반 라이센스 {갯수}개 생성 완료:\n```\n" + "\n".join(keys) + "\n```", ephemeral=True)

    # --- [수정됨] 대상 서버 ID 없이 생성 ---
    @app_commands.command(name="복구키생성", description="[최고관리자] 인원수 제한 상품 판매를 위한 1회용 복구키를 생성합니다.")
    async def create_recovery_key(self, interaction: discord.Interaction, 인원제한: int, 갯수: int):
        if not self.is_bot_owner(interaction.user.id):
            return await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)

        con, cur = start_db()
        keys = []
        for _ in range(갯수):
            key = "Key-" + generate_random_string(16).upper()
            keys.append(key)
            # 서버 ID 정보 없이 키와 제한 인원수만 저장합니다.
            cur.execute("INSERT INTO sold_keys (key, max_users) VALUES (?, ?);", (key, 인원제한))
        con.commit()
        con.close()

        await interaction.response.send_message(f"✅ 🎯 **[{인원제한}명 제한용]** 판매 키 {갯수}개가 발급되었습니다:\n```\n" + "\n".join(keys) + "\n```", ephemeral=True)

    @app_commands.command(name="서버정리", description="[최고관리자] 기간이 만료된 구독 서버 데이터를 DB에서 일괄 정리합니다.")
    async def clean_servers(self, interaction: discord.Interaction):
        if not self.is_bot_owner(interaction.user.id):
            return await interaction.response.send_message("이 명령어를 사용할 권한이 없습니다.", ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT id, expiredate FROM guilds")
        guilds = cur.fetchall()
        
        deleted = 0
        from main import is_expired
        for gid, expire in guilds:
            if is_expired(expire):
                cur.execute("DELETE FROM guilds WHERE id = ?", (gid,))
                deleted += 1
                
        con.commit()
        con.close()
        await interaction.response.send_message(embed=embeda("success", "서버 정리 완료", f"기간이 만료된 {deleted}개의 서버 데이터를 파기했습니다."), ephemeral=True)

    @app_commands.command(name="자동화", description="[관리자] 복구키 입력 전용 버튼이 달린 자동화 임베드를 출력합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automation_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(title="복구 시스템", description="본인 서버의 데이터를 가져오시려면 아래 버튼을 클릭하여 서버 ID와 복구키를 입력해주세요.", color=0x2b2d31)
        await interaction.channel.send(embed=embed, view=RecoveryView())
        await interaction.response.send_message("✅ 복구 자동화 인터페이스를 생성했습니다.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))