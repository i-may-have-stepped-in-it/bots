"""
OpenClaw Device Registration

Handles first-run device identity generation and gateway pairing.
Called from app.py before Discord login.

Flow:
  1. If no identity file → generate Ed25519 keypair, write identity file
  2. If no device token → connect to gateway to trigger/await pairing
     - Local gateway (localhost): silent auto-pairing, succeeds immediately
     - Remote gateway: waits for admin to run `claude code devices approve`
  3. Once paired → call device.token.rotate → write token back to config.json
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path

import aiohttp
from nacl.signing import SigningKey

logger = logging.getLogger(__name__)

# How long to wait between retry attempts when waiting for remote approval
RETRY_INTERVAL_S = 10
# Max time to wait for remote approval before giving up and continuing without device auth
APPROVAL_TIMEOUT_S = 300


# ---------------------------------------------------------------------------
# Key generation helpers
# ---------------------------------------------------------------------------

def _der_to_pem(der: bytes, label: str) -> str:
    b64 = base64.b64encode(der).decode("ascii")
    lines = [f"-----BEGIN {label}-----"]
    for i in range(0, len(b64), 64):
        lines.append(b64[i:i + 64])
    lines.append(f"-----END {label}-----")
    return "\n".join(lines) + "\n"


def _ed25519_private_key_to_pkcs8_pem(seed_bytes: bytes) -> str:
    """Encode 32-byte Ed25519 seed as PKCS8 PEM (matches _private_key_pem_to_seed decoder)."""
    oid = bytes([0x06, 0x03, 0x2b, 0x65, 0x70])
    alg_id = bytes([0x30, 0x05]) + oid
    inner_octet = bytes([0x04, 0x20]) + seed_bytes
    outer_octet = bytes([0x04, 0x22]) + inner_octet
    version = bytes([0x02, 0x01, 0x00])
    inner = version + alg_id + outer_octet
    der = bytes([0x30, len(inner)]) + inner
    return _der_to_pem(der, "PRIVATE KEY")


def _ed25519_public_key_to_spki_pem(pub_bytes: bytes) -> str:
    """Encode 32-byte Ed25519 public key as SubjectPublicKeyInfo PEM (matches _public_key_pem_to_base64url decoder)."""
    oid = bytes([0x06, 0x03, 0x2b, 0x65, 0x70])
    alg_id = bytes([0x30, 0x05]) + oid
    bit_string = bytes([0x03, 0x21, 0x00]) + pub_bytes
    inner = alg_id + bit_string
    der = bytes([0x30, len(inner)]) + inner
    return _der_to_pem(der, "PUBLIC KEY")


def generate_device_identity() -> dict:
    """Generate a new Ed25519 device identity."""
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    seed_bytes = bytes(signing_key)
    pub_bytes = bytes(verify_key)
    device_id = hashlib.sha256(pub_bytes).hexdigest()
    return {
        "deviceId": device_id,
        "publicKeyPem": _ed25519_public_key_to_spki_pem(pub_bytes),
        "privateKeyPem": _ed25519_private_key_to_pkcs8_pem(seed_bytes),
        "createdAt": int(time.time() * 1000),
    }


# ---------------------------------------------------------------------------
# Gateway connection helpers
# ---------------------------------------------------------------------------

def _ws_url(gateway_url: str) -> str:
    return gateway_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _public_key_pem_to_base64url(pem: str) -> str:
    lines = [l.strip() for l in pem.splitlines() if l.strip() and "BEGIN" not in l and "END" not in l]
    der = base64.b64decode("".join(lines))
    raw = der[-32:]
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _private_key_pem_to_seed(pem: str) -> bytes:
    lines = [l.strip() for l in pem.splitlines() if l.strip() and "BEGIN" not in l and "END" not in l]
    der = base64.b64decode("".join(lines))
    return der[-32:]


def _build_signed_device(identity: dict, *, nonce: str, device_token: str,
                          client_id: str, client_mode: str, role: str, scopes: list) -> dict:
    pub_b64 = _public_key_pem_to_base64url(identity["publicKeyPem"])
    derived_id = hashlib.sha256(_decode_base64url(pub_b64)).hexdigest()
    if derived_id != identity["deviceId"]:
        raise RuntimeError("Device identity public key does not match deviceId")

    signed_at_ms = int(time.time() * 1000)
    payload = "|".join([
        "v3", identity["deviceId"], client_id, client_mode, role,
        ",".join(scopes), str(signed_at_ms), device_token or "", nonce, "linux", "",
    ])
    seed = _private_key_pem_to_seed(identity["privateKeyPem"])
    sig = SigningKey(seed).sign(payload.encode("utf-8")).signature
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return {
        "id": identity["deviceId"],
        "publicKey": pub_b64,
        "signature": sig_b64,
        "signedAt": signed_at_ms,
        "nonce": nonce,
    }


async def _try_pair_and_rotate(gateway_url: str, api_token: str, identity: dict,
                                device_token: str) -> tuple[str | None, str | None]:
    """
    Attempt one WebSocket connect cycle.
    Returns (token, None) on success, (None, requestId) if pairing required, (None, None) on other error.
    """
    ws_url = _ws_url(gateway_url)
    scopes = ["operator.admin", "operator.write", "operator.read"]
    try:
        ssl_ctx = None
        if ws_url.startswith("wss://"):
            import ssl as ssl_module
            ssl_ctx = ssl_module.create_default_context()

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url, ssl=ssl_ctx, timeout=aiohttp.ClientTimeout(total=30)) as ws:
                # Wait for challenge
                challenge_nonce = None
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "event" and data.get("event") == "connect.challenge":
                            challenge_nonce = (data.get("payload") or {}).get("nonce", "").strip()
                            if challenge_nonce:
                                break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        return None, None

                if not challenge_nonce:
                    logger.warning("Device registration: no challenge nonce received")
                    return None, None

                # Build connect frame
                req_id = str(uuid.uuid4())
                connect_frame = {
                    "type": "req",
                    "id": req_id,
                    "method": "connect",
                    "params": {
                        "minProtocol": 3,
                        "maxProtocol": 3,
                        "client": {
                            "id": "gateway-client",
                            "displayName": "bot-device-registration",
                            "version": "1.0.0",
                            "platform": "linux",
                            "mode": "backend",
                        },
                        "role": "operator",
                        "scopes": scopes,
                        "auth": {"deviceToken": device_token or api_token},
                        "device": _build_signed_device(
                            identity, nonce=challenge_nonce,
                            device_token=device_token or api_token,
                            client_id="gateway-client", client_mode="backend",
                            role="operator", scopes=scopes,
                        ),
                    },
                }
                await ws.send_json(connect_frame)

                # Wait for connect response
                connect_ok = False
                pair_request_id = None
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "res" and data.get("id") == req_id:
                            if data.get("ok"):
                                connect_ok = True
                            else:
                                err = data.get("error") or {}
                                details = err.get("details") or {}
                                pair_request_id = details.get("requestId")
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

                if not connect_ok:
                    return None, pair_request_id

                # Connected — rotate device token
                rotate_id = str(uuid.uuid4())
                rotate_frame = {
                    "type": "req",
                    "id": rotate_id,
                    "method": "device.token.rotate",
                    "params": {
                        "deviceId": identity["deviceId"],
                        "role": "operator",
                        "scopes": scopes,
                    },
                }
                await ws.send_json(rotate_frame)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "res" and data.get("id") == rotate_id:
                            if data.get("ok"):
                                token = (data.get("result") or {}).get("token")
                                return token, None
                            else:
                                logger.warning(f"device.token.rotate failed: {data.get('error')}")
                                return None, None
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break

    except Exception as e:
        logger.debug(f"Device registration connect attempt failed: {e}")

    return None, None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def ensure_device_registered(config_path: str) -> None:
    """
    Ensure this bot instance has a registered device identity and token.
    Reads and writes config_path in place.
    No-op if OpenClawDeviceToken and identity file are already configured.
    """
    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    gateway_url = raw.get("OpenClawGateway", "").strip()
    api_token = raw.get("OpenClawToken", "").strip()
    device_token = raw.get("OpenClawDeviceToken", "").strip()
    identity_path = raw.get("OpenClawDeviceIdentityPath", "").strip()

    if not gateway_url or not api_token:
        logger.info("Device registration skipped: OpenClawGateway or OpenClawToken not configured")
        return

    # Determine default identity path if not set
    if not identity_path:
        bot_name = raw.get("Name", "bot").lower().replace(" ", "-")
        identity_path = f"/app/config/{bot_name}-device-identity.json"
        raw["OpenClawDeviceIdentityPath"] = identity_path
        logger.info(f"OpenClawDeviceIdentityPath not set, using default: {identity_path}")

    # Step 1: ensure identity file exists
    identity_file = Path(identity_path)
    if not identity_file.exists():
        logger.info(f"Generating new device identity → {identity_path}")
        identity_file.parent.mkdir(parents=True, exist_ok=True)
        identity = generate_device_identity()
        with open(identity_path, "w", encoding="utf-8") as f:
            json.dump(identity, f, indent=2)
        logger.info(f"Device identity created: deviceId={identity['deviceId']}")
    else:
        with open(identity_path, encoding="utf-8") as f:
            identity = json.load(f)
        logger.debug(f"Loaded existing device identity: deviceId={identity['deviceId']}")

    # Step 2: if token already present, nothing to do
    if device_token:
        logger.debug("OpenClawDeviceToken already configured, skipping registration")
        return

    logger.info(f"No device token — initiating gateway pairing for deviceId={identity['deviceId']}")

    # Detect local vs remote gateway
    import urllib.parse
    parsed = urllib.parse.urlparse(gateway_url)
    is_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")

    deadline = time.monotonic() + APPROVAL_TIMEOUT_S
    pair_request_id = None
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        token, request_id = await _try_pair_and_rotate(gateway_url, api_token, identity, device_token)

        if token:
            logger.info(f"Device registered and token obtained (attempt {attempt})")
            raw["OpenClawDeviceToken"] = token
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=4)
            logger.info("config.json updated with OpenClawDeviceToken")
            return

        if request_id and request_id != pair_request_id:
            pair_request_id = request_id
            if is_local:
                logger.warning(
                    f"Pairing required (local — should auto-approve). requestId={request_id}. "
                    "If this persists, approve manually: claude code devices approve"
                )
            else:
                logger.warning(
                    f"Gateway pairing approval required. Run on the gateway host:\n"
                    f"  claude code devices approve\n"
                    f"  (requestId: {request_id})\n"
                    f"Retrying every {RETRY_INTERVAL_S}s for up to {APPROVAL_TIMEOUT_S}s..."
                )

        await asyncio.sleep(RETRY_INTERVAL_S)

    logger.warning(
        f"Device registration timed out after {APPROVAL_TIMEOUT_S}s. "
        "Bot will start without device auth — set OpenClawDeviceToken manually after approving the pairing request."
    )
