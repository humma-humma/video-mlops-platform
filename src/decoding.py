"""Token constraints for one category-generation request; no GPU imports."""
from src.taxonomy import CATEGORIES


def category_constraint(tokenizer, eos_token_id):
    """Return a prefix callback and budget that allow only canonical labels + EOS.

    The callback belongs to one generate() call with one input. Capture prompt
    length on its first invocation, after the pipeline has prepared video tokens.
    """
    endings = [eos_token_id] if isinstance(eos_token_id, int) else list(eos_token_id or [])
    if not endings:
        raise ValueError("Constrained category generation requires an EOS token")
    prefixes = {}
    budget = 0
    for label in CATEGORIES:
        for text in (label, " " + label):
            tokens = tokenizer.encode(text, add_special_tokens=False)
            if not tokens or any(token in endings for token in tokens):
                raise ValueError("Category tokenization is empty or contains EOS")
            budget = max(budget, len(tokens) + 1)
            for index, token in enumerate(tokens):
                prefixes.setdefault(tuple(tokens[:index]), set()).add(token)
            prefixes.setdefault(tuple(tokens), set()).update(endings)
    prompt_length = None

    def allowed(batch_id, input_ids):
        nonlocal prompt_length
        if batch_id != 0:
            raise ValueError("Category constraint supports one input per generation")
        if prompt_length is None:
            prompt_length = len(input_ids)
        suffix = tuple(int(token) for token in input_ids[prompt_length:])
        if suffix not in prefixes:
            raise ValueError("Generation departed from the canonical category token tree")
        return sorted(prefixes[suffix])

    return allowed, budget
