"""Comfy Remote."""

__version__ = "0.4.0"

# v0.4 is layered as an explicit runtime integration module so the creation
# policies stay isolated from the v0.3 compatibility core while the beta is
# still supporting existing workflow packages and local databases.
from .v04 import install as _install_v04

_install_v04()
del _install_v04
