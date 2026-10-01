"""
Helpers for locating and preloading CUDA runtime libraries from the venv.
"""

import ctypes
import os
from pathlib import Path
import sys


_STATE = {
    "configured": False,
    "library_dirs": [],
    "loaded_libs": [],
    "errors": [],
}


def _site_package_roots():
    """Return site-packages paths for this venv, preferring the active Python."""
    lib_root = Path(sys.prefix) / "lib"
    active = lib_root / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    roots = [active]
    roots.extend(sorted(lib_root.glob("python*/site-packages"), reverse=True))

    unique_roots = []
    for root in roots:
        if root.is_dir() and root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def _cuda_library_dirs():
    """Find CUDA package library directories in any Python version of this venv."""
    package_paths = (
        Path("nvidia/cuda_nvrtc/lib"),
        Path("nvidia/cublas/lib"),
        Path("nvidia/cudnn/lib"),
    )
    library_dirs = []
    for site_packages in _site_package_roots():
        for package_path in package_paths:
            path = site_packages / package_path
            if path.is_dir() and str(path) not in library_dirs:
                library_dirs.append(str(path))
    return library_dirs


def configure_cuda_runtime():
    """
    Preload CUDA libraries shipped as Python packages inside the venv.

    The venv may survive a Python minor-version upgrade. CUDA shared libraries
    are not Python extensions, so package libraries in an older venv
    site-packages directory can still be loaded by the active interpreter.
    """
    if _STATE["configured"]:
        return _STATE

    library_dirs = _cuda_library_dirs()
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
