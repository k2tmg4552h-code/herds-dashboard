from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import asyncio
import json
import os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_KEY = "D0189A28425D41968A90B820EFB2089F"
TEST_MODE = False 
HISTORY_FILE = "herds_memory.json" 

# --- NEW: THE SCAN LIST ---
# The brain will check Tech, then wait 60 seconds, then check Kitchen, and repeat!
SCAN_LIST = [
    {"name": "tech", "url": "https://www.amazon.com/Best-Sellers-Electronics/zgbs/electronics/"},
    {"name": "kitchen", "url": "https://www.amazon.com/Best-Sellers-Kitchen-Dining/zgbs/kitchen/"}
]

def load_memory():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_memory(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)

@app.get("/")
def get_home():
    with open("index.html", "r") as file:
        return HTMLResponse(content=file.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # This is your Master Record
    master_database = load_memory() 
    scan_index = 0
    
    while True:
        flows = []
        
        # Figure out which category to scan this minute
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
                        reviews = item.get('ratings_total', 100) 
                        name = item.get('title', 'Unknown Product')[:35] + "..." 
                        cat = current_target['name']
                        
                        units_bought = reviews * 35
                        in_carts = int(units_bought * 0.15)
                        gravity_score = (in_carts * 3) + units_bought
                        
                        # Add it to the Master Database!
                        if name not in master_database:
                            master_database[name] = {"category": cat, "history": []}
                            
                        master_database[name]["history"].append(gravity_score)
                        
                        # Keep the last 50 data points
                        if len(master_database[name]["history"]) > 50:
                            master_database[name]["history"].pop(0)

            except Exception as e:
                print(f"Internet error: {e}")

        # Now we package up the entire Master Database to send to the website
        all_items = []
        for name, data in master_database.items():
            history = data["history"]
            if len(history) == 0: continue
            
            current_score = history[-1]
            
            is_spiking = False
            if len(history) >= 2:
                old_score = history[-2]
                jump = ((current_score - old_score) / max(1, old_score)) * 100
                if jump > 10: is_spiking = True
                
            all_items.append({
                "name": name,
                "category": data["category"],
                "score": current_score,
                "history": history,
                "is_spiking": is_spiking,
                "is_heating_up": False # Simplified for the Vault upgrade
            })
            
        # Sort by biggest gravity score
        all_items.sort(key=lambda x: x['score'], reverse=True)
        
        save_memory(master_database)
        await websocket.send_json({"items": all_items, "flows": flows})
        
        # Move to the next category for the next minute
        scan_index += 1
        if scan_index >= len(SCAN_LIST):
            scan_index = 0
            
        await asyncio.sleep(60)