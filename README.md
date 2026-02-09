# Discord-Bot

Multi-user Discord bot playground for the Thematic Project.

## Quick start (per person)

1. Clone the repo.
2. Copy the template folder to your name:
   - Example: copy `bots/_template` to `bots/John`
3. In your folder, change `.env.example` to `.env` and paste your bot token.
4. Install dependencies - type the following into console:
   - `python -m venv .venv`
   - `./.venv/Scripts/activate`
   - `pip install -r requirements.txt`
5. Run your bot from your folder:
   - `python bot.py`

## Folder layout

- `bots/_template/` starter template for new users
- `bots/<Name>/` each person works in their own folder

## Notes

- Each bot reads `DISCORD_TOKEN` from the `.env` in its own folder.
- `.env` files are ignored by git, so tokens never get committed ! 