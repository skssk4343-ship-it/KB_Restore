import discord
from discord.ext import commands
from main import start_db, embeda, is_guild, is_guild_valid, normalize_link

class UserCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="명령어")
    async def help_cmd(self, ctx):
        embed = discord.Embed(title="SinLinkBackup", description="...", color=0x5C6CDF)
        await ctx.send(embed=embed)

    @commands.command(name="등록")
    async def register(self, ctx, license_key: str):
        # ... 기존 .등록 로직 ...
        pass

    @commands.command(name="정보")
    async def info(self, ctx):
        # ... 기존 .정보 로직 ...
        pass

async def setup(bot):
    await bot.add_cog(UserCommands(bot))