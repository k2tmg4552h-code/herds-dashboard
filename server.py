from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import asyncio
import json
import os

app = FastAPI()

# This allows your website to talk to the Python brain without security blocks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONFIGURATION ---
API_KEY = "D0189A28425D41968A90B820EFB2089F"
TEST_MODE = False 
HISTORY_FILE = "herds_memory.json" 

# Focused on 2 categories for testing as requested
SCAN_LIST = [
    {"name": "tech", "url": "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"},
    {"name": "kitchen", "url": "https://www.amazon.com/Best-Sellers-Kitchen-Dining/zgbs/kitchen/"}
]

def load_memory():
    """Loads the Master Log from the hard drive"""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_memory(data):
    """Saves the Master Log to the hard drive"""
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)

@app.get("/")
def get_home():
    with open("index.html", "r") as file:
        return HTMLResponse(content=file.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Load past history so we never lose a record
    master_database = load_memory() 
    scan_index = 0
    
    while True:
        current_target = SCAN_LIST[scan_index]
        print(f"Scanning Amazon for: {current_target['name']}...")
        
        if not TEST_MODE:
            params = {
              'api_key': API_KEY,
              'type': 'bestsellers',
              'url': current_target['url']
            }
            
            try:
                response = requests.get('https://api.rainforestapi.com/request', params=params)
                real_api_data = response.json()
                
                if 'bestsellers' in real_api_data:
                    for item in real_api_data['bestsellers'][:15]: 
                        full_name = item.get('title', 'Unknown Product')
                        # Create a shorter name for the map UI
                        short_name = full_name[:30] + "..." if len(full_name) > 30 else full_name
                        
                        reviews = item.get('ratings_total', 100) 
                        cat = current_target['name']
                        
                        # Math to calculate the "Gravity Score"
                        units_bought = reviews * 35
                        in_carts = int(units_bought * 0.15)
                        gravity_score = (in_carts * 3) + units_bought
                        
                        # Store in the Master Database
                        if short_name not in master_database:
                            master_database[short_name] = {
                                "full_name": full_name, 
                                "category": cat, 
                                "history": []
                            }
                            
                        master_database[short_name]["history"].append(gravity_score)
                        
                        # Keep the last 50 data points for the trend chart
                        if len(master_database[short_name]["history"]) > 50:
                            master_database[short_name]["history"].pop(0)

            except Exception as e:
                print(f"Internet error: {e}")

        # Package the database into a list for the website
        all_items = []
        for name, data in master_database.items():
            history = data.get("history", [])
            if not history: continue
            
            current_score = history[-1]
            
            # Detect if the score is jumping fast
            is_spiking = False
            if len(history) >= 2:
                old_score = history[-2]
                jump = ((current_score - old_score) / max(1, old_score)) * 100
                if jump > 10:
                    is_spiking = True
            
            all_items.append({
                "name": name,
                "full_name": data.get("full_name", name),
                "score": current_score,
                "category": data["category"],
                "history": history,
                "is_spiking": is_spiking
            })
            
        # Sort by most popular
        all_items.sort(key=lambda x: x['score'], reverse=True)
        
        # Save to hard drive and send to website
        save_memory(master_database)
        await websocket.send_json({"items": all_items})
        
        # Rotate categories: Tech -> Kitchen -> Tech...
        scan_index = (scan_index + 1) % len(SCAN_LIST)
        
        # Wait 60 seconds before next scan
        await asyncio.sleep(60)
