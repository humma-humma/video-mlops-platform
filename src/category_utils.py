import re

from src.taxonomy import CATEGORIES, CATEGORY_ALIASES


_CATEGORY_PREFIX_RE = re.compile(r"^\s*\d+\s*[\).:-]\s*")
_CATEGORY_LOOKUP = {category.casefold(): category for category in CATEGORIES}
_CATEGORY_LOOKUP.update(
    {alias.casefold(): category for alias, category in CATEGORY_ALIASES.items()}
)


def normalize_category(value: object) -> str:
    """Normalize model category text for comparison with ground truth labels."""
    text = str(value).strip()
    text = _CATEGORY_PREFIX_RE.sub("", text)
    text = text.strip().rstrip(".").strip()
    return _CATEGORY_LOOKUP.get(text.casefold(), text)


def is_canonical_category(value: object) -> bool:
    """Return whether a normalized value belongs to the versioned taxonomy."""
    return normalize_category(value) in CATEGORIES
