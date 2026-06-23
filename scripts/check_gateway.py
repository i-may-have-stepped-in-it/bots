import asyncio
import json

from utils.openclaw import OpenClawClient


async def check():
    config_path = "./config/config.json"
    with open(config_path) as f:
        config = json.load(f)

    gateway_url = config.get("OpenClawGateway")
    api_token = config.get("OpenClawToken")
    client = OpenClawClient(gateway_url, api_token)

    print("Fetching Gateway Config...")
    res = await client.call_rpc("config.get", {})
    if res.get("ok"):
        payload = res.get("payload", {}).get("config", {})
        print(f"Global Primary Model: {payload.get('models', {}).get('primary')}")
        print(f"LocalAI BaseURL: {payload.get('models', {}).get('providers', {}).get('localai', {}).get('baseUrl')}")

        agents = payload.get("agents", {}).get("list", [])
        user_agent = next((a for a in agents if a.get("id") == "jennifer-user-401695424827883530"), None)
        print(f"User Agent Config: {json.dumps(user_agent, indent=2)}")

        print("\nFetching Models List...")
        m_res = await client.call_rpc("models.list", {})
        if m_res.get("ok"):
            models = m_res.get("payload", {}).get("models", [])
            print(f"Total Models: {len(models)}")
            qwen = next((m for m in models if "qwen" in m.get("id", "").lower()), None)
            print(f"Qwen match: {json.dumps(qwen, indent=2)}")
            kimi = next((m for m in models if "kimi" in m.get("id", "").lower()), None)
            print(f"Kimi match: {json.dumps(kimi, indent=2)}")

        # Also check session state
        print("\nFetching Session Entry...")
        s_res = await client.call_rpc("sessions.list", {})
        if s_res.get("ok"):
            sessions = s_res.get("payload", {}).get("sessions", [])
            user_session = next((s for s in sessions if s.get("key") == "jennifer:user:401695424827883530"), None)
            print(f"User Session: {json.dumps(user_session, indent=2)}")
    else:
        print(f"Failed to fetch config: {res}")

if __name__ == "__main__":
    asyncio.run(check())
