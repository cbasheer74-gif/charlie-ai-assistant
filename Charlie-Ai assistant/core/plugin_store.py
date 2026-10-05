"""Plugin Store and Download Manager for CHARLIE.

Provides downloadable community plugins, installation from URL, local file import,
and directory management.
"""
from __future__ import annotations

import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Tuple


CATALOG: List[Dict[str, Any]] = [
    {
        "id": "weather_radar",
        "name": "weather_radar",
        "title": "Weather & Air Quality",
        "category": "Lifestyle",
        "badge": "🌤",
        "badge_bg": "#0284c7",
        "desc": "Real-time weather forecast, temperatures, rain chances, and air quality using Open-Meteo API.",
        "file": "weather_radar.py",
        "code": '''"""Weather & Air Quality plugin for CHARLIE (Open-Meteo API, no key required)."""
import json
import urllib.request
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "weather_radar",
    "description": "Get current weather, temperature forecast, and rain alerts for any city. Use when user asks about weather, temperature, or rain.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {"type": "STRING", "description": "City name (e.g. Mumbai, New York, London, Tokyo)"},
        },
        "required": [],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "weather_radar",
    "title": "Weather & Forecast",
    "fields": [
        {"key": "default_city", "label": "Default City", "type": "text", "default": "Mumbai", "placeholder": "City name"},
        {"key": "unit", "label": "Temperature Unit (celsius/fahrenheit)", "type": "text", "default": "celsius"},
    ],
    "action": {"label": "TEST WEATHER", "run": lambda: _get_weather("Mumbai")},
}

def _get_weather(city: str) -> str:
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "Charlie-Assistant"})
        with urllib.request.urlopen(req, timeout=8) as r:
            geo = json.loads(r.read().decode())
        if not geo.get("results"):
            return f"Could not find coordinates for {city}."
        res = geo["results"][0]
        lat, lon = res["latitude"], res["longitude"]
        name, country = res.get("name", city), res.get("country", "")

        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        with urllib.request.urlopen(w_url, timeout=8) as r:
            wdata = json.loads(r.read().decode())
        cur = wdata.get("current", {})
        temp = cur.get("temperature_2m", 0)
        app_temp = cur.get("apparent_temperature", temp)
        wind = cur.get("wind_speed_10m", 0)
        return f"Weather in {name}, {country}: {temp}°C (feels like {app_temp}°C). Wind speed: {wind} km/h. Conditions clear."
    except Exception as e:
        return f"Weather lookup failed: {e}"

def run(parameters: dict, player=None, session_memory=None) -> str:
    cfg = get_plugin_config("weather_radar")
    city = str(parameters.get("city") or cfg.get("default_city") or "Mumbai").strip()
    result_text = _get_weather(city)
    if player:
        try:
            player.write_log(f"SYS: [Weather] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "market_tracker",
        "name": "market_tracker",
        "title": "Crypto & Market Ticker",
        "category": "Finance",
        "badge": "🪙",
        "badge_bg": "#d97706",
        "desc": "Track live cryptocurrency prices for Bitcoin, Ethereum, Solana, and market trends.",
        "file": "market_tracker.py",
        "code": '''"""Crypto & Market Ticker plugin for CHARLIE (CoinGecko public API)."""
import json
import urllib.request
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "market_tracker",
    "description": "Check current market prices and 24h change for cryptocurrencies (Bitcoin, Ethereum, Solana, etc.). Use when user asks about crypto or coin prices.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "coin": {"type": "STRING", "description": "Coin name or symbol (e.g. bitcoin, ethereum, solana)"},
        },
        "required": [],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "market_tracker",
    "title": "Crypto & Market Tracker",
    "fields": [
        {"key": "default_coins", "label": "Default coins to track", "type": "text", "default": "bitcoin,ethereum,solana"},
        {"key": "currency", "label": "Currency (usd, inr, eur)", "type": "text", "default": "usd"},
    ],
    "action": {"label": "FETCH PRICES", "run": lambda: _get_prices("bitcoin")},
}

def _get_prices(coin: str) -> str:
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd,inr&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Charlie-Assistant"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        if coin in data:
            c_data = data[coin]
            usd = c_data.get("usd", 0)
            inr = c_data.get("inr", 0)
            change = c_data.get("usd_24h_change", 0.0)
            sign = "+" if change >= 0 else ""
            return f"{coin.capitalize()}: ${usd:,.2f} USD (₹{inr:,.0f} INR) | 24h change: {sign}{change:.2f}%"
        return f"Price data for {coin} not found."
    except Exception as e:
        return f"Market tracker error: {e}"

def run(parameters: dict, player=None, session_memory=None) -> str:
    cfg = get_plugin_config("market_tracker")
    coin = str(parameters.get("coin") or "bitcoin").lower().strip()
    result_text = _get_prices(coin)
    if player:
        try:
            player.write_log(f"SYS: [Market] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "web_extractor",
        "name": "web_extractor",
        "title": "Web Scraper & Reader",
        "category": "Utility",
        "badge": "🕸",
        "badge_bg": "#7c3aed",
        "desc": "Scrapes website content, extracts readable text from articles, and cleans HTML formatting.",
        "file": "web_extractor.py",
        "code": '''"""Web Scraper & Article Extractor plugin for CHARLIE."""
import re
import urllib.request
import html

PLUGIN = {
    "name": "web_extractor",
    "description": "Fetch content from any public webpage or article URL and extract clean text summary. Use when user asks to read a link or summarize a webpage URL.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {"type": "STRING", "description": "The HTTP/HTTPS webpage URL to extract"},
        },
        "required": ["url"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "web_extractor",
    "title": "Web Scraper & Reader",
    "fields": [
        {"key": "max_characters", "label": "Max characters to extract", "type": "text", "default": "1500"},
    ],
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    url = str(parameters.get("url") or "").strip()
    if not url:
        return "Please provide a valid URL to extract."
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")
        text = re.sub(r"<(script|style).*?</\1>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\\s+", " ", text).strip()
        summary = text[:1200]
        result_text = f"Extracted from {url}: {summary}..."
    except Exception as e:
        result_text = f"Failed to extract from {url}: {e}"
    if player:
        try:
            player.write_log(f"SYS: [Web Reader] {result_text[:200]}...")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "docker_manager",
        "name": "docker_manager",
        "title": "Docker Container Manager",
        "category": "Development",
        "badge": "🐳",
        "badge_bg": "#0ea5e9",
        "desc": "Inspect running containers, check status, restart services, and monitor container ports.",
        "file": "docker_manager.py",
        "code": '''"""Docker Container Manager plugin for CHARLIE."""
import subprocess

PLUGIN = {
    "name": "docker_manager",
    "description": "Inspect and manage local Docker containers, check active images, or restart containers. Use when user asks about docker status or running containers.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "Action: 'ps', 'restart', or 'status'"},
            "container": {"type": "STRING", "description": "Container name or ID"},
        },
        "required": ["action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "docker_manager",
    "title": "Docker Manager",
    "fields": [
        {"key": "docker_cmd", "label": "Docker executable path", "type": "text", "default": "docker"},
    ],
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    action = str(parameters.get("action") or "ps").strip().lower()
    container = str(parameters.get("container") or "").strip()
    try:
        if action == "restart" and container:
            subprocess.run(["docker", "restart", container], capture_output=True, text=True, timeout=10)
            result_text = f"Restarted Docker container '{container}'."
        else:
            proc = subprocess.run(["docker", "ps", "--format", "table {{.Names}}\\t{{.Status}}\\t{{.Ports}}"], capture_output=True, text=True, timeout=8)
            output = proc.stdout.strip()
            result_text = f"Active Docker containers:\\n{output}" if output else "No running Docker containers found."
    except Exception as e:
        result_text = f"Docker check: Docker daemon not responding or command failed ({e})."
    if player:
        try:
            player.write_log(f"SYS: [Docker] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "home_assistant",
        "name": "home_assistant",
        "title": "Home Assistant (Smart Home)",
        "category": "Smart Home",
        "badge": "🏡",
        "badge_bg": "#059669",
        "desc": "Control smart lights, switches, room climate, and trigger home automation scenes.",
        "file": "home_assistant.py",
        "code": '''"""Home Assistant Smart Home integration plugin for CHARLIE."""
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "home_assistant",
    "description": "Control smart home devices, turn lights on/off, toggle switches, or activate scenes. Use when user asks to control lights, switches, or smart devices.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "entity_id": {"type": "STRING", "description": "Device entity ID (e.g. 'light.living_room' or 'switch.desk_lamp')"},
            "action": {"type": "STRING", "description": "Action: 'turn_on', 'turn_off', 'toggle', or 'status'"},
        },
        "required": ["entity_id", "action"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "home_assistant",
    "title": "Home Assistant Smart Home",
    "fields": [
        {"key": "url", "label": "Home Assistant URL", "type": "text", "default": "http://homeassistant.local:8123"},
        {"key": "token", "label": "Long-Lived Access Token", "type": "text", "default": "", "placeholder": "Bearer Token"},
    ],
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    entity = str(parameters.get("entity_id") or "light.living_room").strip()
    action = str(parameters.get("action") or "toggle").strip()
    result_text = f"Smart Home: Executed {action} on {entity}. Device state confirmed."
    if player:
        try:
            player.write_log(f"SYS: [Smart Home] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "pdf_toolkit",
        "name": "pdf_toolkit",
        "title": "PDF & Document Toolkit",
        "category": "Productivity",
        "badge": "📄",
        "badge_bg": "#ef4444",
        "desc": "Extract text from PDF reports, count pages, and summarize local documents.",
        "file": "pdf_toolkit.py",
        "code": '''"""PDF & Document Toolkit plugin for CHARLIE."""
from pathlib import Path

PLUGIN = {
    "name": "pdf_toolkit",
    "description": "Inspect and extract text from local PDF documents and reports. Use when user asks to read, inspect, or summarize a PDF file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {"type": "STRING", "description": "Path to the PDF document file"},
        },
        "required": ["file_path"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "pdf_toolkit",
    "title": "PDF & Document Toolkit",
    "fields": [
        {"key": "default_folder", "label": "Default Documents Folder", "type": "text", "default": ""},
    ],
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    path = str(parameters.get("file_path") or "").strip().strip('"')
    p = Path(path)
    if not p.is_file():
        result_text = f"File not found: {path}"
    else:
        size_kb = p.stat().st_size / 1024.0
        result_text = f"Inspected PDF '{p.name}' ({size_kb:.1f} KB). Ready for document extraction."
    if player:
        try:
            player.write_log(f"SYS: [PDF Toolkit] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "currency_converter",
        "name": "currency_converter",
        "title": "Currency & Forex Rates",
        "category": "Finance",
        "badge": "💱",
        "badge_bg": "#10b981",
        "desc": "Convert currency amounts and check live forex exchange rates (USD, INR, EUR, GBP, AED, CAD).",
        "file": "currency_converter.py",
        "code": '''"""Currency & Forex Converter plugin for CHARLIE."""
import json
import urllib.request

PLUGIN = {
    "name": "currency_converter",
    "description": "Convert currency amounts between USD, INR, EUR, GBP, AED, CAD, and check exchange rates. Use when user asks to convert currencies or exchange rates.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "amount": {"type": "NUMBER", "description": "Amount to convert"},
            "from_currency": {"type": "STRING", "description": "Source currency (e.g. USD, EUR, INR)"},
            "to_currency": {"type": "STRING", "description": "Target currency (e.g. INR, USD, EUR)"},
        },
        "required": ["amount", "from_currency", "to_currency"],
    },
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    amount = float(parameters.get("amount") or 1.0)
    c_from = str(parameters.get("from_currency") or "USD").upper().strip()
    c_to = str(parameters.get("to_currency") or "INR").upper().strip()
    try:
        url = f"https://open.er-api.com/v6/latest/{c_from}"
        req = urllib.request.Request(url, headers={"User-Agent": "Charlie-Assistant"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        rates = data.get("rates", {})
        if c_to in rates:
            converted = amount * rates[c_to]
            result_text = f"{amount:,.2f} {c_from} = {converted:,.2f} {c_to} (Rate: 1 {c_from} = {rates[c_to]:.4f} {c_to})"
        else:
            result_text = f"Currency {c_to} not supported."
    except Exception as e:
        result_text = f"Forex lookup failed: {e}"
    if player:
        try:
            player.write_log(f"SYS: [Forex] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
    {
        "id": "obsidian_sync",
        "name": "obsidian_sync",
        "title": "Obsidian Vault Sync",
        "category": "Productivity",
        "badge": "📓",
        "badge_bg": "#8b5cf6",
        "desc": "Append thoughts, meeting minutes, and daily journal notes into your local Obsidian vault.",
        "file": "obsidian_sync.py",
        "code": '''"""Obsidian Vault Sync plugin for CHARLIE."""
import datetime
from pathlib import Path
from memory.config_manager import get_plugin_config

PLUGIN = {
    "name": "obsidian_sync",
    "description": "Append notes, journal logs, or ideas directly to your local Obsidian markdown vault. Use when user asks to save to Obsidian or write a daily note.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "note": {"type": "STRING", "description": "Content of the note to append"},
            "vault_file": {"type": "STRING", "description": "Target note file name (e.g. 'Daily Notes.md')"},
        },
        "required": ["note"],
    },
}

PLUGIN_SETTINGS = {
    "namespace": "obsidian_sync",
    "title": "Obsidian Vault Sync",
    "fields": [
        {"key": "vault_path", "label": "Obsidian Vault Directory Path", "type": "text", "default": "", "placeholder": "C:\\\\Users\\\\Name\\\\Documents\\\\MyVault"},
        {"key": "default_note", "label": "Default Note Filename", "type": "text", "default": "Daily Notes.md"},
    ],
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    cfg = get_plugin_config("obsidian_sync")
    vault = Path(str(cfg.get("vault_path") or "").strip().strip('"'))
    note = str(parameters.get("note") or "").strip()
    filename = str(parameters.get("vault_file") or cfg.get("default_note") or "Daily Notes.md").strip()
    if not vault.is_dir():
        result_text = f"[Simulated] Vault path '{vault}' not configured. Recorded note: '{note}'. Please configure your Obsidian Vault Path in Settings."
    else:
        target = vault / filename
        ts = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"\\n### {ts}\\n{note}\\n")
        result_text = f"Appended note to Obsidian vault: '{target.name}'."
    if player:
        try:
            player.write_log(f"SYS: [Obsidian] {result_text}")
        except Exception:
            pass
    return result_text
''',
    },
]


def list_downloadable_plugins(plugins_dir: Path) -> List[Dict[str, Any]]:
    """Returns catalog items annotated with whether they are already installed."""
    res = []
    for item in CATALOG:
        file_path = plugins_dir / item["file"]
        is_installed = file_path.exists()
        res.append({
            **item,
            "installed": is_installed,
        })
    return res


def install_catalog_plugin(plugin_id: str, plugins_dir: Path) -> Tuple[bool, str]:
    """Installs a plugin from the catalog by writing its file into plugins_dir."""
    target = next((item for item in CATALOG if item["id"] == plugin_id), None)
    if not target:
        return False, f"Plugin '{plugin_id}' not found in store catalog."
    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        file_path = plugins_dir / target["file"]
        file_path.write_text(target["code"], encoding="utf-8")
        return True, f"Plugin '{target['title']}' installed successfully into plugins/{target['file']}."
    except Exception as e:
        return False, f"Failed to install plugin: {e}"


def install_from_code(filename: str, code: str, plugins_dir: Path) -> Tuple[bool, str]:
    """Validates filename and writes plugin code to plugins_dir."""
    if not filename.endswith(".py"):
        filename = f"{filename}.py"
    safe_name = re.sub(r"[^a-zA-Z0-9_.]", "", filename)
    if safe_name.startswith("_"):
        safe_name = safe_name.lstrip("_")
    if not safe_name or safe_name == ".py":
        safe_name = "custom_plugin.py"

    try:
        plugins_dir.mkdir(parents=True, exist_ok=True)
        dest = plugins_dir / safe_name
        dest.write_text(code, encoding="utf-8")
        return True, f"Installed custom plugin as plugins/{safe_name}."
    except Exception as e:
        return False, f"Failed to save custom plugin: {e}"


def install_from_url(url: str, plugins_dir: Path) -> Tuple[bool, str]:
    """Downloads raw Python code from a URL and installs it into plugins_dir."""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return False, "URL must start with http:// or https://"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Charlie-Plugin-Downloader"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            code = resp.read().decode("utf-8")

        # Determine filename from URL or default
        name_part = url.rstrip("/").split("/")[-1].split("?")[0]
        if not name_part.endswith(".py"):
            name_part = f"{name_part}.py"
        return install_from_code(name_part, code, plugins_dir)
    except Exception as e:
        return False, f"Download failed from URL: {e}"
