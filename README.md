# Anime Discord Bot

Discord bot for fetching anime data (AniList integration) for the Thematic Project.

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
5. Create a `.env` file in the 'anime_bot'and write the following:
   - `DISCORD_TOKEN=your_bot_token_here`
6. Run the bot:
   - `python bot.py`

## Folder layout

- `bot.py` main entry point (this is the file you run)
- `.env` stores your Discord token (not committed to git)
- `requirements.txt` project dependencies
- `discord.log` bot logs
- `.gitignore` prevents sensitive files from being committed

## Notes

- The bot reads `DISCORD_TOKEN` from the `.env` file.
- `.env` is ignored by git, so your token will not be committed.
- Always run the bot using `python bot.py`.