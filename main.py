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

atl-owl# vim wiki-link-bot/main.py
atl-owl# vim wiki-link-bot/.env                 
atl-owl# systemctl restart wiki-link-bot.service
atl-owl# cat wiki-link-bot/main.py              
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

# Load environment variables
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("DISCORD_PREFIX", "!")
DATABASE_URL = os.getenv("DATABASE_URL")
VERIFICATION_URL = os.getenv("VERIFICATION_URL")
WIKI_AUTHOR_ROLE_ID = int(os.getenv("WIKI_AUTHOR_ROLE_ID", "0"))
ALLOWED_ROLE_IDS = list(map(int, os.getenv("ALLOWED_ROLE_IDS", "").split(",")))

if not all([TOKEN, DATABASE_URL, VERIFICATION_URL]):
    print("Missing one or more required environment variables.")
    exit(1)

# Set up intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

# Create bot
bot = commands.Bot(command_prefix=PREFIX, intents=intents)
tree = bot.tree
processed_users = set()

def db_conn():
    return psycopg2.connect(DATABASE_URL)

def create_token():
    return secrets.token_urlsafe(32)

def init_db():
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

# Wait for DB to be ready
for i in range(10):
    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        break
    except psycopg2.OperationalError:
        time.sleep(3)
else:
    print("Database not ready.")
    exit(1)

@bot.event
async def on_ready():
    init_db()
    await tree.sync()
    purge_old_links.start()
    assign_roles_to_verified_users.start()
    print(f"Logged in as {bot.user}!")

# --- SHARED VERIFY LOGIC ---
async def do_verify(ctx, user):
    token = create_token()
    now = datetime.utcnow()
    user_id = user.id

    try:
        with db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT verified FROM links WHERE discord_id = %s", (user_id,))
                result = cur.fetchone()
                if result:
                    if result[0]:
                        return await ctx.send("✅ You are already verified.", ephemeral=True)
                    else:
                        return await ctx.send("📬 You already have a pending verification. Check your DMs.", ephemeral=True)

                cur.execute(
                    "INSERT INTO links (discord_id, token, created_at, verified) VALUES (%s, %s, %s, FALSE)",
                    (user_id, token, now)
                )
                conn.commit()
    except Exception as e:
        return await ctx.send("⚠ Error creating verification entry.", ephemeral=True)

    link = f"{VERIFICATION_URL}?token={token}"
    try:
        await user.send(f"Click this link to verify your MediaWiki account:\n{link}")
        await ctx.send("📬 I've sent you a DM with the verification link!", ephemeral=True)
    except discord.Forbidden:
        await ctx.send("❌ I can't DM you. Please enable DMs from server members.", ephemeral=True)

# --- SLASH & TEXT COMMANDS ---

@tree.command(name="unverify", description="Remove your verification link and data from the system")
async def slash_unverify(interaction: discord.Interaction):
    user_id = interaction.user.id
    removed = False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (user_id,))
            removed = cur.rowcount > 0
            if removed:
                conn.commit()
                processed_users.discard(user_id)

    if removed:
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, id=WIKI_AUTHOR_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="User unverifying")
        await interaction.response.send_message("✅ Your verification has been removed.", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ You are not currently verified.", ephemeral=True)

@bot.command(name="unverify", help="Remove your own verification entry from the database")
async def cmd_unverify(ctx):
    user_id = ctx.author.id
    removed = False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (user_id,))
            removed = cur.rowcount > 0
            if removed:
                conn.commit()
                processed_users.discard(user_id)

    if removed:
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                role = discord.utils.get(guild.roles, id=WIKI_AUTHOR_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="User unverifying")
        await ctx.send("✅ Your verification has been removed.")
    else:
        await ctx.send("ℹ You are not currently verified.")


@tree.command(name="deleteid", description="Admin: Delete a user's verification by Discord ID")
@app_commands.describe(userid="The Discord user ID to delete")
async def slash_deleteid(interaction: discord.Interaction, userid: int):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send_message("🚫 You do not have permission.", ephemeral=True)

    removed = False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (userid,))
            removed = cur.rowcount > 0
            if removed:
                conn.commit()
                processed_users.discard(userid)

    if removed:
        for guild in bot.guilds:
            member = guild.get_member(userid)
            if member:
                role = discord.utils.get(guild.roles, id=WIKI_AUTHOR_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="Admin deleteid command")
        await interaction.response.send_message(f"🗑 Entry for ID `{userid}` removed.", ephemeral=True)
    else:
        await interaction.response.send_message("ℹ No entry found.", ephemeral=True)

@bot.command(name="deleteid", help="Admin: Delete a user's verification by Discord ID")
async def cmd_deleteid(ctx, userid: int):
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        return await ctx.send("🚫 You do not have permission.")

    removed = False
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE discord_id = %s RETURNING *", (userid,))
            removed = cur.rowcount > 0
            if removed:
                conn.commit()
                processed_users.discard(userid)

    if removed:
        for guild in bot.guilds:
            member = guild.get_member(userid)
            if member:
                role = discord.utils.get(guild.roles, id=WIKI_AUTHOR_ROLE_ID)
                if role and role in member.roles:
                    await member.remove_roles(role, reason="Admin deleteid command")
        await ctx.send(f"🗑 Entry for ID `{userid}` removed.")
    else:
        await ctx.send("ℹ No entry found.")


@tree.command(name="check_verified", description="Admin: Show all currently verified users")
async def slash_check_verified(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_ROLE_IDS for role in interaction.user.roles):
        return await interaction.response.send_message("🚫 You do not have permission.", ephemeral=True)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_id, mediawiki_username FROM links WHERE verified = TRUE")
            results = cur.fetchall()
    if not results:
        return await interaction.response.send_message("✅ No users are currently verified.", ephemeral=True)
    lines = [f"{row[1]} → {row[0]}" for row in results]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.command(name="check_verified", help="Admin: Show all currently verified users")
async def cmd_check_verified(ctx):
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        return await ctx.send("🚫 You do not have permission.")
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_id, mediawiki_username FROM links WHERE verified = TRUE")
            results = cur.fetchall()
    if not results:
        return await ctx.send("✅ No users are currently verified.")
    lines = [f"{row[1]} → {row[0]}" for row in results]
    await ctx.send("\n".join(lines))

@tree.command(name="getid", description="Get a Discord ID by searching MediaWiki username")
@app_commands.describe(wiki_username="The MediaWiki username to search")
async def slash_getid(interaction: discord.Interaction, wiki_username: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_id FROM links WHERE mediawiki_username = %s", (wiki_username,))
            result = cur.fetchone()
    if result:
        await interaction.response.send_message(f"🔎 Discord ID: `{result[0]}`", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No match found.", ephemeral=True)

@bot.command(name="getid", help="Look up Discord ID by MediaWiki username")
async def cmd_getid(ctx, wiki_username: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_id FROM links WHERE mediawiki_username = %s", (wiki_username,))
            result = cur.fetchone()
    if result:
        await ctx.send(f"🔎 Discord ID: `{result[0]}`")
    else:
        await ctx.send("❌ No match found.")

@tree.command(name="getuser", description="Get MediaWiki username from Discord ID")
@app_commands.describe(discord_id="The Discord ID to search for")
async def slash_getuser(interaction: discord.Interaction, discord_id: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT mediawiki_username FROM links WHERE discord_id = %s", (discord_id,))
            result = cur.fetchone()
    if result:
        await interaction.response.send_message(f"👤 MediaWiki: `{result[0]}`", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No match found.", ephemeral=True)

@bot.command(name="getuser", help="Look up MediaWiki username by Discord ID")
async def cmd_getuser(ctx, discord_id: str):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT mediawiki_username FROM links WHERE discord_id = %s", (discord_id,))
            result = cur.fetchone()
    if result:
        await ctx.send(f"👤 MediaWiki: `{result[0]}`")
    else:
        await ctx.send("❌ No match found.")

# --- BACKGROUND TASKS ---

@tasks.loop(minutes=30)
async def purge_old_links():
    expiry = datetime.utcnow() - timedelta(hours=3)
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM links WHERE verified = FALSE AND created_at < %s", (expiry,))
            conn.commit()

@tasks.loop(minutes=5)
async def assign_roles_to_verified_users():
    global processed_users
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_id FROM links WHERE verified = TRUE")
            verified_ids = [row[0] for row in cur.fetchall()]

    all_member_ids = {m.id for g in bot.guilds for m in g.members}
    processed_users.intersection_update(all_member_ids)

    for discord_id in verified_ids:
        if discord_id in processed_users:
            continue
        for guild in bot.guilds:
            member = guild.get_member(discord_id)
            if member:
                role = discord.utils.get(guild.roles, id=WIKI_AUTHOR_ROLE_ID)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role, reason="Verified MediaWiki user")
                        processed_users.add(discord_id)
                    except Exception as e:
                        print(f"Role assignment error: {e}")

bot.run(TOKEN)
