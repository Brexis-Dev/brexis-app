import asyncio
import logging
import os
import threading

import discord
from discord.ext import commands

import database as db

logger = logging.getLogger(__name__)

# Channel structure
PUBLIC_CHANNELS = [
    ("welcome", "public"),
    ("announcements", "public"),
    ("switch-listings", "public"),
    ("pre-order-alerts", "public"),
    ("deals-and-finds", "public"),
]

PRIVATE_CHANNELS = [
    ("brexis-alerts", "private"),
    ("daily-briefing", "private"),
    ("rocket-fuel", "private"),
    ("market-reports", "private"),
]

CATEGORY_PUBLIC = "Saturday Morning PJs"
CATEGORY_PRIVATE = "Brexis Command Center"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
_loop = None
_bot_thread = None


def get_token():
    return os.environ.get("DISCORD_BOT_TOKEN") or db.get_config("DISCORD_BOT_TOKEN")


def get_guild_id():
    raw = os.environ.get("DISCORD_GUILD_ID") or db.get_config("DISCORD_GUILD_ID")
    return int(raw) if raw else None


@bot.event
async def on_ready():
    logger.info(f"Brexis Bot connected as {bot.user}")
    db.log_task("discord", "bot_ready", f"Brexis Bot online as {bot.user}", "success")


@bot.event
async def on_member_join(member):
    guild_id = get_guild_id()
    if not guild_id:
        return
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    welcome_ch = discord.utils.get(guild.text_channels, name="welcome")
    if welcome_ch:
        msg = (
            f"Welcome to **Saturday Morning PJs**, {member.mention}! 👋\n"
            f"I'm Brexis, the platform intelligence for Saturday Morning PJs. "
            f"Check out #announcements for the latest updates and #switch-listings for current inventory."
        )
        await welcome_ch.send(msg)
        db.log_task("discord", "welcome_message", f"Welcomed {member.display_name}", "success")


async def _setup_channels():
    guild_id = get_guild_id()
    if not guild_id:
        return "Discord Guild ID not configured."
    guild = bot.get_guild(guild_id)
    if not guild:
        return "Bot is not in the configured server."

    results = []

    # Public category
    pub_cat = discord.utils.get(guild.categories, name=CATEGORY_PUBLIC)
    if not pub_cat:
        pub_cat = await guild.create_category(CATEGORY_PUBLIC)
        results.append(f"Created category: {CATEGORY_PUBLIC}")

    for name, _ in PUBLIC_CHANNELS:
        existing = discord.utils.get(guild.text_channels, name=name)
        if not existing:
            await guild.create_text_channel(name, category=pub_cat)
            results.append(f"Created #public/{name}")

    # Private category — owner only
    priv_cat = discord.utils.get(guild.categories, name=CATEGORY_PRIVATE)
    if not priv_cat:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        priv_cat = await guild.create_category(CATEGORY_PRIVATE, overwrites=overwrites)
        results.append(f"Created category: {CATEGORY_PRIVATE}")

    for name, _ in PRIVATE_CHANNELS:
        existing = discord.utils.get(guild.text_channels, name=name)
        if not existing:
            await guild.create_text_channel(name, category=priv_cat)
            results.append(f"Created #private/{name}")

    summary = "\n".join(results) if results else "All channels already exist."
    db.log_task("discord", "setup_channels", summary, "success")
    return summary


async def _post_message(channel_name, message, pin=False):
    guild_id = get_guild_id()
    if not guild_id:
        return "Discord Guild ID not configured."
    guild = bot.get_guild(guild_id)
    if not guild:
        return "Bot is not in the configured server."

    channel = discord.utils.get(guild.text_channels, name=channel_name.lstrip("#"))
    if not channel:
        return f"Channel #{channel_name} not found."

    sent = await channel.send(message)
    if pin:
        await sent.pin()
        db.log_task("discord", "post_and_pin", f"Posted and pinned to #{channel_name}", "success")
    else:
        db.log_task("discord", "post_message", f"Posted to #{channel_name}", "success")
    return f"✓ Posted to #{channel_name}"


async def _create_channel(name, category_name=None, private=False):
    guild_id = get_guild_id()
    if not guild_id:
        return "Discord Guild ID not configured."
    guild = bot.get_guild(guild_id)
    if not guild:
        return "Bot is not in the configured server."

    existing = discord.utils.get(guild.text_channels, name=name)
    if existing:
        return f"Channel #{name} already exists."

    category = None
    if category_name:
        category = discord.utils.get(guild.categories, name=category_name)

    overwrites = {}
    if private:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }

    await guild.create_text_channel(name, category=category, overwrites=overwrites or discord.utils.MISSING)
    db.log_task("discord", "create_channel", f"Created {'private' if private else 'public'} #{name}", "success")
    return f"✓ Created #{name}"


# ── Thread-safe wrappers called from Flask/scheduler ──

def run_coroutine(coro):
    global _loop
    if _loop is None or not _loop.is_running():
        return None
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    try:
        return future.result(timeout=30)
    except Exception as e:
        logger.error(f"Discord coroutine error: {e}")
        return f"Error: {e}"


def setup_channels():
    return run_coroutine(_setup_channels())


def post_message(channel_name, message, pin=False):
    return run_coroutine(_post_message(channel_name, message, pin))


def create_channel(name, category_name=None, private=False):
    return run_coroutine(_create_channel(name, category_name, private))


def is_ready():
    return bot.is_ready()


# ── Bot startup ──

def start_bot():
    global _loop, _bot_thread

    token = get_token()
    if not token:
        logger.warning("DISCORD_BOT_TOKEN not configured — Discord bot not started.")
        return

    def run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(bot.start(token))
        except Exception as e:
            logger.error(f"Discord bot error: {e}")

    _bot_thread = threading.Thread(target=run, daemon=True, name="discord-bot")
    _bot_thread.start()
    logger.info("Discord bot thread started.")
