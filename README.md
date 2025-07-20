# Terrabot — Terraria Class‑Setup Discord Bot

A **zero‑cost, self‑hostable** Discord bot that lets your friends
instantly look up the best gear for their current progression phase in **Terraria**.

<div align="center">

| ![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg) | ![discord.py](https://img.shields.io/badge/discord.py-2.5-lightgrey) | ![License](https://img.shields.io/badge/License-MIT-green) |
|:--:|:--:|:--:|

</div>

---

## ✨  Features

|                     | What it does |
|---------------------|--------------|
| **Live presets**    | Scrapes the official *Guide:Class_setups* page and caches the gear lists (weapons, armour, accessories, buffs). |
| **Phase tracking**  | Admins run `/phase set <phase>` once (e.g. *Pre‑Mech Bosses*); the bot remembers it per‑server. |
| **Role auto‑detect**| Players with roles **Ranger / Mage / Summoner / Melee** just type `/setup` and instantly see their list. |
| **Slash commands**  | `/setup`, `/phase get`, `/phase set` (Manage Guild only). |
| **Wiki links**      | Every item is a clickable link to the Terraria wiki. |
| **Docker‑ready**    | One `docker run -e TOKEN=… terrabot` and you’re online. |

---

## 🚀  Quick start (no Docker)

```bash
git clone https://github.com/YourUser/terrabot.git
cd terrabot
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
set TOKEN=YOUR_BOT_TOKEN        # PowerShell: $env:TOKEN="…"
python bot.py
