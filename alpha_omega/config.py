#!/usr/bin/env python3
"""config.py — per-project configuration for Alpha-Omega.

Reads .alpha-omega/config.json if present.
CLI flags override config. Config overrides defaults.

Python 3.9 compatible.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("ao.config")

DEFAULTS = {
    "alpha_model": "claude-sonnet-4-5",
    "alpha_timeout": 300,
    "alpha_max_turns": 3,
    "omega_timeout": 600,
    "review_timeout": 180,
    "implement_timeout": 900,
    "implement_max_turns": 6,
}


def load_config(project_dir=None):
    """Load config from .alpha-omega/config.json, merged with defaults.

    Returns dict with all keys from DEFAULTS, overridden by config file values.
    """
    config = dict(DEFAULTS)

    if project_dir is None:
        project_dir = os.getcwd()

    config_file = os.path.join(project_dir, ".alpha-omega", "config.json")
    if os.path.isfile(config_file):
        try:
            with open(config_file, encoding="utf-8") as f:
                user_config = json.load(f)
            if isinstance(user_config, dict):
                for key in DEFAULTS:
                    if key in user_config:
                        config[key] = user_config[key]
                log.debug("Loaded config from %s", config_file)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read config %s: %s", config_file, exc)

    return config


def save_default_config(project_dir):
    """Save default config.json to .alpha-omega/."""
    config_file = os.path.join(project_dir, ".alpha-omega", "config.json")
    if os.path.isfile(config_file):
        return False  # don't overwrite

    ao_dir = os.path.join(project_dir, ".alpha-omega")
    if not os.path.isdir(ao_dir):
        return False

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, indent=2)
        f.write("\n")

    return True
