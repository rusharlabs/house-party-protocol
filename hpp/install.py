"""Deterministic installation planning with an explicit local apply step."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class InstallError(ValueError):
    """A bundle cannot be installed under the requested host contract."""


def installation_plan(manifest: dict[str, Any], bundle_name: str, host: str, target: Path) -> dict[str, Any]:
    bundles = manifest["bundles"]
    if bundle_name not in bundles:
        raise InstallError(f"unknown bundle: {bundle_name}")
    if host not in manifest["hosts"]:
        raise InstallError(f"unknown host: {host}")
    bundle = bundles[bundle_name]
    modules = {module["id"]: module for module in manifest["modules"]}
    selected = []
    for module_id in bundle["modules"]:
        coverage = modules[module_id]["hosts"][host]
        if coverage == "unsupported":
            raise InstallError(f"bundle {bundle_name} requires {module_id}, unsupported on {host}")
        selected.append({"id": module_id, "integration": coverage})
    return {
        "protocol_version": manifest["protocol_version"], "bundle": bundle_name, "host": host,
        "target": str(target.resolve()), "mode": "plan-only", "modules": selected,
        "instructions": ["Install the selected modules through their host distribution channel.",
                         "Keep this receipt with the workspace for later doctor/status checks."],
    }
