import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import aiohttp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set in your .env file")

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
logging.basicConfig(level=logging.INFO, handlers=[handler])

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Create one shared session (better practice)
bot.session = None


@bot.event
async def on_ready():
    bot.session = aiohttp.ClientSession()
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.event
async def on_close():
    if bot.session:
        await bot.session.close()


@bot.command()
async def ping(ctx):
    await ctx.send("pong")


@bot.command()
async def hello(ctx):
    await ctx.send("World!")


@bot.command()
async def naruto(ctx):
    """Fetch first 10 Naruto episodes from Jikan"""

    await ctx.send("Fetching Naruto episodes...")

    try:
        # Step 1: Get Naruto MAL ID
        search_url = "https://api.jikan.moe/v4/anime?q=naruto&limit=1"
        async with bot.session.get(search_url) as response:
            search_data = await response.json()

        if not search_data["data"]:
            await ctx.send("Naruto not found.")
            return

        mal_id = search_data["data"][0]["mal_id"]

        # Step 2: Get episode list
        episodes_url = f"https://api.jikan.moe/v4/anime/{mal_id}/episodes"
        async with bot.session.get(episodes_url) as response:
            episode_data = await response.json()

        episodes = episode_data["data"][:10]  # First 10 episodes

        embed = discord.Embed(
            title="Naruto - First 10 Episodes",
            color=discord.Color.orange()
        )

        for ep in episodes:
            embed.add_field(
                name=f"Episode {ep['mal_id']}",
                value=ep["title"],
                inline=False
            )

        await ctx.send(embed=embed)

    except Exception as e:
        logging.error(str(e))
        await ctx.send("Something went wrong fetching data.")


bot.run(TOKEN)