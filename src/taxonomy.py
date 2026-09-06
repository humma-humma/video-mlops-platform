"""Versioned category taxonomy shared by prompts and evaluation."""

TAXONOMY_VERSION = "tiktok-video-v1"

CATEGORIES = (
    "News",
    "Politics",
    "Music, Singing, & Dancing",
    "Comedy",
    "Sports",
    "Film & Animation",
    "Pets & Animals",
    "Entertainment & Shows",
    "Gaming",
    "Science & Technology",
    "Autos & Vehicles",
    "Education",
    "Outfit, Style, & Howto",
    "Nonprofits & Activism",
    "Travel & Events",
    "People & Blogs",
    "Food",
    "Relationship",
    "Family",
    "Beauty Care",
    "Daily Life",
    "Drama",
    "Lipsync",
    "Fitness & Health",
    "Society",
)

CATEGORY_ALIASES = {
    "Entertainment": "Entertainment & Shows",
    "Entertainment and Shows": "Entertainment & Shows",
    "Entertainment, Shows": "Entertainment & Shows",
}


def format_category_options() -> str:
    """Render the canonical taxonomy as numbered prompt options."""
    return "\n".join(
        f"{index}. {category}" for index, category in enumerate(CATEGORIES, start=1)
    )
