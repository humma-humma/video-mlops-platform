from src.taxonomy import CATEGORIES, format_category_options


def test_taxonomy_has_unique_categories() -> None:
    assert len(CATEGORIES) == len(set(CATEGORIES))


def test_prompt_options_are_generated_from_taxonomy() -> None:
    lines = format_category_options().splitlines()

    assert len(lines) == len(CATEGORIES)
    assert lines[0] == "1. News"
    assert lines[-1] == f"{len(CATEGORIES)}. Society"
