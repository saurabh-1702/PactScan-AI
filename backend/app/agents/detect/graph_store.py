"""Graph persistence for the Detect agent.

An abstract ``GraphStore`` with two implementations:

* ``Neo4jGraphStore`` — real Cypher against the Phase 0 Neo4j container, including
  the ``OVERRIDES*1..3`` multi-hop traversal. Every query is filtered by
  ``tenant_id`` (hardcoded ``demo_tenant`` for Phase 1; real multi-tenancy is
  Phase 5, but writing the filter now keeps that a small change).
* ``InMemoryGraphStore`` — a pure-Python equivalent used by the mocked test
  suite so unit tests need no Docker / Neo4j.

Node / relationship schema:
  (:Contract {id, filename, tenant_id, upload_date})
  (:Clause {id, contract_id, clause_type, page_number, section_header, raw_text, confidence, tenant_id})
  (:PlaybookRule {id, rule_text, tenant_id})
  (:RegulationClause {id, regulation_name, section, text})
  (:Finding {id, ...})
  (:Clause)-[:BELONGS_TO]->(:Contract)
  (:Clause)-[:OVERRIDES {scope}]->(:Clause)
  (:Clause)-[:VIOLATES]->(:RegulationClause)
  (:Clause)-[:CONTRADICTS]->(:PlaybookRule)
  (:Contract)-[:HAS_FINDING]->(:Finding)-[:ABOUT]->(:Clause)
"""

from __future__ import annotations

import abc
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.models.clause import (
    ConfidenceLevel,
    ExtractedClause,
    Finding,
    Severity,
)

DEMO_TENANT = "demo_tenant"


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class GraphStore(abc.ABC):
    # --- seeding -----------------------------------------------------------
    @abc.abstractmethod
    def seed_playbook_rules(self, rules: list[dict], tenant_id: str = DEMO_TENANT) -> None: ...

    @abc.abstractmethod
    def seed_regulation_clauses(self, clauses: list[dict]) -> None: ...

    @abc.abstractmethod
    def get_playbook_rules(self, tenant_id: str = DEMO_TENANT) -> list[dict]: ...

    @abc.abstractmethod
    def get_regulation_clauses(self) -> list[dict]: ...

    @abc.abstractmethod
    def add_regulation_update(
        self, regulation_name: str, new_clause_text: str, effective_date: str
    ) -> dict:
        """Phase 6 Horizon-Scanning: inserts a new RegulationClause representing
        an amendment/new rule under an existing regulation (DPDP or GDPR) —
        distinct from ``seed_regulation_clauses``, which is for the fixed
        startup seed set. Matches the phase prompt's literal signature (no
        ``section`` param); ``section`` is derived from ``effective_date`` so
        the returned clause still has one, consistent with every seeded
        RegulationClause. Returns the created clause dict: {id,
        regulation_name, section, text, effective_date}. Global, like every
        other RegulationClause — not tenant-scoped."""

    # --- contract / clause writes ---------------------------------------
    @abc.abstractmethod
    def upsert_contract(
        self, contract_id: str, filename: str, tenant_id: str = DEMO_TENANT
    ) -> None: ...

    @abc.abstractmethod
    def add_clause(self, clause: ExtractedClause, tenant_id: str = DEMO_TENANT) -> None: ...

    @abc.abstractmethod
    def add_override(
        self, src_clause_id: str, dst_clause_id: str, scope: str, tenant_id: str = DEMO_TENANT
    ) -> None: ...

    # --- reads ---------------------------------------------------------
    @abc.abstractmethod
    def contract_exists(self, contract_id: str, tenant_id: str = DEMO_TENANT) -> bool: ...

    @abc.abstractmethod
    def get_clauses_for_contract(
        self, contract_id: str, tenant_id: str = DEMO_TENANT
    ) -> list[ExtractedClause]: ...

    @abc.abstractmethod
    def get_overriders(
        self, clause_id: str, max_hops: int = 3, tenant_id: str = DEMO_TENANT
    ) -> list[dict]:
        """Clauses that override ``clause_id`` (incoming OVERRIDES), nearest hop
        first. Each dict: {id, page_number, raw_text, scope, hops}."""

    # --- findings ----------------------------------------------------
    @abc.abstractmethod
    def replace_findings(
        self, contract_id: str, findings: list[Finding], tenant_id: str = DEMO_TENANT
    ) -> None: ...

    @abc.abstractmethod
    def add_findings(
        self, contract_id: str, findings: list[Finding], tenant_id: str = DEMO_TENANT
    ) -> list[Finding]:
        """Additive, unlike ``replace_findings`` — which DETACH DELETEs every
        existing Finding for the contract first. Horizon-Scanning (Phase 6)
        must never call ``replace_findings``: a contract that was already
        Detect-scanned would silently lose its original findings the moment
        a later regulation update re-diffed it. MERGEs by finding_id (so a
        re-run of the same simulated update is idempotent) and returns only
        the findings that were newly created (already-existing ones, by id,
        are skipped) — the caller uses this to know what to notify about."""

    @abc.abstractmethod
    def get_findings(
        self, contract_id: str, tenant_id: str = DEMO_TENANT
    ) -> list[Finding]: ...

    @abc.abstractmethod
    def get_all_findings(self, tenant_id: str = DEMO_TENANT) -> list[dict]:
        """Every finding across every contract in the tenant (Phase 5's
        dashboard). Each dict: {finding_id, contract_id, clause_id, severity,
        rule_or_regulation_violated}. Unlike ``get_findings``, not scoped to
        one contract, and returns plain dicts (with contract_id) rather than
        ``Finding`` — a dashboard aggregate, not a Detect report."""

    @abc.abstractmethod
    def write_compliance_edges(
        self,
        contract_id: str,
        edges: list[tuple[str, str, str]],
        tenant_id: str = DEMO_TENANT,
    ) -> None:
        """Each edge: (clause_id, rel_type, target_node_id) where rel_type is
        'VIOLATES' (-> RegulationClause) or 'CONTRADICTS' (-> PlaybookRule)."""

    @abc.abstractmethod
    def record_detect_run(
        self, contract_id: str, timestamp: str, tenant_id: str = DEMO_TENANT
    ) -> None: ...

    @abc.abstractmethod
    def get_detect_run(
        self, contract_id: str, tenant_id: str = DEMO_TENANT
    ) -> str | None: ...

    # --- test / maintenance ---------------------------------------
    @abc.abstractmethod
    def wipe_contract(self, contract_id: str, tenant_id: str = DEMO_TENANT) -> None: ...

    # --- Suggest agent support (Phase 2) --------------------------
    @abc.abstractmethod
    def get_clause_by_id(
        self, clause_id: str, tenant_id: str = DEMO_TENANT
    ) -> ExtractedClause | None: ...

    @abc.abstractmethod
    def find_finding_by_id(
        self, finding_id: str, tenant_id: str = DEMO_TENANT
    ) -> Finding | None:
        """Look up a finding by id alone (no contract_id required) — the
        POST /api/suggest/from-finding/{finding_id} endpoint only has the id."""

    @abc.abstractmethod
    def set_clause_embedding(
        self, clause_id: str, embedding: list[float], tenant_id: str = DEMO_TENANT
    ) -> None: ...

    @abc.abstractmethod
    def get_clauses_missing_embedding(
        self, tenant_id: str = DEMO_TENANT, contract_id: str | None = None
    ) -> list[ExtractedClause]: ...

    @abc.abstractmethod
    def vector_search_similar_clauses(
        self,
        embedding: list[float],
        tenant_id: str = DEMO_TENANT,
        top_k: int = 5,
        exclude_clause_id: str | None = None,
        contract_id: str | None = None,
    ) -> list[dict]:
        """Each dict: {clause_id, contract_id, clause_type, raw_text, page_number,
        similarity}. ``contract_id`` restricts the search to one contract
        (Phase 4's single-document questions), scored directly against just
        that contract's clauses (no approximate global top-K involved);
        ``None`` searches the whole tenant via the vector index."""

    @abc.abstractmethod
    def list_contracts(self, tenant_id: str = DEMO_TENANT) -> list[dict]:
        """Every contract in the tenant, most-recently-uploaded first. Each
        dict: {contract_id, filename}. Callers that pick "the" contract for a
        given filename (e.g. Ask's name matching) rely on this ordering to
        prefer the newest upload when the same filename was ingested more
        than once."""

    @abc.abstractmethod
    def get_override_relationships(
        self, clause_id: str, tenant_id: str = DEMO_TENANT
    ) -> list[dict]:
        """Direct (1-hop) OVERRIDES edges in both directions. Each dict:
        {clause_id, raw_text, page_number, scope, direction} where direction is
        'overrides' (this clause overrides it) or 'overridden_by'."""

    @abc.abstractmethod
    def get_compliance_targets(
        self, clause_id: str, tenant_id: str = DEMO_TENANT
    ) -> list[dict]:
        """The PlaybookRule/RegulationClause node(s) this clause was flagged
        against by Detect. Each dict: {rel_type, target_id, label, text}."""

    def ensure_vector_index(self) -> None:
        """Create the Neo4j vector index if it doesn't exist. No-op for the
        in-memory store (brute-force cosine search needs no index)."""
        return None


# ======================================================================= #
# In-memory implementation (mocked test suite)
# ======================================================================= #
class InMemoryGraphStore(GraphStore):
    def __init__(self) -> None:
        self.playbook: dict[str, dict] = {}
        self.regulations: dict[str, dict] = {}
        self.contracts: dict[tuple[str, str], dict] = {}
        self.clauses: dict[tuple[str, str], ExtractedClause] = {}
        self.overrides: list[dict] = []  # {src, dst, scope, tenant_id}
        self.findings: dict[tuple[str, str], list[Finding]] = {}
        self.compliance_edges: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        self.detect_runs: dict[tuple[str, str], str] = {}

    def seed_playbook_rules(self, rules, tenant_id=DEMO_TENANT):
        for r in rules:
            self.playbook[r["id"]] = {**r, "tenant_id": tenant_id}

    def seed_regulation_clauses(self, clauses):
        for c in clauses:
            self.regulations[c["id"]] = dict(c)

    def get_playbook_rules(self, tenant_id=DEMO_TENANT):
        return [r for r in self.playbook.values() if r["tenant_id"] == tenant_id]

    def get_regulation_clauses(self):
        return list(self.regulations.values())

    def add_regulation_update(self, regulation_name, new_clause_text, effective_date):
        new_id = f"reg_{uuid.uuid4().hex[:12]}"
        clause = {
            "id": new_id,
            "regulation_name": regulation_name,
            "section": f"Amendment effective {effective_date}",
            "text": new_clause_text,
            "effective_date": effective_date,
        }
        self.regulations[new_id] = clause
        return clause

    def upsert_contract(self, contract_id, filename, tenant_id=DEMO_TENANT):
        self.contracts[(tenant_id, contract_id)] = {
            "id": contract_id,
            "filename": filename,
            "tenant_id": tenant_id,
            "upload_date": datetime.now(timezone.utc).isoformat(),
        }

    def add_clause(self, clause, tenant_id=DEMO_TENANT):
        self.clauses[(tenant_id, clause.clause_id)] = clause

    def add_override(self, src_clause_id, dst_clause_id, scope, tenant_id=DEMO_TENANT):
        self.overrides.append(
            {"src": src_clause_id, "dst": dst_clause_id, "scope": scope, "tenant_id": tenant_id}
        )

    def contract_exists(self, contract_id, tenant_id=DEMO_TENANT):
        return (tenant_id, contract_id) in self.contracts

    def get_clauses_for_contract(self, contract_id, tenant_id=DEMO_TENANT):
        return [
            c
            for (t, _), c in self.clauses.items()
            if t == tenant_id and c.contract_id == contract_id
        ]

    def get_overriders(self, clause_id, max_hops=3, tenant_id=DEMO_TENANT):
        # BFS over incoming OVERRIDES edges: src OVERRIDES dst  =>  from dst, follow to src
        adj: dict[str, list[dict]] = {}
        for e in self.overrides:
            if e["tenant_id"] != tenant_id:
                continue
            adj.setdefault(e["dst"], []).append(e)

        seen = {clause_id}
        out: list[dict] = []
        queue: deque[tuple[str, int]] = deque([(clause_id, 0)])
        while queue:
            node, hops = queue.popleft()
            if hops >= max_hops:
                continue
            for e in adj.get(node, []):
                src = e["src"]
                if src in seen:
                    continue
                seen.add(src)
                clause = self.clauses.get((tenant_id, src))
                if clause is None:
                    continue
                out.append(
                    {
                        "id": src,
                        "page_number": clause.page_number,
                        "raw_text": clause.raw_text,
                        "scope": e["scope"],
                        "hops": hops + 1,
                    }
                )
                queue.append((src, hops + 1))
        out.sort(key=lambda d: d["hops"])
        return out

    def replace_findings(self, contract_id, findings, tenant_id=DEMO_TENANT):
        self.findings[(tenant_id, contract_id)] = list(findings)

    def add_findings(self, contract_id, findings, tenant_id=DEMO_TENANT):
        existing = self.findings.setdefault((tenant_id, contract_id), [])
        existing_ids = {f.finding_id for f in existing}
        new = [f for f in findings if f.finding_id not in existing_ids]
        existing.extend(new)
        return new

    def get_findings(self, contract_id, tenant_id=DEMO_TENANT):
        return list(self.findings.get((tenant_id, contract_id), []))

    def get_all_findings(self, tenant_id=DEMO_TENANT):
        out: list[dict] = []
        for (t, contract_id), findings in self.findings.items():
            if t != tenant_id:
                continue
            for f in findings:
                out.append(
                    {
                        "finding_id": f.finding_id,
                        "contract_id": contract_id,
                        "clause_id": f.clause_id,
                        "severity": f.severity.value,
                        "rule_or_regulation_violated": f.rule_or_regulation_violated,
                    }
                )
        return out

    def write_compliance_edges(self, contract_id, edges, tenant_id=DEMO_TENANT):
        self.compliance_edges[(tenant_id, contract_id)] = list(edges)

    def record_detect_run(self, contract_id, timestamp, tenant_id=DEMO_TENANT):
        self.detect_runs[(tenant_id, contract_id)] = timestamp

    def get_detect_run(self, contract_id, tenant_id=DEMO_TENANT):
        return self.detect_runs.get((tenant_id, contract_id))

    # --- Suggest agent support (Phase 2) --------------------------
    def get_clause_by_id(self, clause_id, tenant_id=DEMO_TENANT):
        return self.clauses.get((tenant_id, clause_id))

    def find_finding_by_id(self, finding_id, tenant_id=DEMO_TENANT):
        for (t, _cid), findings in self.findings.items():
            if t != tenant_id:
                continue
            for f in findings:
                if f.finding_id == finding_id:
                    return f
        return None

    def set_clause_embedding(self, clause_id, embedding, tenant_id=DEMO_TENANT):
        clause = self.clauses.get((tenant_id, clause_id))
        if clause is not None:
            clause.embedding = list(embedding)

    def get_clauses_missing_embedding(self, tenant_id=DEMO_TENANT, contract_id=None):
        return [
            c
            for (t, _), c in self.clauses.items()
            if t == tenant_id
            and c.embedding is None
            and (contract_id is None or c.contract_id == contract_id)
        ]

    def vector_search_similar_clauses(
        self, embedding, tenant_id=DEMO_TENANT, top_k=5, exclude_clause_id=None, contract_id=None
    ):
        scored = []
        for (t, cid), c in self.clauses.items():
            if t != tenant_id or c.embedding is None or cid == exclude_clause_id:
                continue
            if contract_id is not None and c.contract_id != contract_id:
                continue
            scored.append(
                {
                    "clause_id": c.clause_id,
                    "contract_id": c.contract_id,
                    "clause_type": c.clause_type.value,
                    "raw_text": c.raw_text,
                    "page_number": c.page_number,
                    "similarity": _cosine_similarity(embedding, c.embedding),
                }
            )
        scored.sort(key=lambda d: d["similarity"], reverse=True)
        return scored[:top_k]

    def list_contracts(self, tenant_id=DEMO_TENANT):
        matches = [c for (t, _), c in self.contracts.items() if t == tenant_id]
        matches.sort(key=lambda c: c["upload_date"], reverse=True)
        return [{"contract_id": c["id"], "filename": c["filename"]} for c in matches]

    def get_override_relationships(self, clause_id, tenant_id=DEMO_TENANT):
        out: list[dict] = []
        for e in self.overrides:
            if e["tenant_id"] != tenant_id:
                continue
            if e["src"] == clause_id:
                target = self.clauses.get((tenant_id, e["dst"]))
                if target:
                    out.append(
                        {
                            "clause_id": target.clause_id,
                            "raw_text": target.raw_text,
                            "page_number": target.page_number,
                            "scope": e["scope"],
                            "direction": "overrides",
                        }
                    )
            elif e["dst"] == clause_id:
                source = self.clauses.get((tenant_id, e["src"]))
                if source:
                    out.append(
                        {
                            "clause_id": source.clause_id,
                            "raw_text": source.raw_text,
                            "page_number": source.page_number,
                            "scope": e["scope"],
                            "direction": "overridden_by",
                        }
                    )
        return out

    def get_compliance_targets(self, clause_id, tenant_id=DEMO_TENANT):
        out: list[dict] = []
        for (t, _cid), edges in self.compliance_edges.items():
            if t != tenant_id:
                continue
            for edge_clause_id, rel_type, target_id in edges:
                if edge_clause_id != clause_id:
                    continue
                if rel_type == "VIOLATES":
                    reg = self.regulations.get(target_id)
                    if reg:
                        out.append(
                            {
                                "rel_type": rel_type,
                                "target_id": target_id,
                                "label": f"{reg['regulation_name']} {reg['section']}",
                                "text": reg["text"],
                            }
                        )
                else:
                    rule = self.playbook.get(target_id)
                    if rule:
                        out.append(
                            {
                                "rel_type": rel_type,
                                "target_id": target_id,
                                "label": f"Playbook: {target_id}",
                                "text": rule["rule_text"],
                            }
                        )
        return out

    def wipe_contract(self, contract_id, tenant_id=DEMO_TENANT):
        self.contracts.pop((tenant_id, contract_id), None)
        self.findings.pop((tenant_id, contract_id), None)
        self.compliance_edges.pop((tenant_id, contract_id), None)
        self.detect_runs.pop((tenant_id, contract_id), None)
        doomed = [
            key
            for key, c in self.clauses.items()
            if key[0] == tenant_id and c.contract_id == contract_id
        ]
        clause_ids = {key[1] for key in doomed}
        for key in doomed:
            self.clauses.pop(key, None)
        self.overrides = [
            e
            for e in self.overrides
            if not (e["tenant_id"] == tenant_id and (e["src"] in clause_ids or e["dst"] in clause_ids))
        ]


# ======================================================================= #
# Neo4j implementation
# ======================================================================= #
class Neo4jGraphStore(GraphStore):
    def __init__(self, driver: Any | None = None) -> None:
        if driver is None:
            from app.db.neo4j_client import get_driver

            driver = get_driver()
        self._driver = driver

    def _run(self, cypher: str, **params: Any) -> list[dict]:
        with self._driver.session() as session:
            return [r.data() for r in session.run(cypher, **params)]

    # --- seeding -----------------------------------------------------------
    def seed_playbook_rules(self, rules, tenant_id=DEMO_TENANT):
        self._run(
            """
            UNWIND $rules AS rule
            MERGE (p:PlaybookRule {id: rule.id, tenant_id: $tenant_id})
            SET p.rule_text = rule.rule_text, p.category = rule.category
            """,
            rules=rules,
            tenant_id=tenant_id,
        )

    def seed_regulation_clauses(self, clauses):
        self._run(
            """
            UNWIND $clauses AS rc
            MERGE (r:RegulationClause {id: rc.id})
            SET r.regulation_name = rc.regulation_name,
                r.section = rc.section,
                r.text = rc.text
            """,
            clauses=clauses,
        )

    def get_playbook_rules(self, tenant_id=DEMO_TENANT):
        return self._run(
            "MATCH (p:PlaybookRule {tenant_id: $tenant_id}) "
            "RETURN p.id AS id, p.rule_text AS rule_text, p.category AS category",
            tenant_id=tenant_id,
        )

    def get_regulation_clauses(self):
        return self._run(
            "MATCH (r:RegulationClause) "
            "RETURN r.id AS id, r.regulation_name AS regulation_name, "
            "r.section AS section, r.text AS text, r.effective_date AS effective_date"
        )

    def add_regulation_update(self, regulation_name, new_clause_text, effective_date):
        new_id = f"reg_{uuid.uuid4().hex[:12]}"
        section = f"Amendment effective {effective_date}"
        self._run(
            """
            CREATE (r:RegulationClause {
                id: $id, regulation_name: $regulation_name, section: $section,
                text: $text, effective_date: $effective_date
            })
            """,
            id=new_id,
            regulation_name=regulation_name,
            section=section,
            text=new_clause_text,
            effective_date=effective_date,
        )
        return {
            "id": new_id,
            "regulation_name": regulation_name,
            "section": section,
            "text": new_clause_text,
            "effective_date": effective_date,
        }

    # --- contract / clause writes ---------------------------------------
    def upsert_contract(self, contract_id, filename, tenant_id=DEMO_TENANT):
        self._run(
            """
            MERGE (c:Contract {id: $id, tenant_id: $tenant_id})
            SET c.filename = $filename,
                c.upload_date = coalesce(c.upload_date, datetime())
            """,
            id=contract_id,
            filename=filename,
            tenant_id=tenant_id,
        )

    def add_clause(self, clause, tenant_id=DEMO_TENANT):
        self._run(
            """
            MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})
            MERGE (cl:Clause {id: $clause_id, tenant_id: $tenant_id})
            SET cl.contract_id = $contract_id,
                cl.clause_type = $clause_type,
                cl.page_number = $page_number,
                cl.section_header = $section_header,
                cl.raw_text = $raw_text,
                cl.confidence = $confidence
            MERGE (cl)-[:BELONGS_TO]->(c)
            """,
            contract_id=clause.contract_id,
            clause_id=clause.clause_id,
            clause_type=clause.clause_type.value,
            page_number=clause.page_number,
            section_header=clause.section_header,
            raw_text=clause.raw_text,
            confidence=clause.confidence.value,
            tenant_id=tenant_id,
        )

    def add_override(self, src_clause_id, dst_clause_id, scope, tenant_id=DEMO_TENANT):
        self._run(
            """
            MATCH (a:Clause {id: $src, tenant_id: $tenant_id})
            MATCH (b:Clause {id: $dst, tenant_id: $tenant_id})
            MERGE (a)-[r:OVERRIDES]->(b)
            SET r.scope = $scope
            """,
            src=src_clause_id,
            dst=dst_clause_id,
            scope=scope,
            tenant_id=tenant_id,
        )

    # --- reads ---------------------------------------------------------
    def contract_exists(self, contract_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            "MATCH (c:Contract {id: $id, tenant_id: $tenant_id}) RETURN count(c) AS n",
            id=contract_id,
            tenant_id=tenant_id,
        )
        return bool(rows and rows[0]["n"] > 0)

    def get_clauses_for_contract(self, contract_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (cl:Clause {contract_id: $contract_id, tenant_id: $tenant_id})
            RETURN cl.id AS clause_id, cl.contract_id AS contract_id,
                   cl.clause_type AS clause_type, cl.page_number AS page_number,
                   cl.section_header AS section_header, cl.raw_text AS raw_text,
                   cl.confidence AS confidence
            ORDER BY cl.page_number, cl.id
            """,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )
        return [ExtractedClause.model_validate(r) for r in rows]

    def get_overriders(self, clause_id, max_hops=3, tenant_id=DEMO_TENANT):
        cypher = f"""
            MATCH (start:Clause {{id: $id, tenant_id: $tenant_id}})
            MATCH p = (o:Clause)-[rels:OVERRIDES*1..{int(max_hops)}]->(start)
            WHERE all(x IN nodes(p) WHERE x.tenant_id = $tenant_id)
            RETURN o.id AS id, o.page_number AS page_number, o.raw_text AS raw_text,
                   rels[0].scope AS scope, size(rels) AS hops
            ORDER BY hops
        """
        return self._run(cypher, id=clause_id, tenant_id=tenant_id)

    # --- findings ----------------------------------------------------
    def replace_findings(self, contract_id, findings, tenant_id=DEMO_TENANT):
        # idempotent: drop existing findings + derived edges for this contract first
        self._run(
            """
            MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})-[:HAS_FINDING]->(f:Finding)
            DETACH DELETE f
            """,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )
        self._run(
            """
            MATCH (cl:Clause {contract_id: $contract_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (cl)-[v:VIOLATES]->(:RegulationClause)
            OPTIONAL MATCH (cl)-[x:CONTRADICTS]->(:PlaybookRule)
            DELETE v, x
            """,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )
        for f in findings:
            self._run(
                """
                MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})
                MATCH (cl:Clause {id: $clause_id, tenant_id: $tenant_id})
                CREATE (f:Finding {
                    id: $finding_id, clause_id: $clause_id, clause_type: $clause_type,
                    page_number: $page_number, section_header: $section_header,
                    severity: $severity, rule_or_regulation_violated: $rule,
                    explanation: $explanation, confidence: $confidence,
                    override_chain: $override_chain, tenant_id: $tenant_id
                })
                CREATE (c)-[:HAS_FINDING]->(f)
                CREATE (f)-[:ABOUT]->(cl)
                """,
                contract_id=contract_id,
                clause_id=f.clause_id,
                finding_id=f.finding_id,
                clause_type=f.clause_type.value,
                page_number=f.page_number,
                section_header=f.section_header,
                severity=f.severity.value,
                rule=f.rule_or_regulation_violated,
                explanation=f.explanation,
                confidence=f.confidence.value,
                override_chain=f.override_chain,
                tenant_id=tenant_id,
            )

    def add_findings(self, contract_id, findings, tenant_id=DEMO_TENANT):
        existing_ids = {
            r["id"]
            for r in self._run(
                "MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})-[:HAS_FINDING]->(f:Finding) "
                "RETURN f.id AS id",
                contract_id=contract_id,
                tenant_id=tenant_id,
            )
        }
        new = [f for f in findings if f.finding_id not in existing_ids]
        for f in new:
            self._run(
                """
                MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})
                MATCH (cl:Clause {id: $clause_id, tenant_id: $tenant_id})
                CREATE (f:Finding {
                    id: $finding_id, clause_id: $clause_id, clause_type: $clause_type,
                    page_number: $page_number, section_header: $section_header,
                    severity: $severity, rule_or_regulation_violated: $rule,
                    explanation: $explanation, confidence: $confidence,
                    override_chain: $override_chain, tenant_id: $tenant_id
                })
                CREATE (c)-[:HAS_FINDING]->(f)
                CREATE (f)-[:ABOUT]->(cl)
                """,
                contract_id=contract_id,
                clause_id=f.clause_id,
                finding_id=f.finding_id,
                clause_type=f.clause_type.value,
                page_number=f.page_number,
                section_header=f.section_header,
                severity=f.severity.value,
                rule=f.rule_or_regulation_violated,
                explanation=f.explanation,
                confidence=f.confidence.value,
                override_chain=f.override_chain,
                tenant_id=tenant_id,
            )
        return new

    def get_findings(self, contract_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})-[:HAS_FINDING]->(f:Finding)
            RETURN f.id AS finding_id, f.clause_id AS clause_id, f.clause_type AS clause_type,
                   f.page_number AS page_number, f.section_header AS section_header,
                   f.severity AS severity, f.rule_or_regulation_violated AS rule_or_regulation_violated,
                   f.explanation AS explanation, f.confidence AS confidence,
                   f.override_chain AS override_chain
            ORDER BY f.id
            """,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )
        out: list[Finding] = []
        for r in rows:
            r = dict(r)
            r["override_chain"] = r.get("override_chain") or []
            out.append(Finding.model_validate(r))
        return out

    def get_all_findings(self, tenant_id=DEMO_TENANT):
        return self._run(
            """
            MATCH (c:Contract {tenant_id: $tenant_id})-[:HAS_FINDING]->(f:Finding)
            RETURN f.id AS finding_id, c.id AS contract_id, f.clause_id AS clause_id,
                   f.severity AS severity, f.rule_or_regulation_violated AS rule_or_regulation_violated
            """,
            tenant_id=tenant_id,
        )

    def write_compliance_edges(self, contract_id, edges, tenant_id=DEMO_TENANT):
        for clause_id, rel_type, target_id in edges:
            if rel_type == "VIOLATES":
                self._run(
                    """
                    MATCH (cl:Clause {id: $clause_id, tenant_id: $tenant_id})
                    MATCH (r:RegulationClause {id: $target_id})
                    MERGE (cl)-[:VIOLATES]->(r)
                    """,
                    clause_id=clause_id,
                    target_id=target_id,
                    tenant_id=tenant_id,
                )
            elif rel_type == "CONTRADICTS":
                self._run(
                    """
                    MATCH (cl:Clause {id: $clause_id, tenant_id: $tenant_id})
                    MATCH (p:PlaybookRule {id: $target_id, tenant_id: $tenant_id})
                    MERGE (cl)-[:CONTRADICTS]->(p)
                    """,
                    clause_id=clause_id,
                    target_id=target_id,
                    tenant_id=tenant_id,
                )

    def record_detect_run(self, contract_id, timestamp, tenant_id=DEMO_TENANT):
        self._run(
            "MATCH (c:Contract {id: $id, tenant_id: $tenant_id}) "
            "SET c.detect_completed_at = $ts",
            id=contract_id,
            ts=timestamp,
            tenant_id=tenant_id,
        )

    def get_detect_run(self, contract_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            "MATCH (c:Contract {id: $id, tenant_id: $tenant_id}) "
            "RETURN c.detect_completed_at AS ts",
            id=contract_id,
            tenant_id=tenant_id,
        )
        return rows[0]["ts"] if rows and rows[0].get("ts") else None

    def wipe_contract(self, contract_id, tenant_id=DEMO_TENANT):
        self._run(
            """
            MATCH (c:Contract {id: $contract_id, tenant_id: $tenant_id})
            OPTIONAL MATCH (c)-[:HAS_FINDING]->(f:Finding)
            OPTIONAL MATCH (cl:Clause {contract_id: $contract_id, tenant_id: $tenant_id})
            DETACH DELETE c, f, cl
            """,
            contract_id=contract_id,
            tenant_id=tenant_id,
        )

    # --- Suggest agent support (Phase 2) --------------------------
    def get_clause_by_id(self, clause_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (cl:Clause {id: $id, tenant_id: $tenant_id})
            RETURN cl.id AS clause_id, cl.contract_id AS contract_id,
                   cl.clause_type AS clause_type, cl.page_number AS page_number,
                   cl.section_header AS section_header, cl.raw_text AS raw_text,
                   cl.confidence AS confidence, cl.embedding AS embedding
            """,
            id=clause_id,
            tenant_id=tenant_id,
        )
        return ExtractedClause.model_validate(rows[0]) if rows else None

    def find_finding_by_id(self, finding_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (f:Finding {id: $id, tenant_id: $tenant_id})
            RETURN f.id AS finding_id, f.clause_id AS clause_id, f.clause_type AS clause_type,
                   f.page_number AS page_number, f.section_header AS section_header,
                   f.severity AS severity, f.rule_or_regulation_violated AS rule_or_regulation_violated,
                   f.explanation AS explanation, f.confidence AS confidence,
                   f.override_chain AS override_chain
            """,
            id=finding_id,
            tenant_id=tenant_id,
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["override_chain"] = row.get("override_chain") or []
        return Finding.model_validate(row)

    def set_clause_embedding(self, clause_id, embedding, tenant_id=DEMO_TENANT):
        self._run(
            "MATCH (cl:Clause {id: $id, tenant_id: $tenant_id}) SET cl.embedding = $embedding",
            id=clause_id,
            tenant_id=tenant_id,
            embedding=list(embedding),
        )

    def get_clauses_missing_embedding(self, tenant_id=DEMO_TENANT, contract_id=None):
        cypher = (
            "MATCH (cl:Clause {tenant_id: $tenant_id}) WHERE cl.embedding IS NULL "
            + ("AND cl.contract_id = $contract_id " if contract_id else "")
            + "RETURN cl.id AS clause_id, cl.contract_id AS contract_id, cl.clause_type AS clause_type, "
            "cl.page_number AS page_number, cl.section_header AS section_header, "
            "cl.raw_text AS raw_text, cl.confidence AS confidence"
        )
        params = {"tenant_id": tenant_id}
        if contract_id:
            params["contract_id"] = contract_id
        rows = self._run(cypher, **params)
        return [ExtractedClause.model_validate(r) for r in rows]

    def ensure_vector_index(self) -> None:
        self._run(
            f"""
            CREATE VECTOR INDEX clause_embeddings IF NOT EXISTS
            FOR (cl:Clause) ON (cl.embedding)
            OPTIONS {{ indexConfig: {{
                `vector.dimensions`: {int(settings.embedding_dimensions)},
                `vector.similarity_function`: 'cosine'
            }} }}
            """
        )

    def vector_search_similar_clauses(
        self, embedding, tenant_id=DEMO_TENANT, top_k=5, exclude_clause_id=None, contract_id=None
    ):
        # A single-document search only ever needs to rank ONE contract's own
        # (small, bounded) clause set — over-fetching from the GLOBAL vector
        # index and filtering afterward doesn't scale: once the tenant's total
        # embedded-clause count grows well past the over-fetch window, this
        # contract's clauses may simply not be among the globally-nearest
        # neighbours at all, silently returning zero hits for a document that
        # is, in fact, relevant. Score this contract's clauses directly
        # instead — no index, no global top-K, so no starvation is possible.
        if contract_id is not None:
            rows = self._run(
                """
                MATCH (n:Clause {tenant_id: $tenant_id, contract_id: $contract_id})
                WHERE n.embedding IS NOT NULL AND n.id <> coalesce($exclude, '')
                RETURN n.id AS clause_id, n.contract_id AS contract_id,
                       n.clause_type AS clause_type, n.raw_text AS raw_text,
                       n.page_number AS page_number, n.embedding AS embedding
                """,
                tenant_id=tenant_id,
                contract_id=contract_id,
                exclude=exclude_clause_id,
            )
            scored = [
                {**{k: v for k, v in r.items() if k != "embedding"}, "similarity": _cosine_similarity(embedding, r["embedding"])}
                for r in rows
            ]
            scored.sort(key=lambda d: d["similarity"], reverse=True)
            return scored[:top_k]

        self.ensure_vector_index()
        # Portfolio-wide search: the vector index returns its top-K matches
        # globally before the WHERE filter below applies, so over-fetch to
        # keep the filtered result close to top_k in the common case (this is
        # an approximate mitigation, not a guarantee, for a tenant-wide scan).
        fetch_k = min(max(top_k * 5, 25), 200)
        rows = self._run(
            """
            CALL db.index.vector.queryNodes('clause_embeddings', $fetch_k, $embedding)
            YIELD node, score
            WHERE node.tenant_id = $tenant_id AND node.id <> coalesce($exclude, '')
            RETURN node.id AS clause_id, node.contract_id AS contract_id,
                   node.clause_type AS clause_type, node.raw_text AS raw_text,
                   node.page_number AS page_number, score AS similarity
            ORDER BY similarity DESC
            LIMIT $top_k
            """,
            fetch_k=fetch_k,
            top_k=top_k,
            embedding=list(embedding),
            tenant_id=tenant_id,
            exclude=exclude_clause_id,
        )
        return rows

    def list_contracts(self, tenant_id=DEMO_TENANT):
        return self._run(
            "MATCH (c:Contract {tenant_id: $tenant_id}) "
            "RETURN c.id AS contract_id, c.filename AS filename "
            "ORDER BY c.upload_date DESC",
            tenant_id=tenant_id,
        )

    def get_override_relationships(self, clause_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (cl:Clause {id: $id, tenant_id: $tenant_id})
            OPTIONAL MATCH (cl)-[ro:OVERRIDES]->(overridden:Clause)
            OPTIONAL MATCH (overrider:Clause)-[ri:OVERRIDES]->(cl)
            RETURN collect(DISTINCT {clause_id: overridden.id, raw_text: overridden.raw_text,
                                      page_number: overridden.page_number, scope: ro.scope,
                                      direction: 'overrides'}) AS forward,
                   collect(DISTINCT {clause_id: overrider.id, raw_text: overrider.raw_text,
                                      page_number: overrider.page_number, scope: ri.scope,
                                      direction: 'overridden_by'}) AS backward
            """,
            id=clause_id,
            tenant_id=tenant_id,
        )
        if not rows:
            return []
        forward = [r for r in rows[0]["forward"] if r.get("clause_id")]
        backward = [r for r in rows[0]["backward"] if r.get("clause_id")]
        return forward + backward

    def get_compliance_targets(self, clause_id, tenant_id=DEMO_TENANT):
        rows = self._run(
            """
            MATCH (cl:Clause {id: $id, tenant_id: $tenant_id})
            OPTIONAL MATCH (cl)-[:VIOLATES]->(reg:RegulationClause)
            OPTIONAL MATCH (cl)-[:CONTRADICTS]->(pb:PlaybookRule)
            RETURN collect(DISTINCT {rel_type: 'VIOLATES', target_id: reg.id,
                                      label: reg.regulation_name + ' ' + reg.section,
                                      text: reg.text}) AS regs,
                   collect(DISTINCT {rel_type: 'CONTRADICTS', target_id: pb.id,
                                      label: 'Playbook: ' + pb.id,
                                      text: pb.rule_text}) AS rules
            """,
            id=clause_id,
            tenant_id=tenant_id,
        )
        if not rows:
            return []
        regs = [r for r in rows[0]["regs"] if r.get("target_id")]
        rules = [r for r in rows[0]["rules"] if r.get("target_id")]
        return regs + rules


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_graph_store() -> GraphStore:
    """Return the production graph store (Neo4j)."""
    return Neo4jGraphStore()
