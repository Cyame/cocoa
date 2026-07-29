"""Agent runtime subpackage (P11c — k8s_adapter + legacy module bridge)."""

import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path

_pkg_root = _Path(__file__).resolve().parent.parent
_legacy_path = _pkg_root / "agent_runtime.py"
_spec = _ilu.spec_from_file_location("app._agent_runtime_legacy", _legacy_path)
_legacy = _ilu.module_from_spec(_spec) if _spec else None
if _legacy is not None and _spec is not None:
    _sys.modules["app._agent_runtime_legacy"] = _legacy
    _spec.loader.exec_module(_legacy)
    start_runtime_for = _legacy.start_runtime_for
    run_agent_loop = getattr(_legacy, "run_agent_loop", None)
    del _ilu, _sys, _Path, _pkg_root, _legacy_path, _spec, _legacy
else:
    def start_runtime_for(instance_id: str) -> None:  # pragma: no cover
        raise RuntimeError("legacy agent_runtime module missing")

    run_agent_loop = None  # type: ignore[assignment]
    del _ilu, _sys, _Path, _pkg_root, _legacy_path, _spec

__all__ = ["start_runtime_for", "run_agent_loop"]
