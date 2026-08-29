"""Comfy Remote."""

__version__ = "0.4.0"

# v0.4 is layered as explicit runtime integration modules so the creation
# policies stay isolated from the v0.3 compatibility core while the beta is
# still supporting existing workflow packages and local databases.
from .v04 import install as _install_v04
from .v04_overrides import install as _install_v04_overrides
from .v04_compat import install as _install_v04_compat
from .v04_cache import install as _install_v04_cache

_install_v04()
_install_v04_overrides()
_install_v04_compat()
_install_v04_cache()
del _install_v04, _install_v04_overrides, _install_v04_compat, _install_v04_cache
