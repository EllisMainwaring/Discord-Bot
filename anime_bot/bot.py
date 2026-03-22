import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import aiohttp
import json
import requests
import re
import random

# Load environment variables from the .env file
# This is where your DISCORD_TOKEN should be stored. Find it here: https://discord.com/developers/applications
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

# Path to the file that stores Discord -> AniList links
LINKS_FILE = "linked_accounts.json"


def load_links() -> dict:
    """Load the Discord->AniList account links from disk."""
    if not os.path.exists(LINKS_FILE):
        return {}
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_links(links: dict):
    """Save the Discord->AniList account links to disk."""
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        json.dump(links, f, indent=2)


async def fetch_anilist_user(session: aiohttp.ClientSession, username: str) -> dict | None:
    """
    Fetch an AniList user profile by username.
    Returns the user dict on success, or None if not found.
    """
    query = """
    query ($name: String) {
      User(name: $name) {
        id
        name
        siteUrl
        avatar {
          large
        }
        statistics {
          anime {
            count
            episodesWatched
            meanScore
          }
          manga {
            count
            chaptersRead
            meanScore
          }
        }
      }
    }
    """
    async with session.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": {"name": username}}
    ) as response:
        data = await response.json()

    if data.get("errors") or not data.get("data", {}).get("User"):
        return None

    return data["data"]["User"]


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
        coverImage {
            medium
            large
        }
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

        # Get cover image URL (use medium size if available)
        image_url = media["coverImage"]["medium"] if media.get("coverImage") else None

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
        embed.set_image(url=image_url)

        # Send the embed to the Discord channel
        await ctx.send(embed=embed)

    except Exception as e:
        # Log any errors to discord.log
        logging.error(str(e))

        # Send a simple error message to the user
        await ctx.send("Something went wrong fetching data.")


@bot.command()
async def link(ctx, anilist_username: str = None):
    """
    Link your Discord account to an AniList username.
    Usage: !link <anilist_username>
    """
    if not anilist_username:
        await ctx.send("Usage: `!link <anilist_username>`")
        return

    await ctx.send(f"Looking up **{anilist_username}** on AniList...")

    try:
        user = await fetch_anilist_user(bot.session, anilist_username)
    except Exception as e:
        logging.error(str(e))
        await ctx.send("Something went wrong contacting AniList.")
        return

    if not user:
        await ctx.send(f"No AniList account found with the username **{anilist_username}**.")
        return

    links = load_links()
    links[str(ctx.author.id)] = user["name"]
    save_links(links)

    await ctx.send(
        f"Linked your Discord account to AniList user **{user['name']}**. "
        f"Use `!profile` to view your stats."
    )


@bot.command()
async def unlink(ctx):
    """
    Remove the link between your Discord account and AniList.
    Usage: !unlink
    """
    links = load_links()
    if str(ctx.author.id) not in links:
        await ctx.send("You don't have a linked AniList account. Use `!link <anilist_username>` to set one.")
        return

    removed = links.pop(str(ctx.author.id))
    save_links(links)
    await ctx.send(f"Unlinked your Discord account from AniList user **{removed}**.")


@bot.command()
async def profile(ctx, member: discord.Member = None):
    """
    Show the AniList profile for you or a mentioned user.
    Usage: !profile or !profile @user
    """
    target = member or ctx.author

    links = load_links()
    anilist_username = links.get(str(target.id))

    if not anilist_username:
        if target == ctx.author:
            await ctx.send("You haven't linked an AniList account yet. Use `!link <anilist_username>`.")
        else:
            await ctx.send(f"**{target.display_name}** hasn't linked an AniList account.")
        return

    try:
        user = await fetch_anilist_user(bot.session, anilist_username)
    except Exception as e:
        logging.error(str(e))
        await ctx.send("Something went wrong contacting AniList.")
        return

    if not user:
        await ctx.send(f"Could not find AniList user **{anilist_username}**. They may have changed their username.")
        return

    anime_stats = user["statistics"]["anime"]
    manga_stats = user["statistics"]["manga"]

    embed = discord.Embed(
        title=user["name"],
        url=user["siteUrl"],
        color=discord.Color.blue()
    )
    embed.set_author(name=f"{target.display_name}'s AniList Profile")
    embed.set_thumbnail(url=user["avatar"]["large"])

    embed.add_field(
        name="Anime",
        value=f"**{anime_stats['count']}** titles\n{anime_stats['episodesWatched']} episodes\nMean score: {anime_stats['meanScore'] or 'N/A'}",
        inline=True
    )
    embed.add_field(
        name="Manga",
        value=f"**{manga_stats['count']}** titles\n{manga_stats['chaptersRead']} chapters\nMean score: {manga_stats['meanScore'] or 'N/A'}",
        inline=True
    )

    await ctx.send(embed=embed)

@bot.command(aliases=['random'])
async def randoms(ctx):
    """
    Fetch anime information from AniList.
    """
  
    # Tell the user the bot is working
    await ctx.send(f"Displaying a random anime from AniList...")

    # GraphQL query
    # This tells AniList exactly which information we want back
    query = """
    query ($page: Int) {
    Page(page: $page, perPage: 50)
    {
      media(type: ANIME) {
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
    }
    """

    # Select a random page from AniList
    ranPages = random.randint(1, 400)
    variables = {"page": ranPages}

    # Send POST request to AniList with the query and variables
    res = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )

    # Find a random anime to display on the page chosen 
    ranList = res.json()["data"]["Page"]["media"]
    randomList = random.choice(ranList)
    
    # Use English title if available, otherwise use Romaji
    title = randomList["title"]["english"] or randomList["title"]["romaji"]

    # Get total episode count
    episodes = randomList["episodes"] or "Unknown"

    # Get description — strip HTML tags (AniList returns HTML like <br>, <i>), then limit length
    raw_description = re.sub(r"<[^>]+>", "", randomList["description"] or "")
    description = (raw_description.strip() or "No description available.")[:300] + "..."

    # Get link to AniList page
    site_url = randomList["siteUrl"]

    # Get average score
    score = randomList["averageScore"] or "N/A"

    # Get genres and turn list into a comma-separated string
    genres = ", ".join(randomList["genres"]) if randomList["genres"] else "N/A"

    # Create a Discord embed (formatted message)
    ranEmbed = discord.Embed(
        title=title,
        url=site_url,
        description=description,
        color=discord.Color.blue()
    )

    # Add extra fields to the embed
    ranEmbed.add_field(name="Episodes", value=str(episodes), inline=True)
    ranEmbed.add_field(name="Average Score", value=str(score), inline=True)
    ranEmbed.add_field(name="Genres", value=genres, inline=False)

    # Send the embed to the Discord channel
    await ctx.send(embed=ranEmbed)
    
@bot.command()
async def charInfo(ctx, *, char_name):
    """
    Fetch character information from AniList.
    The user can type any anime name after !charInfo.
    """

    # Tell the user the bot is working
    await ctx.send(f"Searching for '{char_name}' on AniList...")

    # GraphQL query
    # This tells AniList exactly which information we want back
    query = """
    query ($search: String) {
      Character(search: $search) {
        name { 
          full 
        }
        image {
            medium
            large
        }
        media (perPage: 1)
        {
          nodes {
            title {
              romaji
              english
            }
          }
        }
        description
        siteUrl
      }
    }
    """

    # Send POST request to AniList with the query and variables
    variables = {"search": char_name}
    res = requests.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": variables}
    )

    # Get the data necessary in order to display it
    character = res.json()["data"]["Character"]
    charNode = ((character.get("media") or {}).get("nodes") or [{}])[0]
    title = charNode.get("title", {}).get("english") or charNode.get("title", {}).get("romaji") or character.get("name", {}).get("full") or "Unknown Title"
    nameChar = character["name"]["full"]
    raw_description = re.sub(r"<[^>]+>", "", character["description"] or "")
    description = (raw_description.strip() or "No description available.")[:300] + "..."
    site_url = character["siteUrl"]
    image_url = character["image"]["medium"] if character.get("image") else None
        
    # Create a Discord embed (formatted message)
    charEmbed = discord.Embed(
      title=nameChar,
      color=discord.Color.blue()
        )
    
    # Add additional content to the embed
    charEmbed.add_field(name="Featured in: ", value=str(title), inline=False)
    charEmbed.add_field(name="Character description: ", value=str(description), inline=False)
    charEmbed.add_field(name="AniList Character Profile: ", value=str(site_url), inline=False)
    charEmbed.set_image(url=image_url)
    
    # Send the embed to the Discord channel
    await ctx.send(embed=charEmbed)

# Start the bot using your token
bot.run(TOKEN)

