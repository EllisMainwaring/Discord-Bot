#use Python for Manchester server
FROM python:3.13-slim

#set the 'Home' for your bot inside the container
WORKDIR /app

#copy the 'Shopping List' and install it
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

#copy the rest of the files (bot.py, etc.)
COPY . .

#point to readme
CMD ["python", "anime_bot/bot.py"]