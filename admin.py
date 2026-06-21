import discord
from discord import app_commands
from discord.ext import commands
from main import (
    start_db, embeda, refresh_token, add_user, is_guild_valid, 
    generate_random_string, owner
)
import uuid

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_bot_owner(self, user_id):
        return owner and user_id == owner

    @app_commands.command(name="생성", description="[소유자 전용] 라이센스를 생성합니다.")
    async def create_license(self, interaction: discord.Interaction, 갯수: int, 기간_일수: int):
        if not self.is_bot_owner(interaction.user.id):
            return await interaction.response.send_message(embed=embeda("error", "오류", "봇 소유자만 사용할 수 있습니다."), ephemeral=True)
        if not (1 <= 갯수 <= 30):
            return await interaction.response.send_message("라이센스는 1~30개까지만 생성 가능합니다.", ephemeral=True)

        con, cur = start_db()
        keys = []
        for _ in range(갯수):
            key = "SinRestore-" + generate_random_string(20)
            keys.append(key)
            cur.execute("INSERT INTO licenses (key, day) VALUES (?, ?);", (key, 기간_일수))
        con.commit()
        con.close()

        keys_str = "\n".join(keys)
        await interaction.response.send_message(f"✅ 생성 성공! 아래 키를 저장하세요:\n```\n{keys_str}\n```", ephemeral=True)

    @app_commands.command(name="복구", description="[소유자 전용] 유저 복구를 진행합니다.")
    async def restore_users(self, interaction: discord.Interaction, 복구키: str):
        if not self.is_bot_owner(interaction.user.id):
            return await interaction.response.send_message(embed=embeda("error", "오류", "봇 소유자만 사용할 수 있습니다."), ephemeral=True)

        con, cur = start_db()
        cur.execute("SELECT * FROM guilds WHERE token == ?;", (복구키,))
        token_result = cur.fetchone()
        con.close()

        if token_result is None:
            return await interaction.response.send_message(embed=embeda("error", "오류", "복구 키가 틀렸습니다."), ephemeral=True)
        
        await interaction.response.send_message(embed=embeda("success", "복구 시작", "서버 복구 중입니다. 잠시만 기다려주세요."))

        con, cur = start_db()
        cur.execute("SELECT DISTINCT id, token FROM users WHERE guild_id == ?;", (token_result[0],))
        users = cur.fetchall()
        con.close()

        restored = 0
        for user_id, refresh_token_value in users:
            try:
                new_token = await refresh_token(refresh_token_value)
                if not new_token: continue

                added = await add_user(new_token["access_token"], interaction.guild_id, user_id)
                if added: restored += 1

                con, cur = start_db()
                cur.execute("UPDATE users SET token = ? WHERE token == ?;", (new_token["refresh_token"], refresh_token_value))
                con.commit()
                con.close()
            except Exception: pass

        # DB 업데이트 (새로운 서버 ID로 갱신)
        con, cur = start_db()
        cur.execute("UPDATE users SET guild_id = ? WHERE guild_id == ?;", (interaction.guild_id, token_result[0]))
        cur.execute("UPDATE guilds SET id = ? WHERE id == ?;", (interaction.guild_id, token_result[0]))
        con.commit()
        con.close()

        await interaction.channel.send(embed=embeda("success", "복구 완료", f"복구가 완료되었습니다. 성공: {restored}/{len(users)}명"))

    @app_commands.command(name="로그웹훅", description="[관리자 전용] 인증 로그 웹훅을 설정합니다.")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_webhook(self, interaction: discord.Interaction, 웹훅주소: str):
        con, cur = start_db()
        cur.execute("UPDATE guilds SET log_webhook = ? WHERE id = ?", (웹훅주소, interaction.guild_id))
        con.commit()
        con.close()
        await interaction.response.send_message(embed=embeda("success", "성공", "로그 웹훅이 설정되었습니다."), ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))