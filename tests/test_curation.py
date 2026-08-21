import csv
import json

import pytest

from pipeline.curation import ConfirmationRequired, CurationStore, DocumentConflict

FIELDS = [
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


def candidate(
    candidate_id: str,
    left: str,
    right: str,
    *,
    confidence: str = "high",
    left_document: str = "",
    right_document: str = "",
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "confidence": confidence,
        "score": 100 if confidence == "high" else 91,
        "reasons": "nombre_o_apellido_adicional",
        "left_entity_id": left,
        "left_name": f"PERSONA {left}",
        "left_document": left_document,
        "left_records": 2,
        "left_first_seen": "2023-01-01T00:00:00Z",
        "left_last_seen": "2023-02-01T00:00:00Z",
        "left_locations": "casa-rosada",
        "right_entity_id": right,
        "right_name": f"PERSONA {right}",
        "right_document": right_document,
        "right_records": 5,
        "right_first_seen": "2023-01-01T00:00:00Z",
        "right_last_seen": "2023-03-01T00:00:00Z",
        "right_locations": "casa-rosada|olivos",
    }


def store(tmp_path, rows: list[dict[str, object]]) -> CurationStore:
    candidates = tmp_path / "candidates.csv"
    with candidates.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return CurationStore(candidates, tmp_path / "entity_merges.json")


def test_lists_searches_and_paginates_candidates(tmp_path) -> None:
    curation = store(
        tmp_path,
        [
            candidate("cand_1", "A", "B", left_document="DNI:123"),
            candidate("cand_2", "C", "D", confidence="review"),
        ],
    )

    result = curation.list_candidates(query="123", confidence="high", limit=1)

    assert result["total"] == 1
    assert result["items"][0]["candidate_id"] == "cand_1"
    assert result["items"][0]["recommended_canonical_id"] == "A"
    assert result["summary"]["pending"] == 2


def test_merges_rejects_defers_and_undoes_atomically(tmp_path) -> None:
    curation = store(tmp_path, [candidate("cand_1", "A", "B", right_document="DNI:123")])

    merged = curation.decide("cand_1", "merge", canonical_entity_id="B")
    assert merged["status"] == "merged"
    saved = json.loads((tmp_path / "entity_merges.json").read_text(encoding="utf-8"))
    assert saved["merges"][0]["from"] == "A"
    assert saved["merges"][0]["into"] == "B"
    assert not (tmp_path / "entity_merges.json.tmp").exists()

    undone = curation.decide("cand_1", "undo")
    assert undone["status"] == "pending"
    assert curation.decide("cand_1", "defer")["status"] == "deferred"
    assert curation.decide("cand_1", "reject")["status"] == "rejected"


def test_requires_confirmation_for_review_and_chain(tmp_path) -> None:
    curation = store(
        tmp_path,
        [
            candidate("cand_1", "A", "B"),
            candidate("cand_2", "B", "C", confidence="review"),
        ],
    )
    curation.decide("cand_1", "merge", canonical_entity_id="B")

    with pytest.raises(ConfirmationRequired) as error:
        curation.decide("cand_2", "merge", canonical_entity_id="C")

    assert set(error.value.details["warnings"]) == {
        "confianza_de_revision",
        "fusion_en_cadena",
    }
    merged = curation.decide("cand_2", "merge", canonical_entity_id="C", confirmed=True)
    assert merged["status"] == "merged"


def test_blocks_documents_that_conflict_inside_chain(tmp_path) -> None:
    curation = store(
        tmp_path,
        [
            candidate("cand_1", "A", "B", left_document="DNI:111"),
            candidate("cand_2", "B", "C", right_document="DNI:222"),
        ],
    )
    curation.decide("cand_1", "merge", canonical_entity_id="A")

    with pytest.raises(DocumentConflict) as error:
        curation.decide("cand_2", "merge", canonical_entity_id="B", confirmed=True)

    assert error.value.details["documents"] == ["DNI:111", "DNI:222"]
