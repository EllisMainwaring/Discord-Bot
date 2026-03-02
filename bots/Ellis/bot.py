import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import aiohttp

# Load environment variables from the .env file
# This is where your DISCORD_TOKEN should be stored
load_dotenv()

# Get the bot token from environment variables
TOKEN = os.getenv("DISCORD_TOKEN")

# If the token is missing, stop the program
if not TOKEN:
    raise SystemExit("DISCORD_TOKEN is not set in your .env file")

# Set up logging to write information and errors to discord.log
handler = logging.FileHandler(
    filename="discord.log",
    encoding="utf-8",
    mode="w"  # Overwrites the log file every time the bot restarts
)

logging.basicConfig(level=logging.INFO, handlers=[handler])

# Set up Discord intents (permissions)
intents = discord.Intents.default()

# Required so the bot can read message content (needed for !commands)
intents.message_content = True

# Create the bot with "!" as the command prefix
bot = commands.Bot(command_prefix="!", intents=intents)

# Create a placeholder for a shared HTTP session
# This will be used for making API requests
bot.session = None


# This runs when the bot successfully connects to Discord
@bot.event
async def on_ready():
    # Create one reusable HTTP session for API calls
    bot.session = aiohttp.ClientSession()

    # Log that the bot is online
    logging.info(f"Logged in as {bot.user} (ID: {bot.user.id})")


# This runs when the bot shuts down
@bot.event
async def on_close():
    # Close the HTTP session properly
    if bot.session:
        await bot.session.close()


# Simple test command
# If a user types !ping, the bot replies "pong"
@bot.command()
async def ping(ctx):
    await ctx.send("pong")


# Main command to search for any anime using AniList
# Usage example: !anime naruto
@bot.command()
async def anime(ctx, *, anime_name: str):
    """
    Fetch anime information from AniList.
    The user can type any anime name after !anime.
    """

    # Tell the user the bot is working
    await ctx.send(f"Searching for '{anime_name}' on AniList...")

    # GraphQL query
    # This tells AniList exactly which information we want back
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        title {
          romaji
          english
        }
        episodes
        description
        siteUrl
        averageScore
        genres
      }
    }
    """

    # Variables for the query
    # The anime name typed by the user is passed here
    variables = {
        "search": anime_name
    }

    # Official AniList GraphQL endpoint
    url = "https://graphql.anilist.co"

    try:
        # Send POST request to AniList with the query and variables
        async with bot.session.post(
            url,
            json={"query": query, "variables": variables}
        ) as response:

            # Convert the response into JSON format
            data = await response.json()

        # Check if the anime was found
        if not data.get("data") or not data["data"]["Media"]:
            await ctx.send("Anime not found.")
            return

        # Extract the anime information
        media = data["data"]["Media"]

        # Use English title if available, otherwise use Romaji
        title = media["title"]["english"] or media["title"]["romaji"]

        # Get total episode count
        episodes = media["episodes"] or "Unknown"

        # Get description (limit to 300 characters to avoid Discord limits)
        description = (media["description"] or "No description available.")[:300] + "..."

        # Get link to AniList page
        site_url = media["siteUrl"]

        # Get average score
        score = media["averageScore"] or "N/A"

        # Get genres and turn list into a comma-separated string
        genres = ", ".join(media["genres"]) if media["genres"] else "N/A"

        # Create a Discord embed (formatted message)
        embed = discord.Embed(
            title=title,
            url=site_url,
            description=description,
            color=discord.Color.orange()
        )

        # Add extra fields to the embed
        embed.add_field(name="Episodes", value=str(episodes), inline=True)
        embed.add_field(name="Average Score", value=str(score), inline=True)
        embed.add_field(name="Genres", value=genres, inline=False)

        # Send the embed to the Discord channel
        await ctx.send(embed=embed)

    except Exception as e:
        # Log any errors to discord.log
        logging.error(str(e))

        # Send a simple error message to the user
        await ctx.send("Something went wrong fetching data.")


# Start the bot using your token
bot.run(TOKEN)