"""Profile loading and validation from YAML files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from device_use.core.models import DeviceProfile

# Built-in profiles ship alongside the package
BUILTIN_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def load_profile(name_or_path: str | Path) -> DeviceProfile:
    """Load a device profile by name or file path.

    Lookup order:
    1. If path exists and is .yaml/.yml, load directly.
    2. Search built-in profiles directory by stem name.
    3. Search built-in profiles directory by substring match.

    Raises:
        FileNotFoundError: If no matching profile is found.
        pydantic.ValidationError: If YAML doesn't match DeviceProfile schema.
    """
    path = Path(name_or_path)

    # Direct file path
    if path.exists() and path.suffix in (".yaml", ".yml"):
        return _load_from_file(path)

    # Search built-in profiles by exact stem
    name = str(name_or_path)
    for yaml_file in BUILTIN_PROFILES_DIR.rglob("*.yaml"):
        if yaml_file.stem == name:
            return _load_from_file(yaml_file)

    # Substring match (e.g., "fiji" matches "imagej-fiji.yaml")
    for yaml_file in BUILTIN_PROFILES_DIR.rglob("*.yaml"):
        if name.lower() in yaml_file.stem.lower():
            return _load_from_file(yaml_file)

    raise FileNotFoundError(
        f"Profile not found: {name_or_path}. "
        f"Available profiles: {[p['name'] for p in list_profiles()]}"
    )


def _load_from_file(path: Path) -> DeviceProfile:
    """Load and validate a single YAML profile file."""
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Profile YAML must be a mapping, got {type(data).__name__}")
    return DeviceProfile(**data)


def list_profiles(profiles_dir: Path | None = None) -> list[dict[str, Any]]:
    """List all available built-in profiles.

    Returns:
        List of dicts with name, path, software, hardware_connected.
    """
    search_dir = profiles_dir or BUILTIN_PROFILES_DIR
    if not search_dir.exists():
        return []

    profiles = []
    for yaml_file in sorted(search_dir.rglob("*.yaml")):
        try:
            profile = _load_from_file(yaml_file)
            profiles.append({
                "name": profile.name,
                "path": str(yaml_file),
                "software": profile.software,
                "hardware_connected": profile.hardware_connected,
            })
        except Exception:
            continue
    return profiles


def validate_profile(data: dict[str, Any]) -> DeviceProfile:
    """Validate a raw dict against the DeviceProfile schema."""
    return DeviceProfile(**data)
