"""Compatibility shims so ComfyUI-3D-Pack's older bundled modules import under the
megapak's newer libraries (transformers 5.x, diffusers 0.38).

Imported as the first line of ComfyUI-3D-Pack/__init__.py (wired by pre-start.sh).
Each shim patches the *canonical* sys.modules object as the final step, because the
lazy module machinery can swap object identity during submodule import.
"""
import sys
import importlib

# --- transformers: CLIPFeatureExtractor was renamed to CLIPImageProcessor and removed
#     from the top-level namespace in v5 (used by 3D-Pack's Era3D pipeline). ---
try:
    import transformers  # noqa: F401
    from transformers.models.clip import CLIPImageProcessor as _CIP
    _t = sys.modules["transformers"]
    if not hasattr(_t, "CLIPFeatureExtractor"):
        _t.CLIPFeatureExtractor = _CIP
except Exception as e:  # pragma: no cover
    print("[comfy3d_compat] transformers shim skipped:", e, file=sys.stderr)

# --- diffusers: models.controlnet moved under models.controlnets (>=0.30); 3D-Pack's
#     Stable3DGen/stablex imports `from diffusers.models.controlnet import ControlNetOutput`. ---
try:
    try:
        import diffusers.models.controlnet  # noqa: F401
    except ImportError:
        _cn = importlib.import_module("diffusers.models.controlnets.controlnet")
        sys.modules["diffusers.models.controlnet"] = _cn
except Exception as e:  # pragma: no cover
    print("[comfy3d_compat] diffusers controlnet shim skipped:", e, file=sys.stderr)
