from pipeline.normalize import canonical_name, document_identity, entity_id, valid_cuil


def test_normalizes_names_and_documents() -> None:
    assert canonical_name("  Pérez, Ana María ") == "PEREZ ANA MARIA"
    assert valid_cuil("20-31248860-5")
    assert document_identity("20-31248860-5") == ("CUIL", "20312488605", "DNI:31248860")
    assert entity_id("PEREZ ANA", "31.248.860") == entity_id("ANA PEREZ", "20-31248860-5")


def test_invalid_cuil_stays_as_generic_document() -> None:
    assert not valid_cuil("20-00000000-0")
    assert document_identity("20-00000000-0")[0] == "DOCUMENTO"
