from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
import uuid
from datetime import datetime
import random
import asyncio

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory database (replace with Supabase later)
players = {}
dungeon_sessions = {}
leaderboard = []
trading_posts = []

# Models
class Player(BaseModel):
    id: str
    username: str
    level: int = 1
    hp: int = 100
    max_hp: int = 100
    exp: int = 0
    gold: int = 0
    weapon: str = "basic_sword"
    abilities: List[str] = ["slash", "spin"]
    trophies: List[Dict] = []
    position: str = "village"

class DungeonSession(BaseModel):
    id: str
    players: List[str]
    dungeon_type: str
    current_floor: int = 1
    enemies: List[Dict] = []
    start_time: datetime

class TradingPost(BaseModel):
    id: str
    seller: str
    item_type: str
    item_name: str
    price: int
    created_at: datetime

# API Routes
@app.get("/")
async def root():
    return {"message": "Bleed Online API", "status": "alive"}

@app.post("/api/register")
async def register(username: str):
    player_id = str(uuid.uuid4())
    players[player_id] = Player(
        id=player_id,
        username=username
    ).dict()
    return {"player_id": player_id, "player": players[player_id]}

@app.get("/api/player/{player_id}")
async def get_player(player_id: str):
    if player_id not in players:
        raise HTTPException(404, "Player not found")
    return players[player_id]

@app.post("/api/combat")
async def combat(player_id: str, enemy_type: str, damage_dealt: int):
    if player_id not in players:
        raise HTTPException(404, "Player not found")
    
    player = players[player_id]
    
    # Simple enemy stats
    enemies = {
        "goblin": {"hp": 30, "exp": 20, "gold": 10, "damage": 8},
        "wolf": {"hp": 45, "exp": 30, "gold": 15, "damage": 12},
        "ogre": {"hp": 80, "exp": 50, "gold": 25, "damage": 18},
        "skeleton": {"hp": 40, "exp": 25, "gold": 12, "damage": 10},
        "demon": {"hp": 120, "exp": 100, "gold": 50, "damage": 25}
    }
    
    enemy = enemies.get(enemy_type, enemies["goblin"])
    
    # Calculate enemy damage to player
    player_damage = random.randint(5, damage_dealt)
    enemy_damage = random.randint(5, enemy["damage"])
    
    player["hp"] -= enemy_damage
    
    # Enemy defeated
    if enemy_damage >= enemy["hp"]:
        player["exp"] += enemy["exp"]
        player["gold"] += enemy["gold"]
        
        # Level up
        if player["exp"] >= player["level"] * 100:
            player["level"] += 1
            player["max_hp"] += 20
            player["hp"] = player["max_hp"]
            
            # New ability at level 3 and 5
            if player["level"] == 3 and "heal" not in player["abilities"]:
                player["abilities"].append("heal")
            if player["level"] == 5 and "rage" not in player["abilities"]:
                player["abilities"].append("rage")
        
        # Random trophy drop
        if random.random() > 0.7:
            trophy = {
                "name": f"{enemy_type}_trophy",
                "enemy": enemy_type,
                "earned_at": datetime.now().isoformat()
            }
            player["trophies"].append(trophy)
    
    return {
        "player_hp": player["hp"],
        "enemy_hp": max(0, enemy["hp"] - enemy_damage),
        "exp_gained": enemy["exp"] if enemy_damage >= enemy["hp"] else 0,
        "gold_gained": enemy["gold"] if enemy_damage >= enemy["hp"] else 0,
        "player_damage_taken": enemy_damage,
        "enemy_defeated": enemy_damage >= enemy["hp"]
    }

@app.post("/api/dungeon/create")
async def create_dungeon(player_id: str, dungeon_type: str):
    dungeon_id = str(uuid.uuid4())
    
    # Generate enemies for dungeon
    enemies = []
    for floor in range(1, 4):
        floor_enemies = []
        for _ in range(random.randint(2, 4)):
            enemy_types = ["goblin", "wolf", "skeleton"]
            floor_enemies.append({
                "type": random.choice(enemy_types),
                "hp": random.randint(30, 50),
                "floor": floor
            })
        enemies.append(floor_enemies)
    
    dungeon_sessions[dungeon_id] = DungeonSession(
        id=dungeon_id,
        players=[player_id],
        dungeon_type=dungeon_type,
        enemies=enemies,
        start_time=datetime.now()
    ).dict()
    
    return {"dungeon_id": dungeon_id, "enemies": enemies}

@app.post("/api/dungeon/join")
async def join_dungeon(dungeon_id: str, player_id: str):
    if dungeon_id not in dungeon_sessions:
        raise HTTPException(404, "Dungeon not found")
    
    dungeon = dungeon_sessions[dungeon_id]
    if len(dungeon["players"]) >= 3:
        raise HTTPException(400, "Dungeon is full")
    
    dungeon["players"].append(player_id)
    return {"dungeon": dungeon}

@app.get("/api/leaderboard")
async def get_leaderboard():
    sorted_players = sorted(
        [p for p in players.values()],
        key=lambda x: (x["level"], x["exp"]),
        reverse=True
    )[:10]
    
    return [{"username": p["username"], "level": p["level"], "exp": p["exp"]} 
            for p in sorted_players]

@app.post("/api/trading/post")
async def create_trading_post(seller: str, item_type: str, item_name: str, price: int):
    post = TradingPost(
        id=str(uuid.uuid4()),
        seller=seller,
        item_type=item_type,
        item_name=item_name,
        price=price,
        created_at=datetime.now()
    ).dict()
    
    trading_posts.append(post)
    return post

@app.get("/api/trading/listings")
async def get_listings():
    return trading_posts[-20:]  # Last 20 listings

# WebSocket for real-time co-op
@app.websocket("/ws/dungeon/{dungeon_id}")
async def websocket_endpoint(websocket: WebSocket, dungeon_id: str):
    await websocket.accept()
    
    if dungeon_id not in dungeon_sessions:
        await websocket.close()
        return
    
    dungeon = dungeon_sessions[dungeon_id]
    
    try:
        while True:
            data = await websocket.receive_text()
            
            if data.startswith("attack:"):
                # Broadcast attack to all players in dungeon
                enemy_index = int(data.split(":")[1])
                damage = int(data.split(":")[2])
                
                # Update enemy HP
                floor = dungeon["current_floor"] - 1
                if floor < len(dungeon["enemies"]):
                    enemy = dungeon["enemies"][floor][enemy_index]
                    enemy["hp"] -= damage
                    
                    # Enemy defeated
                    if enemy["hp"] <= 0:
                        dungeon["enemies"][floor].pop(enemy_index)
                        
                        # Next floor if all enemies defeated
                        if len(dungeon["enemies"][floor]) == 0:
                            dungeon["current_floor"] += 1
                            
                            if dungeon["current_floor"] > 3:
                                await websocket.send_text("boss:final")
                            else:
                                await websocket.send_text(f"floor:{dungeon['current_floor']}")
                
                # Broadcast to all connected clients
                await websocket.send_text(f"update:{enemy_index}:{enemy['hp']}")
            
            elif data == "leave":
                break
                
    except:
        pass
    finally:
        # Remove player from dungeon
        if dungeon_id in dungeon_sessions:
            dungeon = dungeon_sessions[dungeon_id]
            # Don't delete dungeon if other players are still in it
            if len(dungeon["players"]) == 1:
                del dungeon_sessions[dungeon_id]
