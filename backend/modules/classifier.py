from models.internal import ClassificationResult, ClassifiedItem
from modules.classifier_index import ClassifierIndex, normalize


def classify_list(items: list[str], index: ClassifierIndex) -> ClassificationResult:
    """
    Clasifica una lista de ítems de texto libre.

    Orden:
      1. Coincidencia exacta en el índice
      2. Coincidencia parcial por tokens
      3. Fallback a category="otros"
    """
    classified: list[ClassifiedItem] = []
    unrecognized: list[str] = []

    for raw in items:
        item = classify_item(raw, index)
        classified.append(item)
        if item.match_type == "unknown":
            unrecognized.append(raw)

    return ClassificationResult(items=classified, unrecognized=unrecognized)


def classify_item(raw_input: str, index: ClassifierIndex) -> ClassifiedItem:
    key = normalize(raw_input)

    if key in index:
        entry = index[key]
        return ClassifiedItem(
            input=raw_input,
            norm=entry["norm"],
            category=entry["category"],
            match_type=entry["match_type"],
        )

    best = _best_partial_match(key, index)
    if best is not None:
        entry = index[best]
        return ClassifiedItem(
            input=raw_input,
            norm=entry["norm"],
            category=entry["category"],
            match_type="partial",
        )

    return ClassifiedItem(
        input=raw_input,
        norm=None,
        category="otros",
        match_type="unknown",
    )


def _best_partial_match(key: str, index: ClassifierIndex) -> str | None:
    input_tokens = tokenize(key)

    best_key: str | None = None
    best_score = 0

    for known_key in index.keys():
        known_tokens = tokenize(known_key)
        if not known_tokens:
            continue
        if all_tokens_present(known_tokens, input_tokens):
            score = len(known_tokens)
            if score > best_score:
                best_key = known_key
                best_score = score

    return best_key


def tokenize(normalized_text: str) -> list[str]:
    if not normalized_text:
        return []
    return normalized_text.split(" ")


def all_tokens_present(tokens_a: list[str], tokens_b: list[str]) -> bool:
    set_b = set(tokens_b)
    return all(token in set_b for token in tokens_a)
