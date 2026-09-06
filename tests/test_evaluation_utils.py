import pandas as pd

from src.evaluation_utils import evaluate_with_stats


class FakeScores:
    def mean(self) -> float:
        return 0.8

    def std(self) -> float:
        return 0.1


def test_category_metrics_exclude_noncanonical_ground_truth() -> None:
    ground_truth = pd.DataFrame(
        {
            "summary": ["one", "two", "three"],
            "category": [
                "Travel & Events",
                "Entertainment and Shows",
                "News, Politics",
            ],
        }
    )
    predictions = pd.DataFrame(
        {
            "summary": ["one", "two", "three"],
            "category": ["travel & events", "Entertainment & Shows", "Politics"],
        }
    )

    result = evaluate_with_stats(
        ground_truth,
        predictions,
        bertscore_fn=lambda *args, **kwargs: (
            FakeScores(),
            FakeScores(),
            FakeScores(),
        ),
    )

    assert result["Category"]["Accuracy"] == 1.0
    assert result["Category"]["EvaluatedCount"] == 2
    assert result["Category"]["ExcludedGroundTruthCount"] == 1
    assert result["Category"]["ExcludedGroundTruthLabels"] == ["News, Politics"]
