"""Comfy Remote."""

__version__ = "0.4.4"

# v0.4 is layered as explicit runtime integration modules so the creation
# policies stay isolated from the v0.3 compatibility core while the beta is
# still supporting existing workflow packages and local databases.
from .v04 import install as _install_v04
from .v04_overrides import install as _install_v04_overrides
from .v04_compat import install as _install_v04_compat
from .v04_cache import install as _install_v04_cache
from .recovery_lite import install as _install_recovery_lite
from .recovery_debounce import install as _install_recovery_debounce
from .v041 import install as _install_v041
from .v041_frontend import install as _install_v041_frontend
from .v042 import install as _install_v042
from .v042_frontend import install as _install_v042_frontend
from .v043 import install as _install_v043

_install_v04()
_install_v04_overrides()
_install_v04_compat()
_install_v04_cache()
_install_recovery_lite()
_install_recovery_debounce()
_install_v041()
_install_v041_frontend()
_install_v042()
_install_v042_frontend()
_install_v043()
del (
    _install_v04,
    _install_v04_overrides,
    _install_v04_compat,
    _install_v04_cache,
    _install_recovery_lite,
    _install_recovery_debounce,
    _install_v041,
    _install_v041_frontend,
    _install_v042,
    _install_v042_frontend,
    _install_v043,
)
