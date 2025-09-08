
"""
version_utils.py
----------------
Utility module for retrieving the installed version of Python packages.

Functions:
- `get_installed_version(package_name: str) -> str`:
    Returns the currently installed version of the specified package, 
    using `importlib.metadata` for compatibility with modern Python packaging.

Use Case:
Primarily used in the ADE → Snowflake pipeline to record the version 
of `agentic-doc` used for each document parse, ensuring reproducibility 
and traceability in downstream data.

"""

from importlib import import_module
from importlib.metadata import version as _get_version, PackageNotFoundError

def get_installed_version(pkg_name: str, default: str = "unknown") -> str:
    """
    Returns the installed version of a package, or 'unknown' if not found.

    Attempts both:
      1. importlib.metadata.version()
      2. getattr(module, '__version__', ...)

    Handles both dash-named and underscore-named modules.
    """
    try:
        return _get_version(pkg_name)
    except PackageNotFoundError:
        try:
            mod = import_module(pkg_name.replace("-", "_"))
            return getattr(mod, "__version__", default)
        except Exception:
            return default