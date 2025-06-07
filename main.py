import os
import time
import secrets
from datetime import datetime, timedelta

import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import psycopg2
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_URL = os.getenv("VERIFICATION_URL")
WIKI_AUTHOR_ROLE_ID = int(os.getenv("WIKI_AUTHOR_ROLE_ID", "0"))
ALLOWED_ROLE_IDS = list(map(int, os.getenv("ALLOWED_ROLE_IDS", "").split(",")))
DISCORD_PREFIX = os.getenv("DISCORD_PREFIX", "$w")  # fallback to "$w" if not set

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

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = commands.Bot(command_prefix=DISCORD_PREFIX, intents=intents)
tree = client.tree

@client.event
async def on_ready():
    init_db()
    await tree.sync()
    purge_old_links.start()
    grant_roles_loop.start()
    print(f"🤖 Logged in as {client.user}!")

# Text command wrapper helper
def wrap_text_command(handler):
    async def wrapped(ctx, *args):
        class DummyInteraction:
            def __init__(self, user, response):
                self.user = user
                self.response = response
        interaction = DummyInteraction(ctx.author, ctx)
        await handler(interaction, *args)
    return wrapped

@tree.command(name="verify", description="Start the MediaWiki verification process")
async def slash_verify(interaction: discord.Interaction):
    await handle_verify(interaction)

@client.command(name="verify", help="Start the MediaWiki verification process")
@wrap_text_command
async def text_verify(interaction):
    await handle_verify(interaction)

async def handle_verify(interaction):
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
                        await interaction.response.send("✅ You are already verified.")
                    else:
                        await interaction.response.send("📬 You already have a pending verification. Check your DMs.")
                    return

                cur.execute(
                    "INSERT INTO links (discord_id, token, created_at, verified) VALUES (%s, %s, %s, FALSE)",
                    (user_id, token, now)
                )
                conn.commit()
    except Exception as e:
        await interaction.response.send("⚠ Failed to generate verification link. Please try again later.")
        print(f"Error inserting into DB: {e}")
        return

    link = f"{VERIFICATION_URL}?token={token}"
    try:
        await interaction.user.send(f"Click this link to verify your MediaWiki account:\n{link}")
        await interaction.response.send("📬 I've sent you a DM with the verification link!")
    except discord.Forbidden:
        await interaction.response.send("❌ I can't DM you. Please enable DMs from server members.")

@tree.command(name="unverify", description="Remove your own verification entry")
async def slash_unverify(interaction: discord.Interaction):
    await handle_unverify(interaction)

@client.command(name="unverify", help="Remove your own verification entry")
@wrap_text_command
async def text_unverify(interaction):
    await handle_unverify(interaction)

async def handle_unverify(interaction):
    user_id = interaction.user.id
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (user_id,))
                deleted = cur.fetchone()
                if not deleted:
                    await interaction.response.send("ℹ No entry found to remove.")
                else:
                    conn.commit()
                    await interaction.user.remove_roles(discord.Object(id=WIKI_AUTHOR_ROLE_ID))
                    await interaction.response.send("✅ Your verification entry has been removed.")
    except Exception as e:
        await interaction.response.send("⚠ Error during unverification.")
        print(f"Unverify error: {e}")

@tree.command(name="check_verified", description="List all verified users")
async def slash_check_verified(interaction: discord.Interaction):
    await handle_check_verified(interaction)

@client.command(name="check_verified", help="List all verified users")
@wrap_text_command
async def text_check_verified(interaction):
    await handle_check_verified(interaction)

async def handle_check_verified(interaction):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send("🚫 You do not have permission to run this command.")

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT discord_id, mediawiki_username FROM links WHERE verified = TRUE")
                results = cur.fetchall()
    except Exception as e:
        await interaction.response.send("⚠ Error querying the database.")
        print(f"Database error: {e}")
        return

    if not results:
        await interaction.response.send("✅ No users have been verified yet.")
        return

    verified_users = "\n".join([f"Discord ID: {row[0]}, MediaWiki Username: {row[1]}" for row in results])
    await interaction.response.send(f"✅ Verified users:\n{verified_users}")

@tree.command(name="deleteid", description="Delete a verified ID")
@app_commands.describe(userid="The Discord ID to delete")
async def slash_deleteid(interaction: discord.Interaction, userid: str):
    await handle_deleteid(interaction, userid)

@client.command(name="deleteid", help="Delete a verified ID")
@wrap_text_command
async def text_deleteid(interaction, userid: str):
    await handle_deleteid(interaction, userid)

async def handle_deleteid(interaction, userid):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send("🚫 You do not have permission to run this command.")

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (int(userid),))
                deleted = cur.fetchone()
                if not deleted:
                    await interaction.response.send("ℹ No entry found for that user ID.")
                else:
                    conn.commit()
                    await interaction.response.send(f"🗑 Entry for Discord ID `{userid}` has been deleted.")
    except Exception as e:
        await interaction.response.send("⚠ Error deleting entry.")
        print(f"Delete error: {e}")

@tree.command(name="getid", description="Get Discord ID by MediaWiki username")
@app_commands.describe(wiki_username="MediaWiki username to search for")
async def slash_getid(interaction: discord.Interaction, wiki_username: str):
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
async def slash_getuser(interaction: discord.Interaction, discord_id: str):
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
                cur.execute("DELETE FROM links WHERE verified = FALSE AND created_at < %s", (expiry,))
                conn.commit()
        print("🧹 Old unverified links purged.")
    except Exception as e:
        print(f"Failed to purge old links: {e}")

@tasks.loop(minutes=5)
async def grant_roles_loop():
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT discord_id FROM links WHERE verified = TRUE")
                verified_ids = cur.fetchall()

        for guild in client.guilds:
            for discord_id_tuple in verified_ids:
                member = guild.get_member(discord_id_tuple[0])
                if member and WIKI_AUTHOR_ROLE_ID not in [r.id for r in member.roles]:
                    await member.add_roles(discord.Object(id=WIKI_AUTHOR_ROLE_ID))
                    print(f"✅ Granted role to {member.display_name} in {guild.name}")
    except Exception as e:
        print(f"Error in grant_roles_loop: {e}")

client.run(TOKEN)
