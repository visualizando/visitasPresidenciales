import csv
import json

import pytest

from pipeline.curation import ConfirmationRequired, CurationError, CurationStore, DocumentConflict

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
    left_records: int = 2,
    right_records: int = 5,
) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "confidence": confidence,
        "score": 100 if confidence == "high" else 91,
        "reasons": "nombre_o_apellido_adicional",
        "left_entity_id": left,
        "left_name": f"PERSONA {left}",
        "left_document": left_document,
        "left_records": left_records,
        "left_first_seen": "2023-01-01T00:00:00Z",
        "left_last_seen": "2023-02-01T00:00:00Z",
        "left_locations": "casa-rosada",
        "right_entity_id": right,
        "right_name": f"PERSONA {right}",
        "right_document": right_document,
        "right_records": right_records,
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


def test_filters_candidates_by_combined_activity_and_returns_counts(tmp_path) -> None:
    curation = store(
        tmp_path,
        [
            candidate("low", "A", "B", left_records=1, right_records=3),
            candidate("medium", "C", "D", left_records=2, right_records=7),
            candidate("high", "E", "F", left_records=10, right_records=25),
            candidate("very_high", "G", "H", left_records=40, right_records=80),
        ],
    )

    result = curation.list_candidates(activity="very_high")

    assert [item["candidate_id"] for item in result["items"]] == ["very_high"]
    assert result["items"][0]["total_records"] == 120
    assert result["activity_summary"] == {
        "all": 4,
        "very_high": 1,
        "high": 1,
        "medium": 1,
        "low": 1,
    }


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


def test_safe_batch_previews_applies_and_undoes_without_touching_manual_merges(tmp_path) -> None:
    curation = store(
        tmp_path,
        [
            candidate("safe_1", "A", "B", left_document="DNI:111"),
            candidate("safe_2", "B", "C"),
            candidate("no_doc", "D", "E"),
            candidate("conflict_1", "F", "G", left_document="DNI:222"),
            candidate("conflict_2", "G", "H", right_document="DNI:333"),
            candidate("curated", "I", "J", left_document="DNI:444"),
            candidate("curated_path_1", "I", "K", left_document="DNI:444"),
            candidate("curated_path_2", "K", "J"),
            candidate("manual", "Y", "Z", confidence="review", right_document="DNI:999"),
        ],
    )
    curation.decide("curated", "reject")
    curation.decide("manual", "merge", canonical_entity_id="Z", confirmed=True)

    preview = curation.safe_batch_preview()
    assert preview["eligible_components"] == 1
    assert preview["merge_operations"] == 2
    assert preview["excluded_no_document_merges"] == 1
    assert preview["excluded_conflict_merges"] == 2
    assert preview["excluded_curated_merges"] == 2

    with pytest.raises(ConfirmationRequired):
        curation.apply_safe_batch()

    applied = curation.apply_safe_batch(confirmed=True)
    batch_id = applied["batch"]["batch_id"]
    assert applied["batch"]["merge_count"] == 2
    assert curation.list_candidates(status="merged")["total"] == 3

    with pytest.raises(CurationError, match="lote completo"):
        curation.decide("safe_1", "undo")

    undone = curation.undo_batch(batch_id)
    assert undone["batch"]["status"] == "undone"
    assert curation.list_candidates(status="merged")["total"] == 1
    saved = json.loads((tmp_path / "entity_merges.json").read_text(encoding="utf-8"))
    assert saved["merges"] == [
        next(item for item in saved["merges"] if item["candidate_id"] == "manual")
    ]
