#!/bin/bash
#
# Setup shared directories for Jennifer image generation backends.
# Creates the required directory structure for sharing models and outputs
# between Automatic1111, ComfyUI, and InvokeAI backends.
#
# Usage: bash setup_shared_dirs.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GRAY='\033[0;37m'
NC='\033[0m' # No Color

# Get the project root (scripts is in jennifer/scripts, so go up 2 levels)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
DATA_DIR="$PROJECT_ROOT/data"
OUTPUT_DIR="$PROJECT_ROOT/output"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Shared Directories Setup for Jennifer${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Define required directories
declare -a REQUIRED_DIRS=(
    # Core model directories (shared)
    "$DATA_DIR/models/Stable-diffusion"
    "$DATA_DIR/models/VAE"
    "$DATA_DIR/models/Lora"
    "$DATA_DIR/models/ControlNet"
    "$DATA_DIR/models/ESRGAN"
    "$DATA_DIR/models/hypernetworks"
    "$DATA_DIR/embeddings"
    
    # Backend-specific app data
    "$DATA_DIR/comfyui"
    "$DATA_DIR/comfyui/custom_nodes"
    "$DATA_DIR/invokeai"
    
    # Shared output
    "$OUTPUT_DIR"
    "$OUTPUT_DIR/txt2img"
    "$OUTPUT_DIR/img2img"
    "$OUTPUT_DIR/saved"
    
    # Config
    "$DATA_DIR/config"
    "$PROJECT_ROOT/config/sd-webui"
)

echo -e "${YELLOW}Creating required directories...${NC}"
echo ""

CREATED_COUNT=0
EXISTING_COUNT=0

for DIR in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$DIR" ]; then
        echo -e "${GRAY}  [EXISTS] $DIR${NC}"
        ((EXISTING_COUNT++))
    else
        if mkdir -p "$DIR" 2>/dev/null; then
            echo -e "${GREEN}  [CREATE] $DIR${NC}"
            ((CREATED_COUNT++))
        else
            echo -e "${RED}  [ERROR]  $DIR${NC}"
        fi
    fi
done

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}Summary:${NC}"
echo -e "  ${GREEN}Created:   $CREATED_COUNT directories${NC}"
echo -e "  ${GRAY}Existing:  $EXISTING_COUNT directories${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Set permissions (Linux/Mac only)
if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}Setting permissions...${NC}"
    chmod -R 755 "$DATA_DIR/models" 2>/dev/null || true
    chmod -R 755 "$OUTPUT_DIR" 2>/dev/null || true
    echo -e "${GREEN}Permissions set${NC}"
    echo ""
fi

# Verify critical paths
echo -e "${YELLOW}Verifying critical paths...${NC}"
echo ""

declare -A CRITICAL_PATHS=(
    ["Models (Stable-diffusion)"]="$DATA_DIR/models/Stable-diffusion"
    ["Models (VAE)"]="$DATA_DIR/models/VAE"
    ["Models (Lora)"]="$DATA_DIR/models/Lora"
    ["Output"]="$OUTPUT_DIR"
    ["ComfyUI Data"]="$DATA_DIR/comfyui"
    ["InvokeAI Data"]="$DATA_DIR/invokeai"
)

ALL_GOOD=true
for NAME in "${!CRITICAL_PATHS[@]}"; do
    PATH="${CRITICAL_PATHS[$NAME]}"
    if [ -d "$PATH" ]; then
        echo -e "${GREEN}  [OK] $NAME -> $PATH${NC}"
    else
        echo -e "${RED}  [MISSING] $NAME -> $PATH${NC}"
        ALL_GOOD=false
    fi
done

echo ""
if [ "$ALL_GOOD" = true ]; then
    echo -e "${GREEN}All critical directories are ready!${NC}"
else
    echo -e "${RED}Some directories are missing. Please check errors above.${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}Next steps:${NC}"
echo -e "  ${WHITE}1. Place your model files in: $DATA_DIR/models/${NC}"
echo -e "  ${WHITE}2. Start the desired backend with:${NC}"
echo -e "     ${YELLOW}docker compose --profile nvidia up -d${NC}"
echo -e "     ${YELLOW}docker compose --profile comfyui-nvidia up -d${NC}"
echo -e "     ${YELLOW}docker compose --profile invokeai-nvidia up -d${NC}"
echo ""
