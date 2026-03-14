# Jennifer Bot — Regeneration Context
*Last updated: 2026-03-14*

This document is a compact reference for resuming AI-assisted development sessions on Jennifer. Read this first before diving into any code.

---

## What Jennifer Is

Jennifer is a Discord bot that acts as a persistent, persona-driven AI companion. It integrates with:

- **OpenClaw Gateway** — the core AI backend (LLM agent management, chat completions, session/memory persistence)
- **Stable Diffusion** — image generation (supports automatic1111, ComfyUI, InvokeAI backends)
- **Z.AI / FramePack** — video generation
- **Silero TTS / Whisper STT** — voice features
- **model_router** — intelligent model selection/routing based on message content

The bot creates a unique per-user OpenClaw agent for each Discord user it talks to, so each user gets their own persistent memory context.

---

## Deployment Architecture

Jennifer is the **canonical build source** for all three bots. Yennifer and Lauren are just Jennifer containers with different `config/` volumes.

```
Jennifer (docker-compose-jennifer.yml)
  image: idacat411/app:latest
  build: context: .              ← BUILDS the shared image
  volumes: ./config/ → /app/config/

Yennifer (docker-compose-yennifer.yml)
  image: idacat411/app:latest    ← PULLS Jennifer's image, no build
  volumes: ./config/ → /app/config/

Lauren (docker-compose-lauren.yml)
  image: idacat411/app:latest    ← PULLS Jennifer's image, no build
  volumes: ./config/ → /app/config/
```

**What this means:**
- Code changes (e.g., to `utils/openclaw.py`) only need to be made in Jennifer's directory
- After changing code, rebuild and push: `docker compose -f docker-compose-jennifer.yml build && docker push idacat411/app:latest`
- Yennifer and Lauren pick up the new code by pulling: `docker compose pull && docker compose up -d`
- **Only** `config/` is per-bot — all bot-specific config/credentials/identity files live there

## Directory Layout

```
/mnt/stable-diffusion-webui-docker/jennifer/   ← canonical source / build context
├── Dockerfile                    # Builds idacat411/app:latest
├── app.py                        # Main bot entrypoint
├── config/config.json            # Jennifer's live config (never commit credentials)
├── config/jennifer-device-identity.json  # Jennifer's Ed25519 device identity
├── config.json.template          # Template for new deployments
├── core/
│   ├── config.py                 # Pydantic config model (JenniferConfig, OpenClawConfig, etc.)
│   ├── tracing.py                # Internal span tracing
│   ├── persistent_queue.py       # Task queue for async image/video jobs
│   └── logging_config.py
├── bot/
│   ├── client.py                 # Discord client setup
│   └── commands/
│       ├── handlers.py           # All Discord command handlers (!imagine, !recreate, etc.)
│       └── music.py              # Music player commands
├── utils/
│   ├── openclaw.py               # OpenClaw gateway client ← PRIMARY INTEGRATION FILE
│   ├── model_router.py           # Model routing logic
│   ├── image_gen.py              # Image generation dispatch
│   ├── video_gen.py              # Video generation dispatch
│   ├── interactions.py           # Message handling / LLM response loop
│   └── ssl_config.py             # SSL cert management for Tailscale hosts
├── integrations/
│   └── image_generation/         # Backend-specific SD integrations
└── docs/                         # Internal documentation

/mnt/stable-diffusion-webui-docker/lauren2.0/config/   ← Lauren's config volume only
├── config.json                   # Lauren's live config
└── lauren-device-identity.json   # Lauren's Ed25519 device identity

/mnt/stable-diffusion-webui-docker/Yennifer/config/    ← Yennifer's config volume only
├── config.json                   # Yennifer's live config
└── yennifer-device-identity.json # Yennifer's Ed25519 device identity
```

---

## OpenClaw Integration — How It Works

### Normal flow
1. Discord message arrives → `utils/interactions.py` → `utils/openclaw.py:generate_openclaw_response()`
2. `OpenClawClient.send_message()` calls `route_and_update_config()` (model_router) then `ensure_agent_exists()` (creates/verifies per-user agent via RPC), then POSTs to `/v1/chat/completions` with `agent=<agent_id>` and `user=<session_key>`
3. Persona is injected via `inject_system_prompt()` (system message + primer + per-turn re-anchor) to maintain character against gateway bootstrap drift

### Agent lifecycle
- Agent IDs are deterministic: `jennifer-user-<discord_user_id>` (normalized to lowercase alphanumeric + hyphens)
- Session keys: `jennifer:user:<discord_user_id>`
- `!recreate agent` → `delete_openclaw_agent()` + re-create on next message
- `!new session` → `new_session()` which calls `sessions.reset` RPC
- `!model <name>` → `change_openclaw_model()` which calls `sessions.patch` RPC

### RPC over WebSocket
All gateway mutations go through `call_rpc(method, params)` which opens a fresh WebSocket per call, performs a `connect` handshake, then sends the actual method frame. Methods used:
- `connect` — authenticate the WS session
- `config.get` / `config.patch` — read/write gateway config (agent list, model routing)
- `agents.create` / `agents.delete` — agent lifecycle
- `agents.files.set` — write `IDENTITY.md` / `SOUL.md` into agent workspace
- `sessions.reset` / `sessions.patch` — session management

---

## Device Auth for `operator.admin` Scope — COMPLETE

### The problem
`!recreate agent` fails with `missing scope: operator.admin` on the `agents.delete` RPC call.

**Root cause:** Using a shared bearer token on WebSocket. The OpenClaw gateway intentionally strips client-declared scopes from shared-token WS connections — the `scopes` declaration in `connect_params` is ignored unless the connection uses a device token with a signed identity.

### How the fix works
When `OpenClawDeviceToken` and `OpenClawDeviceIdentityPath` are both configured, `call_rpc()` switches to device auth:

1. Connects without `Authorization` header
2. Waits for `connect.challenge` event from gateway (contains `nonce`)
3. Loads device identity JSON from `OpenClawDeviceIdentityPath` (Ed25519 keypair + deviceId)
4. Signs a v3 payload: `v3|<deviceId>|<clientId>|<mode>|<role>|<scopes>|<timestamp>|<token>|<nonce>|<platform>|`
5. Sends signed `device` block + `auth.deviceToken` in the `connect` frame
6. Gateway validates signature → grants declared scopes including `operator.admin`

Signing uses `nacl.signing.SigningKey` (PyNaCl) — **Ed25519**. Fallback: if either config key is empty, old bearer-token path is used silently.

### Provisioning (done 2026-03-14)

Device credentials were generated via Node.js (`crypto.generateKeyPairSync('ed25519')`) and injected directly into the gateway's `paired.json` (gateway reads this file fresh on every auth — no restart needed).

| Bot | Identity file | DeviceId (first 8) |
|-----|--------------|-------------------|
| Jennifer | `jennifer/config/jennifer-device-identity.json` | `750f74ae` |
| lauren2.0 | `lauren2.0/config/lauren-device-identity.json` | `8e345ecb` |
| Yennifer | `Yennifer/config/yennifer-device-identity.json` | `8b7d6187` |

All three devices are registered in `/home/openclaw/.openclaw/devices/paired.json` with scopes `operator.admin`, `operator.write`, `operator.read`.

Config keys populated in each bot's `config/config.json`:
- `OpenClawDeviceToken` — device bearer token (matches the token in `paired.json`)
- `OpenClawDeviceIdentityPath` — absolute path to the identity JSON

### Re-provisioning (if needed)

Run this on the gateway host to regenerate credentials for a bot:

```bash
node -e "
const crypto = require('crypto');
const fs = require('fs');
const ED25519_SPKI_PREFIX = Buffer.from('302a300506032b6570032100', 'hex');
const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
const pub = publicKey.export({type:'spki',format:'pem'}).toString();
const priv = privateKey.export({type:'pkcs8',format:'pem'}).toString();
const raw = publicKey.export({type:'spki',format:'der'}).subarray(ED25519_SPKI_PREFIX.length);
const deviceId = crypto.createHash('sha256').update(raw).digest('hex');
const pubB64 = raw.toString('base64').replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
const token = crypto.randomBytes(32).toString('base64url');
const now = Date.now();
fs.writeFileSync('/path/to/bot-device-identity.json', JSON.stringify({version:1,deviceId,publicKeyPem:pub,privateKeyPem:priv,createdAtMs:now},null,2)+'\n',{mode:0o600});
const paired = JSON.parse(fs.readFileSync('/home/openclaw/.openclaw/devices/paired.json','utf8'));
paired[deviceId]={deviceId,publicKey:pubB64,displayName:'bot-backend',platform:'linux',clientId:'bot-backend',clientMode:'backend',role:'operator',roles:['operator'],scopes:['operator.admin','operator.write','operator.read'],approvedScopes:['operator.admin','operator.write','operator.read'],tokens:{operator:{token,role:'operator',scopes:['operator.admin','operator.write','operator.read'],createdAtMs:now}},createdAtMs:now,approvedAtMs:now};
fs.writeFileSync('/home/openclaw/.openclaw/devices/paired.json',JSON.stringify(paired,null,2)+'\n');
console.log('token:', token, '\ndeviceId:', deviceId);
"
```

Then set `OpenClawDeviceToken` and `OpenClawDeviceIdentityPath` in the bot's `config.json` and restart the bot.

---

## Key Config Keys (OpenClaw)

| Key | Description |
|-----|-------------|
| `OpenClawGateway` | Gateway base URL, e.g. `https://vmi3115281.tail36566.ts.net/` |
| `OpenClawToken` | Shared bearer token (used as fallback / HTTP auth) |
| `OpenClawDeviceToken` | Device-scoped token (for WS device auth — needed for admin ops) |
| `OpenClawDeviceIdentityPath` | Path to Ed25519 identity JSON (see above) |
| `OpenClawmodel` | Default model, e.g. `localai/Qwen3-14B-Nexa-Uncensored` |
| `OpenClawAgent` | Pre-configured agent ID (if not using per-user agents) |
| `OpenClawPersonality` | Persona description injected into system prompt |
| `OpenClawSystemPrompt` | Additional system instructions |
| `OpenClawPrimer` | Static first assistant turn (primes character) |
| `OpenClawModelEndpoint` | LocalAI/OpenAI endpoint URL for `config.patch` routing |

---

## Related Infrastructure

- **OpenClaw gateway source:** `/home/openclaw/openclaw/`
  - Auth logic: `src/gateway/server/ws-connection/message-handler.ts`
  - Method scopes: `src/gateway/method-scopes.ts` (confirms `sessions.delete` requires `operator.admin`)
  - Compat baseline test: `src/gateway/server.auth.compat-baseline.test.ts`
- **OpenClaw live config:** `/home/openclaw/.openclaw/openclaw.json`
- **Gateway service:** `openclaw-gateway.service` (systemd)
- **model-router skill:** `/home/openclaw/model-router/` (live at `~/.openclaw/skills/model-router/`)

---

## Recent Changes (since 2026-03-13)

### OpenClaw gateway (2026-03-13)
- Fixed ACP env-stripping regression: narrowed to bundled/stripped path only
- prompt-defense plugin: gated behind explicit config, fixed session state leak, bounded in-memory map
- Rebuilt and redeployed gateway

### model-router dashboard (2026-03-13)
- Added version display (v2.1.0 + git SHA) to dashboard UI
- **Known issue:** Dashboard SSE socket (`/tmp/dashboard-sse.sock`) fails to bind — sandbox limitation, needs live environment testing

### Device auth for all bots (2026-03-14) — COMPLETE
- `utils/openclaw.py` — full device auth implementation in `call_rpc()`
- `core/config.py` (Jennifer) — `OpenClawConfig` has `device_token` and `device_identity_path` fields
- `config.json.template` — added `OpenClawDeviceToken` and `OpenClawDeviceIdentityPath` keys
- Device identities generated and registered in `/home/openclaw/.openclaw/devices/paired.json`
- All three bot configs populated with device credentials (`OpenClawDeviceToken`, `OpenClawDeviceIdentityPath`)
- Device identity JSON files written to each bot's `config/` directory
- Yennifer and Lauren use `idacat411/app:latest` (Jennifer's image) — no code changes needed in their dirs
- **Status: complete — pull latest image and restart each bot to activate**

---

## Running Jennifer

```bash
cd /mnt/stable-diffusion-webui-docker/jennifer
python app.py
# or via Docker:
docker compose -f docker-compose-jennifer.yml up
```

Tests:
```bash
pytest tests/
```

Syntax check a specific file:
```bash
python -c "import ast; ast.parse(open('utils/openclaw.py').read()); print('OK')"
```
