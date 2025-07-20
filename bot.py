# bot.py
# --------------------------------------------------------------------
# Terraria “class setup” helper bot – fetches live presets from the
#   Guide:Class_setups wiki page, shows them by phase & class.
# --------------------------------------------------------------------
import asyncio
import json
import os
import re
import typing as t
from datetime import datetime
from pathlib import Path

import aiohttp
import discord
from discord import app_commands, Embed
from dotenv import load_dotenv
from rapidfuzz import process, fuzz

# --------------------------- CONFIG ---------------------------------
load_dotenv()
TOKEN: str | None = os.getenv("TOKEN")          # set via env variable or .env
CACHE_TTL = 60 * 60                             # seconds (1 h)
CONFIG_FILE = Path("botconfig.json")            # stores phase per guild

WIKI_API = "https://terraria.fandom.com/api.php"
GUIDE_PAGE = "Guide:Class_setups"

# Map whichever role spellings you use -> the wiki’s section names
ROLE_TO_SECTION = {
    "ranger": "Ranged",
    "ranged": "Ranged",
    "mage": "Mage",
    "magic": "Mage",
    "summoner": "Summoner",
    "melee": "Melee",
}

# --------------------------- GLOBAL STATE ---------------------------
intents = discord.Intents.none()
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# { "phase → class → category → [items]" }
GuideCache: dict[str, dict[str, dict[str, list[str]]]] = {}
GuideFetchedAt: float | None = None

# {guild_id: {"phase": "<name>"}}  – loaded from disk
GuildConfig: dict[str, dict[str, str]] = {}


# ========================== UTILITIES ===============================


def load_config() -> None:
    global GuildConfig
    if CONFIG_FILE.exists():
        GuildConfig = json.loads(CONFIG_FILE.read_text())
    else:
        GuildConfig = {}


def save_config() -> None:
    CONFIG_FILE.write_text(json.dumps(GuildConfig, indent=2))


def get_guild_phase(guild_id: int) -> str:
    # default to "Pre‑Mech Bosses" if nothing set
    return GuildConfig.get(str(guild_id), {}).get("phase", "Pre‑Mech Bosses")


def set_guild_phase(guild_id: int, phase: str) -> None:
    GuildConfig.setdefault(str(guild_id), {})["phase"] = phase
    save_config()


async def fetch_wikitext(session: aiohttp.ClientSession) -> str:
    """Download raw wikitext for the entire Guide page."""
    params = {
        "action": "parse",
        "page": GUIDE_PAGE,
        "prop": "wikitext",
        "format": "json",
    }
    async with session.get(WIKI_API, params=params) as resp:
        data = await resp.json()
    return data["parse"]["wikitext"]["*"]


ITEM_TEMPLATE_RE = re.compile(r"\{\{\s*[iI]tem\|([^|}]+)")
WIKI_LINK_RE = re.compile(r"\[\[([^|\]]+)[^\]]*\]\]")


def _extract_item_name(line: str) -> str | None:
    """Return a plain item name from a wikitext bullet line."""
    if m := ITEM_TEMPLATE_RE.search(line):
        return m.group(1).strip()
    if m := WIKI_LINK_RE.search(line):
        return m.group(1).strip()
    return None


def parse_guide(wikitext: str) -> dict[str, dict[str, dict[str, list[str]]]]:
    """
    Convert Guide wikitext into a nested dict:
      phase -> class -> category -> [item names]
    """
    result: dict[str, dict[str, dict[str, list[str]]]] = {}
    phase = terraria_class = category = None

    for raw_line in wikitext.splitlines():
        line = raw_line.strip()

        # Phase headings: == Pre-Mech Bosses ==
        if line.startswith("==") and not line.startswith("==="):
            phase = line.strip("= ").replace("&nbsp;", " ").strip()
            result.setdefault(phase, {})
            terraria_class = category = None
            continue

        # Class headings: === Ranged ===
        if line.startswith("==="):
            terraria_class = line.strip("= ").strip()
            if phase:
                result[phase].setdefault(terraria_class, {})
            category = None
            continue

        # Category headings inside a class: ;Weapons
        if line.startswith(";"):
            category = line.lstrip(";").strip()
            if phase and terraria_class:
                result[phase][terraria_class].setdefault(category, [])
            continue

        # Bullet lines with items
        if line.startswith("*") and phase and terraria_class and category:
            name = _extract_item_name(line)
            if name:
                result[phase][terraria_class][category].append(name)

    return result


async def get_guide_data() -> dict[str, dict[str, dict[str, list[str]]]]:
    """Return cached guide data, refreshing if expired."""
    global GuideCache, GuideFetchedAt

    now = asyncio.get_event_loop().time()
    if GuideCache and GuideFetchedAt and now - GuideFetchedAt < CACHE_TTL:
        return GuideCache

    async with aiohttp.ClientSession() as sess:
        text = await fetch_wikitext(sess)

    GuideCache = parse_guide(text)
    GuideFetchedAt = now
    return GuideCache


def wiki_item_link(name: str) -> str:
    url_name = name.replace(" ", "_")
    return f"[{name}](https://terraria.wiki.gg/wiki/{url_name})"


def find_member_class(member: discord.Member) -> str | None:
    """Try to guess the player's class from their roles."""
    for role in member.roles:
        key = role.name.lower()
        if key in ROLE_TO_SECTION:
            return ROLE_TO_SECTION[key]
    return None


# ========================== SLASH COMMANDS ==========================

# ----- /phase ------------
phase_group = app_commands.Group(
    name="phase",
    description="View or change the current progression phase (admin)",
    guild_only=True,
)

tree.add_command(phase_group)


@phase_group.command(name="get", description="Show the current phase for this server")
async def phase_get(inter: discord.Interaction):
    phase = get_guild_phase(inter.guild_id)
    await inter.response.send_message(f"🔎  Current phase: **{phase}**", ephemeral=True)


@phase_group.command(name="set", description="Set the phase (Manage Guild only)")
@app_commands.describe(phase="Exact phase heading as on the wiki (e.g. Pre-Mech Bosses)")
@app_commands.checks.has_permissions(manage_guild=True)
async def phase_set(inter: discord.Interaction, phase: str):
    data = await get_guide_data()

    # fuzzy match phase against known wiki headings
    phases = list(data.keys())
    best, score, _ = process.extractOne(phase, phases, scorer=fuzz.QRatio)
    if score < 60:
        await inter.response.send_message("❌  Phase not recognised. Check spelling.", ephemeral=True)
        return

    set_guild_phase(inter.guild_id, best)
    await inter.response.send_message(f"✅  Phase set to **{best}**")


# ----- /setup ------------
@tree.command(
    name="setup",
    description="Show recommended items for your class (auto‑detects from roles)",
    guild_only=True,
)
@app_commands.describe(terraria_class="Override your class (Ranger / Mage / Summoner / Melee)")
async def setup_cmd(
    inter: discord.Interaction,
    terraria_class: str | None = None,
):
    phase = get_guild_phase(inter.guild_id)
    class_name = terraria_class or find_member_class(inter.user)

    if class_name is None:
        await inter.response.send_message(
            "❌  Could not detect your class. Either:\n"
            "• give yourself a role called Ranger/Mage/Summoner/Melee **or**\n"
            "• supply `/setup terraria_class:<class>`.",
            ephemeral=True,
        )
        return

    guide = await get_guide_data()
    phase_data = guide.get(phase)
    if not phase_data:
        await inter.response.send_message("Phase data missing. Ask an admin to `/phase set` again.", ephemeral=True)
        return

    class_data = phase_data.get(class_name)
    if not class_data:
        await inter.response.send_message(f"No data for **{class_name}** in phase **{phase}**.", ephemeral=True)
        return

    embed = Embed(
        title=f"{phase} – {class_name}",
        colour=0x16a085,
        timestamp=datetime.utcnow(),
    )

    for category, items in class_data.items():
        if not items:
            continue
        value = "\n".join(f"• {wiki_item_link(i)}" for i in items)
        embed.add_field(name=category, value=value, inline=False)

    await inter.response.send_message(embed=embed)


# ----- autocomplete for terraria_class ----------
CLASS_CHOICES = [v for v in {"Ranged", "Mage", "Summoner", "Melee"}]


@setup_cmd.autocomplete("terraria_class")
async def class_autocomplete(_: discord.Interaction, current: str):
    current = current.lower()
    choices = [c for c in CLASS_CHOICES if c.lower().startswith(current)]
    return [app_commands.Choice(name=c, value=c) for c in choices]


# ========================== BOT LIFECYCLE ===========================


@bot.event
async def on_ready():
    load_config()
    await tree.sync()
    print(f"Logged in as {bot.user} ({bot.user.id})")


def main() -> None:
    if not TOKEN:
        raise SystemExit("TOKEN environment variable missing.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
