from types import SimpleNamespace

import pytest

from src.decoding import category_constraint
from src.taxonomy import CATEGORIES
from src.inference_utils import run_inference


class CharacterTokenizer:
    def encode(self, text, add_special_tokens=False):
        return [ord(character) for character in text]


def test_every_canonical_label_can_complete_but_early_eos_is_blocked():
    for label in CATEGORIES:
        for text in (label, " " + label):
            callback, budget = category_constraint(CharacterTokenizer(), [0, 1])
            prompt = [120, 121]
            tokens = CharacterTokenizer().encode(text)
            for index, token in enumerate(tokens):
                allowed = callback(0, prompt + tokens[:index])
                assert token in allowed
                assert 0 not in allowed
            assert callback(0, prompt + tokens) == [0, 1]
            assert budget >= len(tokens) + 1


def test_constraint_rejects_unknown_tokens_and_multiple_inputs():
    callback, _ = category_constraint(CharacterTokenizer(), 0)
    callback(0, [120])
    with pytest.raises(ValueError, match="departed"):
        callback(0, [120, 127])
    with pytest.raises(ValueError, match="one input"):
        callback(1, [120])
    with pytest.raises(ValueError, match="EOS"):
        category_constraint(CharacterTokenizer(), None)


def test_inference_forwards_constraint_and_budget_only_for_category():
    class FakePipeline:
        processor = SimpleNamespace(tokenizer=CharacterTokenizer())
        model = SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=0))
        def __call__(self, **kwargs):
            self.kwargs = kwargs
            return [[{"generated_text": [{"content": "News"}]}]]
    pipe = FakePipeline()
    assert run_inference(pipe, [[{}]], mode="category", constrain_category=True)[0] == ["News"]
    assert set(pipe.kwargs) == {"text", "generate_kwargs"}
    assert callable(pipe.kwargs["generate_kwargs"]["prefix_allowed_tokens_fn"])
    assert pipe.kwargs["generate_kwargs"]["max_new_tokens"] > 10
    assert pipe.kwargs["generate_kwargs"]["do_sample"] is False
    run_inference(pipe, [[{}]], mode="summary", constrain_category=True)
    assert "prefix_allowed_tokens_fn" not in pipe.kwargs["generate_kwargs"]
    with pytest.raises(ValueError, match="one video"):
        run_inference(pipe, [[{}], [{}]], constrain_category=True)


def test_installed_transformers_pipeline_forwards_generation_options():
    transformers = pytest.importorskip("transformers")
    class PipelineBoundary:
        processor = SimpleNamespace(tokenizer=CharacterTokenizer())
        model = SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=0))
        def __call__(self, **kwargs):
            kwargs.pop("text")
            preprocessing, forward, _ = transformers.ImageTextToTextPipeline._sanitize_parameters(self, **kwargs)
            assert "prefix_allowed_tokens_fn" not in preprocessing
            assert "do_sample" not in preprocessing
            assert callable(forward["generate_kwargs"]["prefix_allowed_tokens_fn"])
            assert forward["generate_kwargs"]["do_sample"] is False
            return [[{"generated_text": [{"content": "News"}]}]]
    assert run_inference(PipelineBoundary(), [[{}]], constrain_category=True)[0] == ["News"]
