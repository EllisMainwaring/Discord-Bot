# Anime Discord Bot

Discord bot for fetching anime data and managing AniList lists (AniList integration) for the Thematic Project.

## Quick start

1. Clone the repo.
2. Navigate into the project folder if needed:
   - `cd anime_bot`
3. Create and activate a virtual environment:
   - `python -m venv .venv`
   - Windows: `.\.venv\Scripts\activate`
   - Mac/Linux: `source .venv/bin/activate`
4. Install dependencies:
   - `pip install -r requirements.txt`
5. Create a `.env` file in the `anime_bot` folder with the following:
   - `DISCORD_TOKEN=your_bot_token_here`
   - `ANILIST_CLIENT_ID=your_anilist_client_id` (needed for list update commands — create one at https://anilist.co/settings/developer, set the redirect URL to `https://anilist.co/api/v2/oauth/pin`)
6. Run the bot:
   - `python anime_bot/bot.py`

## Folder layout

- `bot.py` — main entry point (this is the file you run)
- `.env` — stores your Discord token and AniList client ID (not committed to git)
- `linked_accounts.json` — stores Discord → AniList account links and OAuth tokens (auto-created, not committed)
- `episode_tracker.json` — tracks airing state for episode notifications (auto-created, not committed)
- `votes.db` — SQLite database storing polls, options, and votes (auto-created, not committed)
- `requirements.txt` — project dependencies
- `discord.log` — bot logs
- `.gitignore` — prevents sensitive files from being committed

## Commands

### General
| Command | Description |
|---|---|
| `!ping` | Check the bot is alive |
| `!anime <name>` | Search for an anime and display its info |
| `!recva <voice actor>` | Recommend an anime featuring that voice actor (EN or JP) |
| `!random` | Display a random anime |
| `!charInfo <name>` | Look up a character |
| `!animatedav` | Set the bot's avatar using an attached animated GIF |

### AniList account linking
| Command | Description |
|---|---|
| `!link <username>` | Link your Discord account to an AniList username |
| `!unlink` | Remove your AniList link |
| `!profile` | View your AniList stats |
| `!profile @user` | View another user's AniList stats |

### AniList list updating
These commands update your AniList directly from Discord. Requires a one-time token setup (see below).

| Command | Description |
|---|---|
| `!watching <anime>` | Mark an anime as currently watching |
| `!completed <anime>` | Mark an anime as completed |
| `!pause <anime>` | Put an anime on hold |
| `!drop <anime>` | Mark an anime as dropped |
| `!plan <anime>` | Add an anime to your plan to watch |

**First time setup:**
1. Run `!authanilist` — the bot will DM you an authorisation link
2. Click the link, approve the bot on AniList, then copy your access token from the redirect URL
3. Run `!settoken <your_token>` — the bot saves it and deletes your message

### Voting
Start a timed poll where server members vote on which anime to watch. Members add options via a popup and vote from a dropdown — each user gets one vote (changeable until the poll ends). Results are posted automatically when the timer expires.

| Command | Description |
|---|---|
| `!vote <duration>` | Start a poll (e.g. `!vote 5m` — supports `s`, `m`, `h`, `d`; default 60s) |
| `!vote_stop` | Manage the active poll — view results, continue, or delete (creator only) |

### Episode notifications
The bot checks AniList every 30 minutes and DMs you when a new episode of something on your watching list has aired.

| Command | Description |
|---|---|
| `!notify on` | Enable episode drop notifications (on by default) |
| `!notify off` | Disable notifications |
| `!notify` | Check your current notification setting |
| `!testnotify` | Send a test DM to confirm notifications are working |

## Notes

- `.env` is ignored by git — your tokens will never be committed.
- Always run the bot with `python bot.py` from inside the `anime_bot` folder.
- Episode notifications require your AniList list to be public (the default).

## The Team

Team Leader: Ellis (https://github.com/EllisMainwaring)

Scrum Master: Matei (https://github.com/mateiwaller)

Infrastructure Lead: Shannon (https://github.com/my-entropy)

Lead Developer: Dylan (https://github.com/dyllo06)

Feature Developer: Angelina (https://github.com/Angelina-EA)

UI/UX Designer: Curtis (https://github.com/cunacurtis8-ux)
