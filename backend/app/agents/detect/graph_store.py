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
    def get_findings(
        self, contract_id: str, tenant_id: str = DEMO_TENANT
    ) -> list[Finding]: ...

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

    def get_findings(self, contract_id, tenant_id=DEMO_TENANT):
        return list(self.findings.get((tenant_id, contract_id), []))

    def write_compliance_edges(self, contract_id, edges, tenant_id=DEMO_TENANT):
        self.compliance_edges[(tenant_id, contract_id)] = list(edges)

    def record_detect_run(self, contract_id, timestamp, tenant_id=DEMO_TENANT):
        self.detect_runs[(tenant_id, contract_id)] = timestamp

    def get_detect_run(self, contract_id, tenant_id=DEMO_TENANT):
        return self.detect_runs.get((tenant_id, contract_id))

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
            "r.section AS section, r.text AS text"
        )

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


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_graph_store() -> GraphStore:
    """Return the production graph store (Neo4j)."""
    return Neo4jGraphStore()
