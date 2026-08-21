import csv

from pipeline.identity_candidates import write_identity_candidates


def person(
    entity_id: str,
    name: str,
    document: str | None = None,
    records: int = 1,
) -> dict[str, object]:
    return {
        "entity_id": entity_id,
        "canonical_name": name,
        "document_type": "DNI" if document else None,
        "document_number": document,
        "record_count": records,
        "first_seen": "2023-01-01T10:00:00",
        "last_seen": "2024-01-01T10:00:00",
        "locations": ["casa-rosada"],
    }


def read_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_proposes_second_name_variant_with_explanation(tmp_path) -> None:
    output = tmp_path / "candidates.csv"
    curation = tmp_path / "entity_merges.json"
    stats = write_identity_candidates(
        output,
        [
            person("per_short", "MARCELO CERIMEDO", records=12),
            person("per_full", "MARCELO DANIEL CERIMEDO", records=8),
        ],
        curation,
    )

    rows = read_rows(output)
    assert stats["candidates"] == 1
    assert stats["high_confidence"] == 1
    assert rows[0]["confidence"] == "high"
    assert rows[0]["score"] == "100"
    assert "nombre_o_apellido_adicional" in rows[0]["reasons"]
    assert {rows[0]["left_records"], rows[0]["right_records"]} == {"8", "12"}


def test_proposes_order_and_typo_variants(tmp_path) -> None:
    output = tmp_path / "candidates.csv"
    curation = tmp_path / "entity_merges.json"
    write_identity_candidates(
        output,
        [
            person("per_order_1", "PEREZ ANA MARIA"),
            person("per_order_2", "ANA MARIA PEREZ"),
            person("per_typo_1", "MARTINEZ CARLOS"),
            person("per_typo_2", "MARTINES CARLOS"),
        ],
        curation,
    )

    rows = read_rows(output)
    by_names = {frozenset((row["left_name"], row["right_name"])): row for row in rows}
    order = by_names[frozenset(("PEREZ ANA MARIA", "ANA MARIA PEREZ"))]
    typo = by_names[frozenset(("MARTINEZ CARLOS", "MARTINES CARLOS"))]
    assert order["confidence"] == "high"
    assert "mismos_tokens" in order["reasons"]
    assert typo["confidence"] == "review"
    assert "posible_error_tipografico" in typo["reasons"]


def test_excludes_conflicting_documents_and_curated_pairs(tmp_path) -> None:
    output = tmp_path / "candidates.csv"
    curation = tmp_path / "entity_merges.json"
    curation.write_text(
        """
        {
          "merges": [],
          "rejections": [{"left": "per_rejected_1", "right": "per_rejected_2"}]
        }
        """,
        encoding="utf-8",
    )
    stats = write_identity_candidates(
        output,
        [
            person("per_doc_1", "JUAN PEREZ", "30111111"),
            person("per_doc_2", "JUAN CARLOS PEREZ", "30222222"),
            person("per_rejected_1", "MARIA LOPEZ"),
            person("per_rejected_2", "MARIA ELENA LOPEZ"),
        ],
        curation,
    )

    assert read_rows(output) == []
    assert stats["excluded_document_conflicts"] == 1
    assert stats["excluded_curated"] == 1


def test_excludes_names_contaminated_with_numeric_columns(tmp_path) -> None:
    output = tmp_path / "candidates.csv"
    stats = write_identity_candidates(
        output,
        [
            person("per_dirty", "1 BOGADO SILVIA 34 434 790"),
            person("per_clean", "BOGADO SILVIA", "34434790"),
        ],
        tmp_path / "entity_merges.json",
    )

    assert read_rows(output) == []
    assert stats["people_excluded_invalid_name"] == 1


def test_downgrades_undocumented_name_linked_to_multiple_documents(tmp_path) -> None:
    output = tmp_path / "candidates.csv"
    write_identity_candidates(
        output,
        [
            person("per_unknown", "JUANA PEREZ"),
            person("per_doc_1", "JUANA PEREZ", "30111111"),
            person("per_doc_2", "JUANA PEREZ", "30222222"),
        ],
        tmp_path / "entity_merges.json",
    )

    rows = read_rows(output)
    assert len(rows) == 2
    assert {row["confidence"] for row in rows} == {"review"}
    assert all("nombre_asociado_a_documentos_distintos" in row["reasons"] for row in rows)
