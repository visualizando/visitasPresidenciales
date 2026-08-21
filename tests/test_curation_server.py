from pipeline.curation_server import CurationApplication


class StubStore:
    def summary(self):
        return {"pending": 1}

    def list_candidates(self, **arguments):
        return arguments

    def decide(self, candidate_id, action, **arguments):
        return {"candidate_id": candidate_id, "action": action, **arguments}


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
