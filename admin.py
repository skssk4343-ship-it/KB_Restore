import discord
from discord.ext import commands
from main import start_db, embeda, is_owner

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="생성")
    async def create_license(self, ctx, amount: int, days: int):
        if not is_owner(ctx.message):
            return await ctx.send(embed=embeda("error", "실패", "봇 소유자만 가능합니다."))
        
        # ... 기존 .생성 로직 ...
        await ctx.send(embed=embeda("success", "생성 성공", f"{amount}개 생성 완료"))

    @commands.command(name="복구")
    async def restore_user(self, ctx, key: str):
        if not is_owner(ctx.message):
            return await ctx.send(embed=embeda("error", "실패", "소유자만 가능합니다."))
        
        # ... 기존 .복구 로직 ...
        await ctx.send(embed=embeda("success", "복구", "복구가 완료되었습니다."))

async def setup(bot):
    await bot.add_cog(AdminCommands(bot))