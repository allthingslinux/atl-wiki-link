import os
import asyncio
import discord
from discord.ext import commands, tasks
import psycopg2
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("DISCORD_PREFIX", "!")
DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_URL = os.getenv("VERIFICATION_URL")
ALLOWED_ROLE_IDS = list(map(int, os.getenv("ALLOWED_ROLE_IDS", "").split(",")))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

def create_token():
    return secrets.token_urlsafe(32)

def db_conn():
    return psycopg2.connect(DATABASE_URL)

@bot.event
async def on_ready():
    purge_old_links.start()
    print(f"Logged in as {bot.user}!")

@bot.command()
async def verify(ctx: commands.Context):
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        return await ctx.send("You do not have permission to run this command.")
    
    token = create_token()
    user_id = ctx.author.id
    now = datetime.utcnow()

    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO links (discord_id, token, created_at, verified) VALUES (%s, %s, %s, FALSE)",
                        (user_id, token, now))
            conn.commit()

    link = f"{VERIFICATION_URL}?token={token}"
    await ctx.author.send(f"Click this link to verify your MediaWiki account:
{link}")
    await ctx.send("I've sent you a DM with the verification link!")

@tasks.loop(minutes=30)
async def purge_old_links():
    expiry = datetime.utcnow() - timedelta(hours=3)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE verified = FALSE AND created_at < %s", (expiry,))
            conn.commit()
