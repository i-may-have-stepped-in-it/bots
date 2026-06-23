#!/usr/bin/env bash
# =============================================================================
# pre-start.sh — sourced by the yanwk entrypoint before ComfyUI launches.
# Handles the bits that depend on the runtime bind-mounted custom_nodes source
# (so they cannot be baked into the image): node-local compiled extensions and
# the 3D-Pack compat-shim import. Idempotent — each block is a no-op once done.
# =============================================================================
set +e
NODES=/root/ComfyUI/custom_nodes
export CUDA_HOME=/usr/local/cuda-13.0
export TORCH_CUDA_ARCH_LIST=12.0
export FORCE_CUDA=1
export PIP_ROOT_USER_ACTION=ignore
PIP="python3.13 -m pip install --no-build-isolation --no-input --no-cache-dir"

echo "[pre-start] 3D-node setup..."

# --- Ensure ComfyUI-3D-Pack loads the transformers/diffusers compat shim first. ---
DP="$NODES/ComfyUI-3D-Pack/__init__.py"
if [ -f "$DP" ] && ! grep -q "import comfy3d_compat" "$DP"; then
  echo "[pre-start] wiring comfy3d_compat into ComfyUI-3D-Pack/__init__.py"
  sed -i '1i import comfy3d_compat  # transformers-5 / diffusers compat shim (auto-added)' "$DP"
fi

# --- SPAR3D: uv_unwrapper (CPU) + texture_baker (CUDA sm_120). HARD import deps. ---
if [ -d "$NODES/stable-point-aware-3d" ]; then
  python3.13 -c "import uv_unwrapper, texture_baker" 2>/dev/null || {
    echo "[pre-start] building SPAR3D extensions (uv_unwrapper + texture_baker)..."
    ( cd "$NODES/stable-point-aware-3d" && $PIP --no-deps ./uv_unwrapper/ && $PIP --no-deps ./texture_baker/ )
  }
fi

# --- Hunyuan3D-2.1: custom_rasterizer (CUDA) + DifferentiableRenderer (C++). ---
# Optional: only needed for the texture-painting runtime path; the node imports without them.
if [ -d "$NODES/ComfyUI-Hunyuan3d-2-1/hy3dpaint/custom_rasterizer" ]; then
  python3.13 -c "import custom_rasterizer" 2>/dev/null || {
    echo "[pre-start] building Hunyuan3D custom_rasterizer..."
    ( cd "$NODES/ComfyUI-Hunyuan3d-2-1/hy3dpaint/custom_rasterizer" && $PIP -e . )
  }
fi
# DifferentiableRenderer: both the standalone node and 3D-Pack's bundled Hunyuan copy
# need the compiled mesh_inpaint_processor (else they fall back to a slow Python path).
for DR in \
  "$NODES/ComfyUI-Hunyuan3d-2-1/hy3dpaint/DifferentiableRenderer" \
  "$NODES/ComfyUI-3D-Pack/Gen_3D_Modules/Hunyuan3D_2_1/hy3dpaint/DifferentiableRenderer"; do
  if [ -f "$DR/mesh_inpaint_processor.cpp" ] && ! ls "$DR"/mesh_inpaint_processor*.so >/dev/null 2>&1; then
    echo "[pre-start] building mesh_inpaint_processor in $DR ..."
    ( cd "$DR" && c++ -O3 -Wall -shared -std=c++11 -fPIC \
        $(python3.13 -m pybind11 --includes) mesh_inpaint_processor.cpp \
        -o mesh_inpaint_processor$(python3.13-config --extension-suffix) )
  fi
done

echo "[pre-start] done."
set -e
