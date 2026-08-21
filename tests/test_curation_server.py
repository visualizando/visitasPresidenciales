from pipeline.curation_server import CurationApplication


class StubStore:
    def summary(self):
        return {"pending": 1}

    def list_candidates(self, **arguments):
        return arguments

    def decide(self, candidate_id, action, **arguments):
        return {"candidate_id": candidate_id, "action": action, **arguments}

    def safe_batch_preview(self):
        return {"merge_operations": 12}

    def apply_safe_batch(self, **arguments):
        return {"action": "apply", **arguments}

    def undo_batch(self, batch_id):
        return {"action": "undo", "batch_id": batch_id}


def test_application_parses_filters_and_decisions() -> None:
    application = CurationApplication(StubStore(), token="fixed")

    result = application.candidates(
        {"q": ["Cerimedo"], "confidence": ["high"], "offset": ["50"], "limit": ["25"]}
    )
    decision = application.decide(
        {
            "candidate_id": "cand_1",
            "action": "merge",
            "canonical_entity_id": "per_1",
            "confirmed": True,
            "note": "Mismo nombre",
        }
    )

    assert result["query"] == "Cerimedo"
    assert result["offset"] == 50
    assert result["limit"] == 25
    assert decision["confirmed"] is True


def test_application_previews_applies_and_undoes_batch() -> None:
    application = CurationApplication(StubStore(), token="fixed")

    assert application.batch_preview()["merge_operations"] == 12
    assert application.batch({"action": "apply", "confirmed": True})["confirmed"] is True
    assert application.batch({"action": "undo", "batch_id": "batch_1"})["batch_id"] == "batch_1"
