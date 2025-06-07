import os
import time
import secrets
from datetime import datetime, timedelta

import asyncio
import discord
from discord import app_commands
from discord.ext import tasks
import psycopg2
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_URL = os.getenv("VERIFICATION_URL")
ALLOWED_ROLE_IDS = list(map(int, os.getenv("ALLOWED_ROLE_IDS", "").split(",")))

if not all([TOKEN, DATABASE_URL, VERIFICATION_URL]):
    print("Missing one or more required environment variables.")
    exit(1)

def db_conn():
    return psycopg2.connect(DATABASE_URL)

def create_token():
    return secrets.token_urlsafe(32)

def init_db():
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS links (
                        discord_id BIGINT PRIMARY KEY,
                        mediawiki_username TEXT,
                        token TEXT NOT NULL,
                        created_at TIMESTAMP NOT NULL,
                        verified BOOLEAN DEFAULT FALSE
                    );
                """)
                conn.commit()
        print("[DB INIT] Table 'links' ensured and schema updated.")
    except Exception as e:
        print(f"[DB INIT ERROR] {e}")

# Wait for DB
for i in range(10):
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        print("✅ Database is ready.")
        break
    except psycopg2.OperationalError:
        print(f"⏳ Database not ready, retrying... ({i+1}/10)")
        time.sleep(3)
else:
    print("❌ Database did not become ready in time.")
    exit(1)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    init_db()
    await tree.sync()
    purge_old_links.start()
    print(f"🤖 Logged in as {client.user}!")

@tree.command(name="verify", description="Start the MediaWiki verification process")
async def verify(interaction: discord.Interaction):
    token = create_token()
    user_id = interaction.user.id
    now = datetime.utcnow()

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT verified FROM links WHERE discord_id = %s", (user_id,))
                result = cur.fetchone()

                if result:
                    if result[0]:
                        await interaction.response.send_message("✅ You are already verified.", ephemeral=True)
                    else:
                        await interaction.response.send_message("📬 You already have a pending verification. Check your DMs.", ephemeral=True)
                    return

                cur.execute(
                    "INSERT INTO links (discord_id, token, created_at, verified) VALUES (%s, %s, %s, FALSE)",
                    (user_id, token, now)
                )
                conn.commit()
    except Exception as e:
        await interaction.response.send_message("⚠ Failed to generate verification link. Please try again later.", ephemeral=True)
        print(f"Error inserting into DB: {e}")
        return

    link = f"{VERIFICATION_URL}?token={token}"
    try:
        await interaction.user.send(f"Click this link to verify your MediaWiki account:\n{link}")
        await interaction.response.send_message("📬 I've sent you a DM with the verification link!", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I can't DM you. Please enable DMs from server members.", ephemeral=True)

@tree.command(name="check_verified", description="List all verified users")
async def check_verified(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send_message("🚫 You do not have permission to run this command.", ephemeral=True)

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT discord_id, mediawiki_username FROM links WHERE verified = TRUE")
                results = cur.fetchall()
    except Exception as e:
        await interaction.response.send_message("⚠ Error querying the database.", ephemeral=True)
        print(f"Database error: {e}")
        return

    if not results:
        await interaction.response.send_message("✅ No users have been verified yet.", ephemeral=True)
        return

    verified_users = "\n".join([f"Discord ID: {row[0]}, MediaWiki Username: {row[1]}" for row in results])
    await interaction.response.send_message(f"✅ Verified users:\n{verified_users}", ephemeral=True)

@tree.command(name="deleteid", description="Delete a verified ID")
@app_commands.describe(userid="The Discord ID to delete")
async def deleteid(interaction: discord.Interaction, userid: int):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send_message("🚫 You do not have permission to run this command.", ephemeral=True)

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (userid,))
                if cur.rowcount == 0:
                    await interaction.response.send_message("ℹ No entry found for that user ID.", ephemeral=True)
                else:
                    conn.commit()
                    await interaction.response.send_message(f"🗑 Entry for Discord ID `{userid}` has been deleted.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("⚠ Error deleting entry.", ephemeral=True)
        print(f"Delete error: {e}")

@tree.command(name="getid", description="Get Discord ID by MediaWiki username")
@app_commands.describe(wiki_username="MediaWiki username to search for")
async def getid(interaction: discord.Interaction, wiki_username: str):
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT discord_id FROM links WHERE mediawiki_username = %s", (wiki_username,))
                result = cur.fetchone()
                if result:
                    await interaction.response.send_message(f"🔎 Discord ID for `{wiki_username}` is `{result[0]}`.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ No match found for that MediaWiki username.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("⚠ Error searching the database.", ephemeral=True)
        print(f"getid error: {e}")

@tree.command(name="getuser", description="Get MediaWiki username by Discord ID")
@app_commands.describe(discord_id="The Discord ID to look up")
async def getuser(interaction: discord.Interaction, discord_id: str):
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT mediawiki_username FROM links WHERE discord_id = %s", (discord_id,))
                result = cur.fetchone()
                if result:
                    await interaction.response.send_message(f"🔎 MediaWiki username for Discord ID `{discord_id}` is `{result[0]}`.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ No match found for that Discord ID.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("⚠ Error searching the database.", ephemeral=True)
        print(f"getuser error: {e}")

@tasks.loop(minutes=30)
async def purge_old_links():
    expiry = datetime.utcnow() - timedelta(hours=3)
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM links WHERE verified = FALSE AND created_at < %s",
                    (expiry,)
                )
                conn.commit()
        print("🧹 Old unverified links purged.")
    except Exception as e:
        print(f"Failed to purge old links: {e}")

client.run(TOKEN)
