import json
import os
from typing import Dict

# Supported languages and their full names
SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "pt-BR": "Português (Brasil)",
    "es": "Español",
}

# Discord locale → our internal code
DISCORD_LOCALE_MAP: Dict[str, str] = {
    "en-US": "en",
    "en-GB": "en",
    "pt-BR": "pt-BR",
    "es-ES": "es",
    "es-419": "es",
}

# Module-level translation cache — loaded once at import time
_translations: Dict[str, Dict[str, str]] = {}


def _load_translations() -> None:
    locales_dir = os.path.join(os.path.dirname(__file__), "..", "locales")
    for code in SUPPORTED_LANGUAGES:
        path = os.path.join(locales_dir, f"{code}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                _translations[code] = json.load(f)
        except FileNotFoundError:
            _translations[code] = {}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """Translates a key into the given language with optional format args.
    Falls back to English if key is missing. Falls back to key name if all else fails.
    """
    if not _translations:
        _load_translations()

    text = _translations.get(lang, {}).get(key)
    if text is None:
        text = _translations.get("en", {}).get(key, key)

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text

    return text


def resolve_language(discord_locale: str = "en-US", preferred_language: str | None = None) -> str:
    """Resolves the final language code following priority: preferred > discord locale > fallback."""
    if preferred_language and preferred_language in SUPPORTED_LANGUAGES:
        return preferred_language
    mapped = DISCORD_LOCALE_MAP.get(discord_locale, None)
    if mapped and mapped in SUPPORTED_LANGUAGES:
        return mapped
    return "en"


# Pre-load at import time so the first bot interaction is instant
_load_translations()
