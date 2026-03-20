import asyncio
import aiohttp
import json
import uuid
import sys
import os

CONFIG_PATH = os.environ.get("JENNIFER_CONFIG", "/app/config/config.json")

def load_token():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f).get("OpenClawToken")
    except FileNotFoundError:
        return None

async def call_rpc(ws_url, api_token, method, params):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(ws_url, headers={"Authorization": f"Bearer {api_token}"}, ssl=False, timeout=15) as ws:
                req_id = str(uuid.uuid4())
                connect_frame = {
                    "type": "req",
                    "id": req_id,
                    "method": "connect",
                    "params": {
                        "minProtocol": 3,
                        "maxProtocol": 3,
                        "client": {
                            "id": "openclaw-gateway-client",
                            "displayName": "config-checker",
                            "version": "1.0.0",
                            "platform": "linux",
                            "mode": "backend"
                        },
                        "role": "operator",
                        "scopes": ["operator.admin", "operator.write", "operator.read"],
                        "auth": { "token": api_token }
                    }
                }
                await ws.send_json(connect_frame)
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "res" and data.get("id") == req_id:
                            if not data.get("ok"):
                                print(f"Connect failed: {data.get('error')}")
                                return
                            break

                method_id = str(uuid.uuid4())
                method_frame = {
                    "type": "req",
                    "id": method_id,
                    "method": method,
                    "params": params
                }
                await ws.send_json(method_frame)
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "res" and data.get("id") == method_id:
                            return data
        except Exception as e:
            print(f"RPC {method} failed: {e}")
            return {"ok": False, "error": str(e)}

async def main():
    gateway_url = "https://vmi3115281.tail36566.ts.net/"
    ws_url = "wss://vmi3115281.tail36566.ts.net/"
    api_token = load_token()
    if not api_token:
        print(f"Error: OpenClawToken not found in {CONFIG_PATH}")
        sys.exit(1)
    
    print("Fetching Gateway config...")
    res = await call_rpc(ws_url, api_token, "config.get", {})
    if res and res.get("ok"):
        config = res.get("payload", {}).get("config", {})
        print(json.dumps(config, indent=2))
    else:
        print(f"Failed to get config: {res}")

if __name__ == "__main__":
    asyncio.run(main())
