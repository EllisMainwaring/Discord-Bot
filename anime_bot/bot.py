import discord
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import aiohttp
import json
import requests
import re
import random

# Load environment variables from the .env file
# This is where your DISCORD_TOKEN and ANILIST_CLIENT_ID should be stored.
load_dotenv()

# Get the bot token from environment variables
TOKEN = os.getenv("DISCORD_TOKEN")

# Get the AniList OAuth client ID (needed to build the auth link for users)
ANILIST_CLIENT_ID = os.getenv("ANILIST_CLIENT_ID")

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

# Path to the file that tracks the last known airing state for each show.
# This is how we detect when a new episode has dropped.
TRACKER_FILE = "episode_tracker.json"


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


def load_tracker() -> dict:
    """
    Load the episode tracker from disk.
    Structure: { "media_id": { "next_episode": N, "title": "..." } }
    'next_episode' is the episode number AniList says is coming next.
    When that number goes up by 1, we know an episode just aired.
    """
    if not os.path.exists(TRACKER_FILE):
        return {}
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tracker(tracker: dict):
    """Save the episode tracker to disk."""
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2)


def get_username(links: dict, discord_id) -> str | None:
    """
    Return the AniList username for a Discord user.
    Handles both the old format (plain string) and new format (dict with 'username').
    """
    entry = links.get(str(discord_id))
    if entry is None:
        return None
    if isinstance(entry, str):
        return entry
    return entry.get("username")


def get_token(links: dict, discord_id) -> str | None:
    """
    Return the stored AniList OAuth token for a Discord user, or None if not set.
    Only the new dict format stores tokens.
    """
    entry = links.get(str(discord_id))
    if isinstance(entry, dict):
        return entry.get("token")
    return None


def set_token(links: dict, discord_id, token: str):
    """
    Store (or update) the AniList OAuth token for a Discord user.
    If their entry is still the old plain-string format, convert it to a dict first.
    """
    key = str(discord_id)
    entry = links.get(key)

    # Convert old string-only entries to the richer dict format
    if isinstance(entry, str):
        links[key] = {"username": entry, "token": token}
    elif isinstance(entry, dict):
        entry["token"] = token
    else:
        # No linked account yet — store just the token for now.
        # The user should !link first, but we save the token regardless.
        links[key] = {"username": None, "token": token}


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

    # Start the background task that checks for new episodes
    check_new_episodes.start()

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

# Command to set the bot avatar using an attached animated GIF
# Usage: attach a GIF file and send !animatedav
@bot.command()
async def animatedav(ctx):
    """
    Set the bot's avatar from an attached animated GIF.
    """
    if not ctx.message.attachments:
        await ctx.send(
            "Please attach an animated GIF to this command. Use `!animatedav` with a GIF attachment."
        )
        return

    attachment = ctx.message.attachments[0]
    content_type = attachment.content_type or ""
    if "gif" not in content_type and not attachment.filename.lower().endswith(".gif"):
        await ctx.send("Error: The attachment must be an animated GIF.")
        return

    if attachment.size > 256000:
        await ctx.send("Error: The GIF is too large. Discord avatar files must be under 256 KB.")
        return

    try:
        avatar_bytes = await attachment.read()
        await bot.user.edit(avatar=avatar_bytes)
        await ctx.send("Avatar updated successfully!")
    except discord.HTTPException as err:
        await ctx.send(f"Error: Could not update avatar: {err}")
    except Exception as err:
        logging.error(f"Animated avatar update failed: {err}")
        await ctx.send("Error: Something went wrong while updating the avatar.")

# Command to allow users to see all the commands available using !helps
@bot.command()
async def helps(ctx):
    await ctx.send("These are the currently available commands:"
    "\n"
    "\n ------IMPORTANT FOR FIRST TIME SETUP------"
    "\n- '!authanilist' -> the bot will DM you an authorisation link"
    "\n- '!settoken <your_token>' -> upon approval of the bot, put your token here and the bot will save and delete the message for security reasons"
    "\n"
    "\n ------ESSENTIAL COMMANDS------"
    "\n- '!ping' -> displays 'pong' to check if the bot is working"
    "\n- '!animatedav' -> set the bot avatar using an attached animated GIF"
    "\n- '!anime <name>' -> displays the details of the anime inputted"
    "\n- '!random' -> displays a random anime from AniList"
    "\n- '!charInfo' -> displays the details of the character inputted"
    "\n"
    "\n ------ANILIST ACCOUNT LINKING COMMANDS------"
    "\n- '!link <username>' -> links your Discord account to an AniList username"
    "\n- '!unlink' -> unlinks your Discord account from that AniList username"
    "\n- '!profile' -> displays your AniList account stats"
    "\n- '!profile @user' -> displays another user's AniList account stats"
    "\n"
    "\n ------ANILIST LIST UPDATING COMMANDS------"
    "\n- '!watching <anime>' -> marks an anime as currently watching"
    "\n- '!completed <anime>' -> marks an anime as completed"
    "\n- '!pause <anime>' -> puts an anime on hold"
    "\n- '!drop <anime>' -> puts an anime as dropped"
    "\n- '!plan <anime>' -> adds an anime to your plan to watch"
    "\n"
    "\n ------NOTIFICATIONS COMMANDS------"
    "\n- '!notify on' -> enables episode drop notifications (on by default)"
    "\n- '!notify off' -> disables notifications"
    "\n- '!notify' -> checks current notification settings"
    "\n- '!testnotify' -> sends a test DM to confirm notifications are working")

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
    anilist_username = get_username(links, target.id)

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

# ---------------------------------------------------------------------------
# AniList list-update helpers
# ---------------------------------------------------------------------------

async def search_anime_id(session: aiohttp.ClientSession, anime_name: str) -> tuple[int | None, str | None, str | None, str | None]:
    """
    Search AniList for an anime by name and return
    (media_id, display_title, cover_image_url, site_url).
    Returns (None, None, None, None) if nothing was found.
    """
    query = """
    query ($search: String) {
      Media(search: $search, type: ANIME) {
        id
        title {
          romaji
          english
        }
        coverImage {
          large
        }
        siteUrl
      }
    }
    """
    async with session.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": {"search": anime_name}}
    ) as response:
        data = await response.json()

    media = data.get("data", {}).get("Media")
    if not media:
        return None, None, None, None

    # Prefer English title; fall back to Romaji
    title = media["title"]["english"] or media["title"]["romaji"]
    cover = media.get("coverImage", {}).get("large")
    site_url = media.get("siteUrl")
    return media["id"], title, cover, site_url


async def update_anilist_status(
    session: aiohttp.ClientSession,
    token: str,
    media_id: int,
    status: str
) -> bool:
    """
    Update the authenticated user's list entry for a given anime.

    AniList status values:
      CURRENT   -> currently watching
      COMPLETED -> finished
      PAUSED    -> on hold
      DROPPED   -> dropped
      PLANNING  -> plan to watch

    Returns True if the update succeeded, False otherwise.
    """
    mutation = """
    mutation ($mediaId: Int, $status: MediaListStatus) {
      SaveMediaListEntry(mediaId: $mediaId, status: $status) {
        id
        status
      }
    }
    """
    # The Authorization header tells AniList which user is making the request
    headers = {"Authorization": f"Bearer {token}"}

    async with session.post(
        "https://graphql.anilist.co",
        json={"query": mutation, "variables": {"mediaId": media_id, "status": status}},
        headers=headers
    ) as response:
        data = await response.json()

    # If there are errors in the response, the update failed
    if data.get("errors"):
        logging.error(f"AniList mutation error: {data['errors']}")
        return False

    return data.get("data", {}).get("SaveMediaListEntry") is not None


async def _handle_list_update(ctx, anime_name: str, status: str, status_label: str):
    """
    Shared logic for all five list-update commands.
    Looks up the user's token, searches for the anime, then sends the mutation.
    """
    links = load_links()

    # Check the user has stored an OAuth token via !settoken
    token = get_token(links, ctx.author.id)
    if not token:
        await ctx.send(
            "You haven't linked your AniList token yet.\n"
            "Use `!authanilist` to see how to get and store your token."
        )
        return

    # Search for the anime to get its AniList media ID, cover image, and page URL
    await ctx.send(f"Searching for **{anime_name}**...")
    try:
        media_id, title, cover, site_url = await search_anime_id(bot.session, anime_name)
    except Exception as e:
        logging.error(str(e))
        await ctx.send("Something went wrong searching AniList.")
        return

    if not media_id:
        await ctx.send(f"Could not find an anime matching **{anime_name}** on AniList.")
        return

    # Send the update mutation to AniList on behalf of the user
    try:
        success = await update_anilist_status(bot.session, token, media_id, status)
    except Exception as e:
        logging.error(str(e))
        await ctx.send("Something went wrong updating your AniList.")
        return

    if success:
        # Build a confirmation embed matching the style of the rest of the bot
        embed = discord.Embed(
            title=title,
            url=site_url,
            color=discord.Color.orange()
        )
        embed.add_field(name="Status updated to", value=status_label, inline=False)
        embed.set_footer(text=f"Updated by {ctx.author.display_name}")
        if cover:
            embed.set_image(url=cover)
        await ctx.send(embed=embed)
    else:
        await ctx.send(
            f"Failed to update **{title}**. "
            "Your token may have expired — try `!settoken <new_token>` to refresh it."
        )


# ---------------------------------------------------------------------------
# OAuth setup commands
# ---------------------------------------------------------------------------

@bot.command()
async def authanilist(ctx):
    """
    Explains how to authorise the bot to update your AniList.
    The bot owner must set ANILIST_CLIENT_ID in .env first.
    Usage: !authanilist
    """
    if not ANILIST_CLIENT_ID:
        await ctx.send(
            "The bot owner hasn't set up an AniList API client yet.\n"
            "They need to create one at **https://anilist.co/settings/developer** "
            "and add `ANILIST_CLIENT_ID=<id>` to the `.env` file."
        )
        return

    # Build the AniList implicit-flow URL.
    # 'response_type=token' means AniList will put the access token directly in
    # the redirect URL — no server needed to catch a callback.
    auth_url = (
        f"https://anilist.co/api/v2/oauth/authorize"
        f"?client_id={ANILIST_CLIENT_ID}&response_type=token"
    )

    # Send instructions as a DM so the token isn't pasted publicly
    try:
        await ctx.author.send(
            "**How to connect your AniList account:**\n\n"
            f"1. Open this link: {auth_url}\n"
            "2. Click **Authorise** on AniList.\n"
            "3. You'll be redirected to a page — copy the access token\n"
            "4. Come back here and type:\n"
            "   `!settoken <paste your token here>`\n\n"
            "Keep your token private — anyone with it can edit your AniList!"
        )
        await ctx.send("I've sent you a DM with instructions!")
    except discord.Forbidden:
        # The user has DMs disabled — fall back to the channel
        await ctx.send(
            "I couldn't DM you (your DMs may be off).\n"
            f"Go to this link to authorise: <{auth_url}>\n"
            "Then use `!settoken <your_token>` — preferably in a private channel."
        )


@bot.command()
async def settoken(ctx, token: str = None):
    """
    Store your AniList OAuth token so the bot can update your list.
    For security, use this command in a DM or delete your message after sending.
    Usage: !settoken <your_anilist_token>
    """
    if not token:
        await ctx.send("Usage: `!settoken <your_anilist_token>`\nUse `!authanilist` to get your token.")
        return

    links = load_links()

    # If the user hasn't linked a username yet, remind them
    username = get_username(links, ctx.author.id)
    if not username:
        await ctx.send(
            "Note: you haven't linked an AniList username yet. "
            "Use `!link <anilist_username>` so your `!profile` command works too."
        )

    # Store the token
    set_token(links, ctx.author.id, token)
    save_links(links)

    # Try to delete the message so the token isn't visible in chat
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass  # Bot doesn't have permission to delete messages — that's fine

    await ctx.send(
        "Token saved! You can now use `!watching`, `!completed`, `!pause`, `!drop`, and `!plan`."
    )


# ---------------------------------------------------------------------------
# List-status commands
# ---------------------------------------------------------------------------

@bot.command()
async def watching(ctx, *, anime_name: str = None):
    """
    Mark an anime as currently watching on your AniList.
    Usage: !watching <anime name>
    Example: !watching Attack on Titan
    """
    if not anime_name:
        await ctx.send("Usage: `!watching <anime name>`")
        return
    await _handle_list_update(ctx, anime_name, "CURRENT", "Currently Watching")


@bot.command()
async def completed(ctx, *, anime_name: str = None):
    """
    Mark an anime as completed on your AniList.
    Usage: !completed <anime name>
    Example: !completed Fullmetal Alchemist Brotherhood
    """
    if not anime_name:
        await ctx.send("Usage: `!completed <anime name>`")
        return
    await _handle_list_update(ctx, anime_name, "COMPLETED", "Completed")


@bot.command()
async def pause(ctx, *, anime_name: str = None):
    """
    Mark an anime as on-hold (paused) on your AniList.
    Usage: !pause <anime name>
    Example: !pause Bleach
    """
    if not anime_name:
        await ctx.send("Usage: `!pause <anime name>`")
        return
    await _handle_list_update(ctx, anime_name, "PAUSED", "On Hold")


@bot.command()
async def drop(ctx, *, anime_name: str = None):
    """
    Mark an anime as dropped on your AniList.
    Usage: !drop <anime name>
    Example: !drop Berserk
    """
    if not anime_name:
        await ctx.send("Usage: `!drop <anime name>`")
        return
    await _handle_list_update(ctx, anime_name, "DROPPED", "Dropped")


@bot.command()
async def plan(ctx, *, anime_name: str = None):
    """
    Add an anime to your Plan to Watch list on AniList.
    Usage: !plan <anime name>
    Example: !plan Vinland Saga
    """
    if not anime_name:
        await ctx.send("Usage: `!plan <anime name>`")
        return
    await _handle_list_update(ctx, anime_name, "PLANNING", "Plan to Watch")


# ---------------------------------------------------------------------------
# Episode notification system
# ---------------------------------------------------------------------------

async def get_watching_list(session: aiohttp.ClientSession, username: str) -> list:
    """
    Fetch all anime a user currently has marked as CURRENT (watching) on AniList.
    AniList lists are public, so no token is needed here.
    Returns a list of media dicts, each containing id, title, and nextAiringEpisode.
    """
    query = """
    query ($username: String) {
      MediaListCollection(userName: $username, type: ANIME, status: CURRENT) {
        lists {
          entries {
            media {
              id
              title { romaji english }
              nextAiringEpisode {
                episode
                airingAt
              }
            }
          }
        }
      }
    }
    """
    async with session.post(
        "https://graphql.anilist.co",
        json={"query": query, "variables": {"username": username}}
    ) as response:
        data = await response.json()

    collection = data.get("data", {}).get("MediaListCollection")
    if not collection:
        return []

    # Flatten the nested lists -> entries structure into a simple list
    entries = []
    for lst in collection.get("lists", []):
        for entry in lst.get("entries", []):
            entries.append(entry["media"])
    return entries


@tasks.loop(minutes=30)
async def check_new_episodes():
    """
    Background task that runs every 30 minutes.
    For every linked user with notifications on, it:
      1. Fetches their current watching list from AniList
      2. Compares the 'next episode' number to what we last stored
      3. If the number went up, a new episode aired — DM the user
      4. Saves the updated state to episode_tracker.json
    """
    links = load_links()
    tracker = load_tracker()

    # Build two maps:
    #   watchers:   media_id -> [discord_id, ...]  (who is watching each show)
    #   media_info: media_id -> media dict          (airing data for each show)
    watchers = {}
    media_info = {}

    for discord_id, entry in links.items():
        # Skip users who have turned notifications off
        if isinstance(entry, dict) and not entry.get("notifications", True):
            continue

        username = get_username(links, discord_id)
        if not username:
            continue

        try:
            watching = await get_watching_list(bot.session, username)
        except Exception as e:
            logging.error(f"Failed to fetch watching list for {username}: {e}")
            continue

        for media in watching:
            mid = str(media["id"])
            media_info[mid] = media
            watchers.setdefault(mid, []).append(discord_id)

    # Now check each watched show for a new episode
    updated_tracker = dict(tracker)

    for media_id, media in media_info.items():
        next_ep = media.get("nextAiringEpisode")
        title = media["title"]["english"] or media["title"]["romaji"]

        # If AniList has no upcoming episode scheduled, nothing to track
        if next_ep is None:
            continue

        current_next = next_ep["episode"]

        # First time we've seen this show — just store the state, don't notify.
        # We only want to notify on *changes*, not on first detection.
        if media_id not in tracker:
            updated_tracker[media_id] = {"next_episode": current_next, "title": title}
            continue

        stored_next = tracker[media_id]["next_episode"]

        # The next-episode number has gone up, meaning the previous episode aired.
        # e.g. stored was 5, now it's 6 → episode 5 just dropped.
        if current_next > stored_next:
            aired_episode = current_next - 1

            for discord_id in watchers[media_id]:
                try:
                    user = await bot.fetch_user(int(discord_id))
                    await user.send(
                        f"Episode **{aired_episode}** of **{title}** has just aired! "
                        f"Time to update your AniList."
                    )
                except discord.Forbidden:
                    # User has DMs disabled — nothing we can do
                    logging.warning(f"Could not DM user {discord_id} (DMs disabled).")
                except Exception as e:
                    logging.error(f"Failed to notify {discord_id} for {title}: {e}")

        # Always update the stored state so we're ready to detect the next episode
        updated_tracker[media_id] = {"next_episode": current_next, "title": title}

    save_tracker(updated_tracker)


@check_new_episodes.before_loop
async def before_check_new_episodes():
    # Wait until the bot is fully connected before the task starts running
    await bot.wait_until_ready()


# ---------------------------------------------------------------------------
# Notification opt-in/out command
# ---------------------------------------------------------------------------

@bot.command()
async def notify(ctx, setting: str = None):
    """
    Toggle new-episode DM notifications on or off.
    Usage:
      !notify on     — enable notifications
      !notify off    — disable notifications
      !notify        — show your current setting
    """
    links = load_links()
    entry = links.get(str(ctx.author.id))

    if not entry:
        await ctx.send(
            "You need to link an AniList account first. Use `!link <anilist_username>`."
        )
        return

    # Upgrade old string-only entries to the dict format so we can store the setting
    if isinstance(entry, str):
        links[str(ctx.author.id)] = {"username": entry, "notifications": True}
        entry = links[str(ctx.author.id)]

    # No argument — show current status
    if setting is None:
        status = entry.get("notifications", True)
        await ctx.send(
            f"Episode notifications are currently **{'enabled' if status else 'disabled'}**.\n"
            "Use `!notify on` or `!notify off` to change this."
        )
        return

    if setting.lower() in ("on", "enable", "yes"):
        entry["notifications"] = True
        save_links(links)
        await ctx.send(
            "Episode notifications **enabled**! "
            "I'll DM you when a new episode of anything on your watching list drops."
        )
    elif setting.lower() in ("off", "disable", "no"):
        entry["notifications"] = False
        save_links(links)
        await ctx.send("Episode notifications **disabled**.")
    else:
        await ctx.send("Usage: `!notify on` or `!notify off`")


@bot.command()
async def testnotify(ctx):
    """
    Immediately sends you a fake episode notification DM so you can confirm
    that the bot can reach you and the message looks right.
    Usage: !testnotify
    """
    try:
        await ctx.author.send(
            "Episode **1** of **Test Anime** has just aired! "
            "Time to update your AniList.\n"
            "*(This is a test notification — everything is working!)*"
        )
        await ctx.send("Test notification sent! Check your DMs.")
    except discord.Forbidden:
        await ctx.send(
            "Couldn't send you a DM — your privacy settings are blocking it. "
            "Go to **Privacy & Safety** in Discord settings and enable DMs from server members."
        )


# Start the bot using your token
bot.run(TOKEN)

