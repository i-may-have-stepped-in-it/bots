# =============================================================================
# Custom ComfyUI image for the jennifer stack — bakes the dependencies for six
# heavy 3D custom nodes on top of yanwk's CUDA-13 megapak.
#   Base: Rocky Linux 10.2, Python 3.13, torch 2.11.0+cu130, nvcc 13.0,
#         flash-attn + sageattention prebuilt for Blackwell (RTX 5080, sm_120).
#   Nodes: SPAR3D, Hunyuan3D-2.1, TRELLIS2, UniRig, geometrypack, ComfyUI-3D-Pack.
#
# NOTE: the live deployment image was produced by `docker commit` of a fully
# verified discovery container (identical recipe, guaranteed-working state).
# This Dockerfile is the reproducible recipe — `docker build` it for a clean
# image. The CUDA source builds make a fresh build take ~35-45 min.
#
# Verified on 2026-06-22: all 6 nodes import (1071 total nodes, 97 from 3D-Pack).
# =============================================================================
FROM yanwk/comfyui-boot:cu130-megapak-pt211

ENV PIP_ROOT_USER_ACTION=ignore \
    CUDA_HOME=/usr/local/cuda-13.0 \
    FORCE_CUDA=1 \
    TORCH_CUDA_ARCH_LIST=12.0
SHELL ["/bin/bash", "-c"]
ARG PIP="python3.13 -m pip install --no-cache-dir --no-input"

# ---------------------------------------------------------------------------
# 1. System libraries
#    libglvnd-opengl -> libOpenGL.so.0 for pymeshlab's GL filter plugins (Hunyuan3D)
# ---------------------------------------------------------------------------
RUN dnf install -y libglvnd-opengl libglvnd-glx && dnf clean all

# ---------------------------------------------------------------------------
# 2. Pure-python / wheel deps (no compilation)
# ---------------------------------------------------------------------------
# SPAR3D: jaxtyping/loralib are import-time deps; transparent-background + CLIP/AlphaCLIP
# are runtime (image conditioning) — installed --no-deps to protect the env's torch/numpy
# /transformers (the node's numpy==1.26.4 / transformers==4.42.3 pins have no cp313 wheels
# and the node runs fine on numpy 2 / transformers 5).
RUN $PIP jaxtyping loralib ftfy regex && \
    $PIP --no-deps transparent-background && \
    $PIP --no-deps "git+https://github.com/openai/CLIP.git" "git+https://github.com/SunzeY/AlphaCLIP.git"

# Hunyuan3D-2.1 (open3d omitted: no cp313 wheel; its optional InPaint feature degrades).
RUN $PIP pymeshlab meshlib xatlas pygltflib configargparse pytorch-lightning \
         accelerate scikit-image timm opencv-python-headless spandrel imageio

# comfy-env trio (TRELLIS2 / UniRig / geometrypack). comfy-env 0.4.3 imports in-process
# (system torch) so nodes register WITHOUT install.py/pixi. libigl is required by UniRig.
RUN $PIP comfy-env comfy-3d-viewers comfy-sparse-attn "trimesh[easy]" libigl

# ComfyUI-3D-Pack pure-python / wheel deps (incl. spconv/cumm cu126 wheels that import on cu130).
RUN $PIP pyhocon easydict iopath plyfile fast-simplification PyMCubes torchtyping \
         nerfacc==0.5.3 slangtorch gsplat torchmetrics pytorch_msssim peft open_clip_torch \
         gpytoolbox lpips roma pymeshfix python-igraph webdataset pyvista mmgp \
         plotly "pynanoinstantmeshes==0.0.3" \
         cumm-cu126==0.7.11 spconv-cu126==2.3.8 && \
    $PIP "git+https://github.com/EasternJournalist/utils3d.git" "git+https://github.com/ashawkey/kiuikit.git"

# ---------------------------------------------------------------------------
# 3. CUDA source builds for sm_120 (each --no-build-isolation against the base torch)
#    These are the heavy steps (pytorch3d ~15 min). Kept as separate layers for caching.
# ---------------------------------------------------------------------------
RUN $PIP --no-build-isolation "git+https://github.com/NVlabs/nvdiffrast.git"
RUN $PIP --no-build-isolation torch_scatter
RUN $PIP --no-build-isolation "git+https://github.com/facebookresearch/pytorch3d.git"
RUN $PIP --no-build-isolation "git+https://github.com/ashawkey/diff-gaussian-rasterization.git"
RUN $PIP --no-build-isolation "git+https://github.com/camenduru/simple-knn.git"
RUN $PIP --no-build-isolation "git+https://github.com/SarahWeiii/diso.git"
# pointnet2_ops: upstream setup.py hardcodes pre-Volta arches that CUDA 13 dropped
# (nvcc fatal: Unsupported gpu architecture 'compute_37'); patch the arch list to modern + sm_120.
RUN cd /tmp && git clone --depth 1 https://github.com/erikwijmans/Pointnet2_PyTorch.git && \
    cd Pointnet2_PyTorch/pointnet2_ops_lib && \
    sed -i -E 's/(os\.environ\[.TORCH_CUDA_ARCH_LIST.\][[:space:]]*=[[:space:]]*).*/\1"8.0;8.6;9.0;12.0"/' setup.py && \
    $PIP --no-build-isolation . && cd / && rm -rf /tmp/Pointnet2_PyTorch

# ---------------------------------------------------------------------------
# 4. Compatibility shim — lets 3D-Pack's older bundled modules import under
#    transformers 5.x / diffusers 0.38 (CLIPFeatureExtractor rename, controlnet move).
#    Loaded via the import prepended to 3D-Pack's __init__.py (done by pre-start.sh).
# ---------------------------------------------------------------------------
COPY comfy3d_compat.py /usr/local/lib/python3.13/site-packages/comfy3d_compat.py

# ---------------------------------------------------------------------------
# 5. Node-local extension builder + node patches (sourced at container start;
#    these depend on the runtime-bind-mounted custom_nodes source).
# ---------------------------------------------------------------------------
COPY pre-start.sh /root/user-scripts/pre-start.sh
RUN chmod +x /root/user-scripts/pre-start.sh
