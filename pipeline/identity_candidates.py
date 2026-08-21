from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from itertools import groupby
from pathlib import Path
from typing import Any

from rapidfuzz.fuzz import ratio, token_set_ratio

from pipeline.normalize import fold_text
from pipeline.storage import load_json

MIN_SCORE = 88
MAX_BLOCK_SIZE = 250


def build_identity_candidates_from_search(data_dir: Path, web_data_dir: Path) -> dict[str, int]:
    """Regenerate only the curation report from the already-built search summaries."""
    people_by_id: dict[str, dict[str, Any]] = {}
    for shard in sorted((web_data_dir / "search" / "name").glob("*.json.gz")):
        with gzip.open(shard, "rt", encoding="utf-8") as handle:
            for person in json.load(handle):
                people_by_id[person["entity_id"]] = person
    stats = write_identity_candidates(
        data_dir / "curation" / "candidates.csv",
        list(people_by_id.values()),
        data_dir / "curation" / "entity_merges.json",
    )
    summary = data_dir / "curation" / "candidates.summary.json"
    summary.write_text(
        json.dumps(stats, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return stats


def write_identity_candidates(
    path: Path,
    people: list[dict[str, Any]],
    curation_path: Path,
) -> dict[str, int]:
    """Write conservative, explainable identity candidates without applying merges."""
    curation = load_json(curation_path, {"merges": [], "rejections": []})
    merged_pairs, rejected_pairs = _curated_pairs(curation)
    all_prepared = [_prepare(person) for person in people]
    prepared = [person for person in all_prepared if person["valid_name"]]
    token_frequency = Counter(
        token for person in prepared for token in person["token_set"] if len(token) >= 3
    )
    rows: list[dict[str, Any]] = []
    emitted: set[tuple[str, str]] = set()
    excluded_document_conflicts = 0
    excluded_curated = 0
    pair_comparisons = 0

    for left_index, right_index in _candidate_pairs(prepared):
        pair_comparisons += 1
        left = prepared[left_index]
        right = prepared[right_index]
        pair = _pair_key(left["entity_id"], right["entity_id"])
        if pair in emitted:
            continue
        if pair in merged_pairs or pair in rejected_pairs:
            excluded_curated += 1
            emitted.add(pair)
            continue
        if _documents_conflict(left, right):
            excluded_document_conflicts += 1
            emitted.add(pair)
            continue
        assessment = _assess(left, right, token_frequency)
        if assessment is None:
            continue
        score, confidence, reasons = assessment
        rows.append(_row(left, right, score, confidence, reasons))
        emitted.add(pair)

    _downgrade_ambiguous_documents(rows)

    rows.sort(
        key=lambda item: (
            0 if item["confidence"] == "high" else 1,
            -item["score"],
            item["left_name"],
            item["right_name"],
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "candidate_id",
            "confidence",
            "score",
            "reasons",
            "left_entity_id",
            "left_name",
            "left_document",
            "left_records",
            "left_first_seen",
            "left_last_seen",
            "left_locations",
            "right_entity_id",
            "right_name",
            "right_document",
            "right_records",
            "right_first_seen",
            "right_last_seen",
            "right_locations",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "people_evaluated": len(prepared),
        "people_excluded_invalid_name": len(all_prepared) - len(prepared),
        "pair_comparisons": pair_comparisons,
        "candidates": len(rows),
        "high_confidence": sum(row["confidence"] == "high" for row in rows),
        "review_confidence": sum(row["confidence"] == "review" for row in rows),
        "excluded_document_conflicts": excluded_document_conflicts,
        "excluded_curated": excluded_curated,
    }


def _prepare(person: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(person)
    normalized = fold_text(str(person.get("canonical_name") or ""))
    tokens = tuple(token for token in normalized.split() if token.isalpha())
    prepared["normalized_name"] = " ".join(tokens)
    prepared["tokens"] = tokens
    prepared["token_set"] = frozenset(tokens)
    prepared["sorted_name"] = " ".join(sorted(tokens))
    prepared["valid_name"] = (
        len(tokens) >= 2
        and sum(len(token) for token in tokens) >= 6
        and not any(character.isdigit() for character in normalized)
    )
    return prepared


def _candidate_pairs(people: list[dict[str, Any]]) -> Iterator[tuple[int, int]]:
    entries = _candidate_entries(people)
    entries.sort()
    for _, group in groupby(entries, key=lambda item: item[0]):
        unique = sorted({item[1] for item in group})
        if len(unique) > MAX_BLOCK_SIZE:
            continue
        for offset, left in enumerate(unique):
            yield from ((left, right) for right in unique[offset + 1 :])


def _candidate_entries(people: list[dict[str, Any]]) -> list[tuple[str, int]]:
    token_frequency = Counter(token for person in people for token in person["token_set"] if len(token) >= 3)
    entries: list[tuple[str, int]] = []
    for index, person in enumerate(people):
        sorted_tokens = sorted(person["tokens"])
        if len(sorted_tokens) <= 5:
            entries.append((f"subset:{' '.join(sorted_tokens)}", index))
        if 2 < len(sorted_tokens) <= 5:
            for offset in range(len(sorted_tokens)):
                subset = sorted_tokens[:offset] + sorted_tokens[offset + 1 :]
                entries.append((f"subset:{' '.join(subset)}", index))
        tokens = sorted(
            (token for token in person["token_set"] if len(token) >= 3),
            key=lambda token: (token_frequency[token], -len(token), token),
        )
        if tokens and len(tokens[0]) >= 5:
            rarest = tokens[0]
            context = "".join(sorted(token[0] for token in person["tokens"] if token != rarest))
            for variant in _deletions(rarest):
                entries.append((f"typo:{variant}:{len(person['tokens'])}:{context}", index))
    return entries


def _deletions(token: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(token[:index] + token[index + 1 :] for index in range(len(token))))


def _assess(
    left: dict[str, Any],
    right: dict[str, Any],
    token_frequency: Counter[str],
) -> tuple[int, str, list[str]] | None:
    left_tokens = left["token_set"]
    right_tokens = right["token_set"]
    shared = left_tokens & right_tokens
    shared_rarity = min((token_frequency[token] for token in shared), default=10**9)
    exact_tokens = left_tokens == right_tokens
    contained = left_tokens < right_tokens or right_tokens < left_tokens
    set_score = int(token_set_ratio(left["normalized_name"], right["normalized_name"]))
    ordered_score = int(ratio(left["sorted_name"], right["sorted_name"]))
    score = max(set_score, ordered_score)
    reasons: list[str] = []

    if exact_tokens:
        reasons.append("mismos_tokens")
        score = max(score, 99)
    if contained and len(shared) >= 2:
        reasons.append("nombre_o_apellido_adicional")
        score = max(score, 96)
    if len(left["tokens"]) == len(right["tokens"]) and ordered_score >= 90 and not exact_tokens:
        reasons.append("posible_error_tipografico")
    if _initials_compatible(left["tokens"], right["tokens"]) and shared:
        reasons.append("iniciales_compatibles")
    if bool(left.get("document_number")) != bool(right.get("document_number")):
        reasons.append("documento_solo_en_una_variante")

    strong_structure = exact_tokens or (contained and len(shared) >= 2)
    probable_typo = len(shared) >= 1 and ordered_score >= 90
    if score < MIN_SCORE or not (strong_structure or probable_typo):
        return None
    confidence = (
        "high" if strong_structure and score >= 96 and shared_rarity <= 20 else "review"
    )
    if shared_rarity > 20:
        reasons.append("nombre_compartido_frecuente")
    return score, confidence, reasons


def _downgrade_ambiguous_documents(rows: list[dict[str, Any]]) -> None:
    documents_by_entity: dict[str, set[str]] = {}
    for row in rows:
        left_document = row["left_document"]
        right_document = row["right_document"]
        if bool(left_document) == bool(right_document):
            continue
        entity = row["right_entity_id"] if left_document else row["left_entity_id"]
        document = left_document or right_document
        documents_by_entity.setdefault(entity, set()).add(document)
    ambiguous = {entity for entity, documents in documents_by_entity.items() if len(documents) > 1}
    for row in rows:
        if row["left_entity_id"] not in ambiguous and row["right_entity_id"] not in ambiguous:
            continue
        row["confidence"] = "review"
        reasons = row["reasons"].split("|") if row["reasons"] else []
        if "nombre_asociado_a_documentos_distintos" not in reasons:
            reasons.append("nombre_asociado_a_documentos_distintos")
        row["reasons"] = "|".join(reasons)


def _initials_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    left_initials = {token[0] for token in left if token}
    right_initials = {token[0] for token in right if token}
    return min(len(left_initials), len(right_initials)) > 0 and (
        left_initials <= right_initials or right_initials <= left_initials
    )


def _documents_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_document = left.get("document_number")
    right_document = right.get("document_number")
    return bool(left_document and right_document and left_document != right_document)


def _row(
    left: dict[str, Any],
    right: dict[str, Any],
    score: int,
    confidence: str,
    reasons: list[str],
) -> dict[str, Any]:
    if (right["canonical_name"], right["entity_id"]) < (
        left["canonical_name"],
        left["entity_id"],
    ):
        left, right = right, left
    pair = _pair_key(left["entity_id"], right["entity_id"])
    candidate_id = "cand_" + hashlib.sha256("\x1f".join(pair).encode()).hexdigest()[:20]
    return {
        "candidate_id": candidate_id,
        "confidence": confidence,
        "score": score,
        "reasons": "|".join(dict.fromkeys(reasons)),
        **_side("left", left),
        **_side("right", right),
    }


def _side(prefix: str, person: dict[str, Any]) -> dict[str, Any]:
    document = person.get("document_number") or ""
    document_type = person.get("document_type") or ""
    return {
        f"{prefix}_entity_id": person["entity_id"],
        f"{prefix}_name": person["canonical_name"],
        f"{prefix}_document": f"{document_type}:{document}" if document else "",
        f"{prefix}_records": person.get("record_count", 0),
        f"{prefix}_first_seen": person.get("first_seen") or "",
        f"{prefix}_last_seen": person.get("last_seen") or "",
        f"{prefix}_locations": "|".join(person.get("locations") or []),
    }


def _curated_pairs(curation: dict[str, Any]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    merges: set[tuple[str, str]] = set()
    for item in curation.get("merges", []):
        if isinstance(item, dict) and item.get("from") and item.get("into"):
            merges.add(_pair_key(item["from"], item["into"]))
    rejections: set[tuple[str, str]] = set()
    for item in curation.get("rejections", []):
        if not isinstance(item, dict):
            continue
        left = item.get("left") or item.get("from")
        right = item.get("right") or item.get("into")
        if left and right:
            rejections.add(_pair_key(left, right))
    return merges, rejections


def _pair_key(left: str, right: str) -> tuple[str, str]:
    return tuple(sorted((left, right)))
