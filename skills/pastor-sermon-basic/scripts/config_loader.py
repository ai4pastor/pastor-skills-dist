#!/usr/bin/env python3
"""Shared config contract for pastor-sermon-import.

Single source of truth:
- format: JSON
- default home: ~/.pastor-sermon-import/  (override: PASTOR_SERMON_IMPORT_HOME)
- default path: <home>/config.json
- optional vault-local path: <vault>/.vault-sermon-import/config.json

Paths are resolved through home()/config_path()/work_dir() rather than module
constants so that an isolated test environment can redirect them with one
environment variable. With the variable unset the behaviour is unchanged.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import re
from typing import Any

HOME_ENV_VAR = "PASTOR_SERMON_IMPORT_HOME"
DEFAULT_HOME = "~/.pastor-sermon-import"

REQUIRED_TOP_LEVEL = {"vault", "input", "output", "naming", "classification", "bible", "safety"}


def home() -> Path:
    """Base directory for config and work files."""
    return Path(os.environ.get(HOME_ENV_VAR) or DEFAULT_HOME).expanduser()


def work_dir() -> Path:
    """Directory for LLM hand-off files (fragments.json, word.json)."""
    return home() / "work"


def default_config() -> dict[str, Any]:
    """The contract. Allow-lists stay empty here on purpose.

    A preset (data/word_preset.a4p.json) may fill classification.*_values, but
    only after the pastor picks it during onboarding. Shipping anyone's personal
    taxonomy as a default is what the empty lists guard against, and
    tests/pastor-sermon-import/ asserts they stay empty.
    """
    return {
        "version": 2,
        "vault": {"path": ""},
        "input": {"sermon_sources": [], "file_types": ["docx", "md", "txt"]},
        "output": {"main_sermon_folder": "", "fragment_folder": "", "log_folder": ".vault-sermon-import/logs"},
        "naming": {
            "main_note_pattern": "{date}_{title}_{main_passage}.md",
            "fragment_note_pattern": "{sermon_id}_{title}.md",
            "date_from_filename": True,
            "target_from_folder": True,
            "collision_policy": "ask",
            "fragment_collision_policy": "skip",
            "target_markers": [],
            "folder_to_target": {},
            "folder_number_prefix_strip": True,
        },
        "classification": {
            "use_word": False,
            "world_values": [],
            "outcome_values": [],
            "route_values": [],
            "doctrine_values": [],
            "allow_unknown_doctrine": False,
            "route_scalar": False,
            "single_world": False,
            "require_value_prefix": {},
            "wrap_values_in_wikilink": False,
            "fragment_world": "",
            "preset": "",
        },
        "bible": {
            "link_style": "[[{normalized}]]",
            "range_policy": "expand_each_verse",
            "max_range_expand": 50,
            "note_folder": "",
            "book_aliases": {},
            "frontmatter_key": "성경구절",
        },
        "safety": {
            "dry_run_first": True,
            "overwrite_existing": False,
            "require_approval_before_write": True,
            "preserve_original_files": True,
        },
    }


def config_path(vault_path: str | None = None) -> Path:
    if vault_path:
        candidate = Path(vault_path).expanduser() / ".vault-sermon-import" / "config.json"
        if candidate.exists():
            return candidate
    return home() / "config.json"


def merge_defaults(user: dict[str, Any], defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fill missing keys from the defaults, recursively.

    This is what lets a config written by an older version load unchanged: new
    keys arrive with their defaults instead of raising KeyError, so no migration
    step is needed when the contract grows.
    """
    out = dict(default_config() if defaults is None else defaults)
    for key, value in (user or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_defaults(value, out[key])
        else:
            out[key] = value
    return out


def load_config(path: str | Path | None = None, vault_path: str | None = None) -> dict[str, Any]:
    p = Path(path).expanduser() if path else config_path(vault_path)
    data = merge_defaults(json.loads(p.read_text(encoding="utf-8")))
    validate_config(data)
    return data


def save_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    validate_config(config)
    p = Path(path).expanduser() if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def validate_config(config: dict[str, Any]) -> None:
    missing = REQUIRED_TOP_LEVEL - set(config)
    if missing:
        raise ValueError(f"config missing top-level keys: {', '.join(sorted(missing))}")
    if config["safety"].get("overwrite_existing") is True:
        raise ValueError("unsafe config: safety.overwrite_existing must be false by default")
    if config["safety"].get("preserve_original_files") is not True:
        raise ValueError("unsafe config: safety.preserve_original_files must be true")
    # These two used to be declarative only. Enforcing them keeps the config from
    # promising a safety property the pastor does not actually get.
    if config["safety"].get("dry_run_first", True) is not True:
        raise ValueError("unsafe config: safety.dry_run_first must be true")
    if config["safety"].get("require_approval_before_write", True) is not True:
        raise ValueError("unsafe config: safety.require_approval_before_write must be true")
    if not isinstance(config["input"].get("sermon_sources"), list):
        raise ValueError("input.sermon_sources must be a list")

    naming = config["naming"]
    if naming.get("collision_policy", "ask") not in {"ask", "skip"}:
        raise ValueError("naming.collision_policy must be 'ask' or 'skip'")
    if naming.get("fragment_collision_policy", "skip") not in {"ask", "skip", "merge"}:
        raise ValueError("naming.fragment_collision_policy must be 'ask', 'skip', or 'merge'")
    if not isinstance(naming.get("target_markers", []), list):
        raise ValueError("naming.target_markers must be a list")
    if not isinstance(naming.get("folder_to_target", {}), dict):
        raise ValueError("naming.folder_to_target must be an object")
    if not isinstance(config["classification"].get("require_value_prefix", {}), dict):
        raise ValueError("classification.require_value_prefix must be an object")
    if config["classification"].get("use_word"):
        for key in ("world_values", "outcome_values", "route_values", "doctrine_values"):
            if not isinstance(config["classification"].get(key), list):
                raise ValueError(f"classification.{key} must be a list")
    allowed_placeholders = {"{normalized}", "{book}", "{chapter}", "{verse}"}
    style = config["bible"].get("link_style", "")
    if "{normalized}" not in style:
        # Other placeholders may be supported later, but normalized is the safe MVP contract.
        raise ValueError("bible.link_style must include {normalized}")
    unknown_placeholders = set("{" + name + "}" for name in re.findall(r"\{([^{}]+)\}", style)) - allowed_placeholders
    if unknown_placeholders:
        raise ValueError(f"unsupported bible.link_style placeholders: {', '.join(sorted(unknown_placeholders))}")


if __name__ == "__main__":
    import sys
    cfg = load_config(sys.argv[1]) if len(sys.argv) > 1 else default_config()
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
