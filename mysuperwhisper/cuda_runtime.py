"""
Helpers for locating and preloading CUDA runtime libraries from the venv.
"""

import ctypes
import os


_STATE = {
    "configured": False,
    "library_dirs": [],
    "loaded_libs": [],
    "errors": [],
}


def _namespace_path(module_name):
    try:
        module = __import__(module_name, fromlist=["__path__"])
        return list(module.__path__)[0]
    except Exception:
        return None


def configure_cuda_runtime():
    """
    Preload CUDA libraries shipped as Python packages inside the venv.

    This keeps the CUDA 12 runtime local to the virtualenv instead of relying
    on matching system-wide CUDA user-space libraries.
    """
    if _STATE["configured"]:
        return _STATE

    library_dirs = []
    for module_name in (
        "nvidia.cuda_nvrtc.lib",
        "nvidia.cublas.lib",
        "nvidia.cudnn.lib",
    ):
        path = _namespace_path(module_name)
        if path and os.path.isdir(path):
            library_dirs.append(path)

    if library_dirs:
        current = os.environ.get("LD_LIBRARY_PATH", "")
        current_parts = [part for part in current.split(":") if part]
        merged = []
        for path in library_dirs + current_parts:
            if path not in merged:
                merged.append(path)
        os.environ["LD_LIBRARY_PATH"] = ":".join(merged)

        for lib_name in (
            "libnvrtc.so.12",
            "libcublas.so.12",
            "libcublasLt.so.12",
            "libcudnn.so.9",
        ):
            loaded = False
            for directory in library_dirs:
                candidate = os.path.join(directory, lib_name)
                if not os.path.exists(candidate):
                    continue
                try:
                    ctypes.CDLL(candidate, mode=ctypes.RTLD_GLOBAL)
                    _STATE["loaded_libs"].append(candidate)
                    loaded = True
                    break
                except OSError as exc:
                    _STATE["errors"].append(f"{candidate}: {exc}")
            if not loaded:
                _STATE["errors"].append(f"{lib_name}: not found in venv CUDA runtime paths")

    _STATE["library_dirs"] = library_dirs
    _STATE["configured"] = True
    return _STATE


def get_cuda_runtime_state():
    """Return the CUDA runtime discovery state."""
    return _STATE
