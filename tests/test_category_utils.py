from src.category_utils import is_canonical_category, normalize_category


def test_normalize_category_removes_numbered_prefixes() -> None:
    assert normalize_category("7. Pets & Animals") == "Pets & Animals"
    assert normalize_category("15) Travel & Events") == "Travel & Events"
    assert normalize_category("2: Politics") == "Politics"


def test_normalize_category_trims_trailing_period() -> None:
    assert normalize_category("Travel & Events.") == "Travel & Events"


def test_normalize_category_is_case_insensitive_and_applies_known_aliases() -> None:
    assert normalize_category("travel & events") == "Travel & Events"
    assert normalize_category("Entertainment and Shows") == "Entertainment & Shows"


def test_is_canonical_category_rejects_ambiguous_legacy_labels() -> None:
    assert is_canonical_category("Politics")
    assert not is_canonical_category("News, Politics")
    assert not is_canonical_category("Business")
