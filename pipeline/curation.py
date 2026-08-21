from __future__ import annotations

import csv
import json
import os
import threading
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pipeline.storage import load_json

FINAL_ACTIONS = {"merge", "reject"}
VALID_ACTIONS = FINAL_ACTIONS | {"defer", "undo"}
SAFE_BATCH_RULE = "high-score-100-single-document-v1"


class CurationError(Exception):
    code = "curation_error"
    status = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class CandidateNotFound(CurationError):
    code = "candidate_not_found"
    status = 404


class ConfirmationRequired(CurationError):
    code = "confirmation_required"
    status = 409


class DocumentConflict(CurationError):
    code = "document_conflict"
    status = 409


class CurationStore:
    def __init__(self, candidates_path: Path, decisions_path: Path) -> None:
        self.candidates_path = candidates_path
        self.decisions_path = decisions_path
        self._lock = threading.RLock()
        self._candidates = self._load_candidates()
        self._candidate_by_id = {
            candidate["candidate_id"]: candidate for candidate in self._candidates
        }
        self._documents_by_entity, self._records_by_entity = self._index_entities()
        self._decisions = self._load_decisions()
        self._refresh_decision_indexes()

    def _load_candidates(self) -> list[dict[str, Any]]:
        with self.candidates_path.open(encoding="utf-8", newline="") as handle:
            candidates = list(csv.DictReader(handle))
        for candidate in candidates:
            for key in ("score", "left_records", "right_records"):
                candidate[key] = int(candidate.get(key) or 0)
            candidate["reasons"] = [
                reason for reason in candidate.get("reasons", "").split("|") if reason
            ]
            candidate["recommended_canonical_id"] = self._recommended_canonical(candidate)
        return candidates

    def _load_decisions(self) -> dict[str, Any]:
        decisions = load_json(
            self.decisions_path,
            {"version": 3, "merges": [], "rejections": [], "deferred": [], "batches": []},
        )
        decisions.setdefault("version", 2)
        decisions.setdefault("merges", [])
        decisions.setdefault("rejections", [])
        decisions.setdefault("deferred", [])
        decisions.setdefault("batches", [])
        return decisions

    def _index_entities(self) -> tuple[dict[str, set[str]], dict[str, int]]:
        documents: dict[str, set[str]] = defaultdict(set)
        records: dict[str, int] = defaultdict(int)
        for candidate in self._candidates:
            for side in ("left", "right"):
                entity = candidate[f"{side}_entity_id"]
                document = candidate.get(f"{side}_document")
                if document:
                    documents[entity].add(document)
                records[entity] = max(records[entity], int(candidate.get(f"{side}_records") or 0))
        return documents, records

    def safe_batch_preview(self) -> dict[str, Any]:
        with self._lock:
            return self._public_batch_plan(self._safe_batch_plan())

    def apply_safe_batch(self, *, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise ConfirmationRequired("Confirmá explícitamente la fusión segura por lote.")
        with self._lock:
            plan = self._safe_batch_plan()
            if not plan["operations"]:
                return self._public_batch_plan(plan)
            now = datetime.now(UTC).isoformat()
            batch_id = (
                f"batch_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
            )
            for operation in plan["operations"]:
                self._decisions["merges"].append(
                    {
                        "from": operation["from"],
                        "into": operation["into"],
                        "action": "merge",
                        "reason": "Lote seguro: puntaje 100 y un único documento consistente",
                        "decided_at": now,
                        "decided_by": "local-curation-ui",
                        "batch_id": batch_id,
                        "rule": SAFE_BATCH_RULE,
                    }
                )
            batch = {
                "batch_id": batch_id,
                "rule": SAFE_BATCH_RULE,
                "status": "applied",
                "created_at": now,
                "merge_count": len(plan["operations"]),
                "component_count": plan["eligible_components"],
            }
            self._decisions["batches"].append(batch)
            self._save()
            return {**self._public_batch_plan(plan), "batch": batch}

    def undo_batch(self, batch_id: str) -> dict[str, Any]:
        with self._lock:
            batch = next(
                (item for item in self._decisions["batches"] if item.get("batch_id") == batch_id),
                None,
            )
            if batch is None:
                raise CandidateNotFound("No se encontró el lote solicitado.")
            if batch.get("status") != "applied":
                raise CurationError("Ese lote ya fue deshecho.")
            removed = sum(item.get("batch_id") == batch_id for item in self._decisions["merges"])
            self._decisions["merges"] = [
                item for item in self._decisions["merges"] if item.get("batch_id") != batch_id
            ]
            batch["status"] = "undone"
            batch["undone_at"] = datetime.now(UTC).isoformat()
            batch["removed_merge_count"] = removed
            self._save()
            return {
                "batch": dict(batch),
                "preview": self._public_batch_plan(self._safe_batch_plan()),
            }

    def _safe_batch_plan(self) -> dict[str, Any]:
        candidates = [
            candidate
            for candidate in self._candidates
            if candidate["confidence"] == "high"
            and candidate["score"] == 100
            and self._candidate_status(candidate) == "pending"
        ]
        graph: dict[str, set[str]] = defaultdict(set)
        for entity, neighbors in self._merge_graph.items():
            graph[entity].update(neighbors)
        for candidate in candidates:
            left, right = candidate["left_entity_id"], candidate["right_entity_id"]
            graph[left].add(right)
            graph[right].add(left)

        curated_pairs = []
        for key in ("rejections", "deferred"):
            for item in self._decisions[key]:
                left, right = item.get("left"), item.get("right")
                if left and right:
                    curated_pairs.append(frozenset((left, right)))

        seen: set[str] = set()
        operations: list[dict[str, str]] = []
        counts = {
            "candidate_edges": len(candidates),
            "eligible_components": 0,
            "eligible_identities": 0,
            "excluded_no_document_components": 0,
            "excluded_no_document_merges": 0,
            "excluded_conflict_components": 0,
            "excluded_conflict_merges": 0,
            "excluded_curated_components": 0,
            "excluded_curated_merges": 0,
        }
        for seed in sorted(
            {
                entity
                for candidate in candidates
                for entity in (candidate["left_entity_id"], candidate["right_entity_id"])
            }
        ):
            if seed in seen:
                continue
            component = {seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                for neighbor in graph.get(current, set()) - component:
                    component.add(neighbor)
                    queue.append(neighbor)
            seen.update(component)
            roots = {self._resolve_entity(entity) for entity in component}
            merge_count = max(0, len(roots) - 1)
            if not merge_count:
                continue
            documents = set().union(
                *(self._documents_by_entity.get(entity, set()) for entity in component)
            )
            if any(pair <= component for pair in curated_pairs):
                counts["excluded_curated_components"] += 1
                counts["excluded_curated_merges"] += merge_count
                continue
            if not documents:
                counts["excluded_no_document_components"] += 1
                counts["excluded_no_document_merges"] += merge_count
                continue
            if len(documents) > 1:
                counts["excluded_conflict_components"] += 1
                counts["excluded_conflict_merges"] += merge_count
                continue
            documented_roots = {
                self._resolve_entity(entity)
                for entity in component
                if self._documents_by_entity.get(entity)
            }
            canonical = min(
                documented_roots,
                key=lambda entity: (-self._component_record_count(entity), entity),
            )
            for other in sorted(roots - {canonical}):
                operations.append({"from": other, "into": canonical})
            counts["eligible_components"] += 1
            counts["eligible_identities"] += len(roots)
        return {**counts, "operations": operations}

    def _component_record_count(self, root: str) -> int:
        return sum(self._records_by_entity.get(entity, 0) for entity in self._merge_component(root))

    def _public_batch_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        latest_batch = next(
            (
                dict(item)
                for item in reversed(self._decisions["batches"])
                if item.get("status") == "applied"
            ),
            None,
        )
        return {key: value for key, value in plan.items() if key != "operations"} | {
            "rule": SAFE_BATCH_RULE,
            "merge_operations": len(plan["operations"]),
            "latest_batch": latest_batch,
        }

    def list_candidates(
        self,
        *,
        query: str = "",
        confidence: str = "all",
        status: str = "pending",
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        query_folded = query.casefold().strip()
        with self._lock:
            decorated = [self._decorate(candidate) for candidate in self._candidates]
        matches = [
            candidate
            for candidate in decorated
            if (confidence == "all" or candidate["confidence"] == confidence)
            and (status == "all" or candidate["status"] == status)
            and (not query_folded or query_folded in self._search_text(candidate))
        ]
        return {
            "items": matches[offset : offset + limit],
            "offset": offset,
            "limit": limit,
            "total": len(matches),
            "summary": self.summary(decorated),
        }

    def summary(self, decorated: list[dict[str, Any]] | None = None) -> dict[str, int]:
        if decorated is None:
            with self._lock:
                decorated = [self._decorate(candidate) for candidate in self._candidates]
        result = {
            "total": len(decorated),
            "pending": 0,
            "merged": 0,
            "rejected": 0,
            "deferred": 0,
            "high": 0,
            "review": 0,
        }
        for candidate in decorated:
            result[candidate["status"]] += 1
            result[candidate["confidence"]] += 1
        return result

    def decide(
        self,
        candidate_id: str,
        action: str,
        *,
        canonical_entity_id: str | None = None,
        confirmed: bool = False,
        note: str = "",
    ) -> dict[str, Any]:
        if action not in VALID_ACTIONS:
            raise CurationError("La acción solicitada no existe.")
        note = note.strip()[:500]
        with self._lock:
            candidate = self._candidate_by_id.get(candidate_id)
            if candidate is None:
                raise CandidateNotFound("No se encontró el candidato solicitado.")
            if action == "undo":
                batch_ids = self._candidate_batch_ids(candidate)
                if batch_ids:
                    raise CurationError(
                        "Esta coincidencia pertenece a un lote. Deshacé el lote completo.",
                        details={"batch_ids": batch_ids},
                    )
                self._remove_candidate_decisions(candidate)
                self._save()
                return self._decorate(candidate)
            if action == "merge":
                self._merge(
                    candidate,
                    canonical_entity_id=canonical_entity_id,
                    confirmed=confirmed,
                    note=note,
                )
            elif action == "reject":
                self._remove_candidate_decisions(candidate)
                self._decisions["rejections"].append(
                    self._decision_payload(candidate, "reject", note)
                )
            else:
                self._remove_candidate_decisions(candidate)
                self._decisions["deferred"].append(self._decision_payload(candidate, "defer", note))
            self._save()
            return self._decorate(candidate)

    def _merge(
        self,
        candidate: dict[str, Any],
        *,
        canonical_entity_id: str | None,
        confirmed: bool,
        note: str,
    ) -> None:
        left = candidate["left_entity_id"]
        right = candidate["right_entity_id"]
        if canonical_entity_id not in {left, right}:
            raise CurationError("Elegí cuál de las dos identidades conservar.")
        component = self._merge_component(left) | self._merge_component(right)
        documents = set().union(
            *(self._documents_by_entity.get(entity, set()) for entity in component)
        )
        if len(documents) > 1:
            raise DocumentConflict(
                "La fusión involucraría documentos diferentes y fue bloqueada.",
                details={"documents": sorted(documents), "entities": sorted(component)},
            )
        warnings = self._merge_warnings(candidate, component)
        if warnings and not confirmed:
            raise ConfirmationRequired(
                "Esta fusión necesita una confirmación adicional.",
                details={"warnings": warnings, "entities": sorted(component)},
            )
        canonical_root = self._resolve_entity(canonical_entity_id)
        other = right if canonical_entity_id == left else left
        other_root = self._resolve_entity(other)
        if canonical_root == other_root:
            return
        self._remove_candidate_decisions(candidate)
        payload = self._decision_payload(candidate, "merge", note)
        payload.update({"from": other_root, "into": canonical_root})
        self._decisions["merges"].append(payload)

    def _merge_warnings(self, candidate: dict[str, Any], component: set[str]) -> list[str]:
        warnings: list[str] = []
        if candidate["confidence"] != "high":
            warnings.append("confianza_de_revision")
        if "nombre_compartido_frecuente" in candidate["reasons"]:
            warnings.append("nombre_frecuente")
        if len(component) > 2:
            warnings.append("fusion_en_cadena")
        return warnings

    def _decorate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        result = dict(candidate)
        result["status"] = self._candidate_status(candidate)
        result["warnings"] = self._merge_warnings(
            candidate,
            self._merge_component(candidate["left_entity_id"])
            | self._merge_component(candidate["right_entity_id"]),
        )
        batch_ids = self._candidate_batch_ids(candidate)
        result["batch_id"] = batch_ids[0] if len(batch_ids) == 1 else None
        return result

    def _candidate_batch_ids(self, candidate: dict[str, Any]) -> list[str]:
        component = self._merge_component(candidate["left_entity_id"]) | self._merge_component(
            candidate["right_entity_id"]
        )
        return sorted(
            {
                item["batch_id"]
                for item in self._decisions["merges"]
                if item.get("batch_id")
                and item.get("from") in component
                and item.get("into") in component
            }
        )

    def _candidate_status(self, candidate: dict[str, Any]) -> str:
        candidate_id = candidate["candidate_id"]
        if candidate_id in self._rejected_candidates:
            return "rejected"
        if candidate_id in self._deferred_candidates:
            return "deferred"
        left = self._resolve_entity(candidate["left_entity_id"])
        right = self._resolve_entity(candidate["right_entity_id"])
        if left == right:
            return "merged"
        return "pending"

    def _merge_component(self, entity_id: str) -> set[str]:
        component = {entity_id}
        queue = [entity_id]
        while queue:
            current = queue.pop()
            for neighbor in self._merge_graph.get(current, set()) - component:
                component.add(neighbor)
                queue.append(neighbor)
        return component

    def _resolve_entity(self, entity_id: str) -> str:
        cached = self._resolved_entities.get(entity_id)
        if cached:
            return cached
        seen: set[str] = set()
        current = entity_id
        while current in self._merge_targets and current not in seen:
            seen.add(current)
            current = self._merge_targets[current]
        if current in seen:
            raise CurationError("Las fusiones existentes contienen un ciclo.")
        for member in seen:
            self._resolved_entities[member] = current
        self._resolved_entities[entity_id] = current
        return current

    def _refresh_decision_indexes(self) -> None:
        self._merge_targets: dict[str, str] = {}
        self._merge_graph: dict[str, set[str]] = defaultdict(set)
        for item in self._decisions["merges"]:
            source, target = item.get("from"), item.get("into")
            if source and target:
                self._merge_targets[source] = target
                self._merge_graph[source].add(target)
                self._merge_graph[target].add(source)
        self._resolved_entities: dict[str, str] = {}
        self._rejected_candidates = {
            item.get("candidate_id")
            for item in self._decisions["rejections"]
            if item.get("candidate_id")
        }
        self._deferred_candidates = {
            item.get("candidate_id")
            for item in self._decisions["deferred"]
            if item.get("candidate_id")
        }

    def _remove_candidate_decisions(self, candidate: dict[str, Any]) -> None:
        candidate_id = candidate["candidate_id"]
        pair = frozenset((candidate["left_entity_id"], candidate["right_entity_id"]))
        for key in ("merges", "rejections", "deferred"):
            self._decisions[key] = [
                item
                for item in self._decisions[key]
                if item.get("candidate_id") != candidate_id
                and not (
                    not item.get("candidate_id")
                    and not item.get("batch_id")
                    and self._same_pair(item, pair)
                )
            ]

    @staticmethod
    def _same_pair(item: dict[str, Any], pair: frozenset[str]) -> bool:
        left = item.get("left") or item.get("from")
        right = item.get("right") or item.get("into")
        return bool(left and right and frozenset((left, right)) == pair)

    @staticmethod
    def _decision_payload(candidate: dict[str, Any], action: str, note: str) -> dict[str, Any]:
        return {
            "candidate_id": candidate["candidate_id"],
            "left": candidate["left_entity_id"],
            "right": candidate["right_entity_id"],
            "action": action,
            "reason": note,
            "decided_at": datetime.now(UTC).isoformat(),
            "decided_by": "local-curation-ui",
        }

    @staticmethod
    def _recommended_canonical(candidate: dict[str, Any]) -> str:
        left_document = candidate.get("left_document")
        right_document = candidate.get("right_document")
        if bool(left_document) != bool(right_document):
            return candidate["left_entity_id"] if left_document else candidate["right_entity_id"]
        if candidate["left_records"] != candidate["right_records"]:
            return (
                candidate["left_entity_id"]
                if candidate["left_records"] > candidate["right_records"]
                else candidate["right_entity_id"]
            )
        return candidate["left_entity_id"]

    @staticmethod
    def _search_text(candidate: dict[str, Any]) -> str:
        return " ".join(
            str(candidate.get(key) or "")
            for key in ("left_name", "right_name", "left_document", "right_document")
        ).casefold()

    def _save(self) -> None:
        self._decisions["version"] = max(3, int(self._decisions.get("version") or 1))
        self._decisions["updated_at"] = datetime.now(UTC).isoformat()
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.decisions_path.with_suffix(self.decisions_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._decisions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.decisions_path)
        self._refresh_decision_indexes()
