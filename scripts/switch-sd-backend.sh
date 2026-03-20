#!/bin/bash
# =============================================================================
# Switch Stable Diffusion Backend Script
# =============================================================================
# 
# Usage:
#   ./switch-sd-backend.sh [backend] [gpu-type]
#
# Arguments:
#   backend   - a1111, comfyui, invokeai
#   gpu-type  - nvidia, cpu (default: nvidia)
#
# Examples:
#   ./switch-sd-backend.sh comfyui nvidia    # Switch to ComfyUI with GPU
#   ./switch-sd-backend.sh a1111 cpu         # Switch to A1111 CPU-only
#   ./switch-sd-backend.sh invokeai nvidia   # Switch to InvokeAI with GPU
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
BACKEND=${1:-comfyui}
GPU_TYPE=${2:-nvidia}

# Validate backend
if [[ ! "$BACKEND" =~ ^(a1111|comfyui|invokeai)$ ]]; then
    echo -e "${RED}Error: Invalid backend '$BACKEND'${NC}"
    echo "Valid options: a1111, comfyui, invokeai"
    exit 1
fi

# Validate GPU type
if [[ ! "$GPU_TYPE" =~ ^(nvidia|cpu)$ ]]; then
    echo -e "${RED}Error: Invalid GPU type '$GPU_TYPE'${NC}"
    echo "Valid options: nvidia, cpu"
    exit 1
fi

# Construct profile name
PROFILE="sd-${BACKEND}-${GPU_TYPE}"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}  Switching Stable Diffusion Backend${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""
echo -e "  Backend:  ${GREEN}${BACKEND}${NC}"
echo -e "  GPU Type: ${GREEN}${GPU_TYPE}${NC}"
echo -e "  Profile:  ${GREEN}${PROFILE}${NC}"
echo ""

# Stop existing SD containers
echo -e "${YELLOW}→ Stopping existing SD containers...${NC}"
docker-compose -f docker-compose-jennifer.yml stop sd-a1111-nvidia sd-a1111-cpu sd-comfyui-nvidia sd-comfyui-cpu sd-invokeai-nvidia sd-invokeai-cpu 2>/dev/null || true

# Update config.json
echo -e "${YELLOW}→ Updating config.json...${NC}"
CONFIG_FILE="config/config.json"

if [ -f "$CONFIG_FILE" ]; then
    case $BACKEND in
        a1111)
            SD_URL="http://localhost:7860"
            SD_BACKEND="automatic1111"
            ;;
        comfyui)
            SD_URL="http://localhost:7860"
            SD_BACKEND="comfyui"
            ;;
        invokeai)
            SD_URL="http://localhost:7860"
            SD_BACKEND="invokeai"
            ;;
    esac
    
    # Use Python to update config
    python3 << EOF
import json

with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)

config['SDBackend'] = '$SD_BACKEND'
config['SDURL'] = '$SD_URL'

with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=4)

print(f"Updated SDBackend to: {config['SDBackend']}")
print(f"Updated SDURL to: {config['SDURL']}")
EOF
else
    echo -e "${YELLOW}Warning: config.json not found at $CONFIG_FILE${NC}"
fi

# Start new backend
echo -e "${YELLOW}→ Starting ${BACKEND} (${GPU_TYPE})...${NC}"
docker-compose -f docker-compose-jennifer.yml --profile ${PROFILE} up -d sd-${BACKEND}-${GPU_TYPE}

# Wait for health check
echo -e "${YELLOW}→ Waiting for service to be healthy...${NC}"
sleep 5

# Check health
HEALTH_URL=""
case $BACKEND in
    a1111)
        HEALTH_URL="http://localhost:7860/sdapi/v1/memory"
        ;;
    comfyui)
        HEALTH_URL="http://localhost:8188/system_stats"
        ;;
    invokeai)
        HEALTH_URL="http://localhost:9090/api/v1/app/config"
        ;;
esac

if [ -n "$HEALTH_URL" ]; then
    for i in {1..30}; do
        if curl -s "$HEALTH_URL" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Service is healthy!${NC}"
            break
        fi
        echo -n "."
        sleep 2
    done
fi

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  Backend switched successfully!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  You can now use the !draw command with ${BACKEND}"
echo ""
echo "  Logs: docker logs -f jennifer-sd-${BACKEND}-${GPU_TYPE}"
echo ""
