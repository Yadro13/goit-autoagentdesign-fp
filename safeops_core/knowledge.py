"""Persistent ChromaDB knowledge base із sanitized Riverwash runbooks."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb

RUNBOOKS: list[dict[str, str]] = [
    {
        "id": "RB-001",
        "topic": "health",
        "text": (
            "Readiness, heartbeat freshness and a successful cycle define healthy state. "
            "Historical recovered errors are not active incidents."
        ),
    },
    {
        "id": "RB-002",
        "topic": "queues",
        "text": (
            "Inspect pending, retry, dead, oldest age and attempts. Growing backlog or any "
            "dead job requires operator attention."
        ),
    },
    {
        "id": "RB-003",
        "topic": "integrity",
        "text": (
            "Balance must stay non-negative, reserved cannot exceed balance, every outcome "
            "requires a ledger record, and projections cannot remain stuck."
        ),
    },
    {
        "id": "RB-004",
        "topic": "remediation",
        "text": (
            "Retry exactly one verified job with expected status, idempotency key and human "
            "approval. Bulk retry is prohibited."
        ),
    },
    {
        "id": "RB-005",
        "topic": "incident",
        "text": (
            "Classify active failures separately from recovered events. Stale state, dead jobs "
            "and integrity violations require attention."
        ),
    },
    {
        "id": "RB-006",
        "topic": "security",
        "text": (
            "Never send customer contacts, tokens, raw payloads or production URLs to an LLM "
            "or trajectory. Use sanitized categories and aggregates."
        ),
    },
    {
        "id": "RB-007",
        "topic": "crm",
        "text": (
            "Token health is determined from TTL and lock metadata without reading token "
            "values. Repeated refresh failures require escalation."
        ),
    },
    {
        "id": "RB-008",
        "topic": "notifications",
        "text": (
            "A handled terminal recipient error with fallback is recovered; an unhandled "
            "repeated send failure is active."
        ),
    },
    {
        "id": "RB-009",
        "topic": "change",
        "text": (
            "Read-only API migration may use fallback. Writes require an explicit compensation "
            "contract and tested rollback."
        ),
    },
    {
        "id": "RB-010",
        "topic": "hitl",
        "text": (
            "Side effects require approve, reject or edit. Edited arguments are fully "
            "revalidated and approval is bound to one action."
        ),
    },
]


def _embed(text: str, dimensions: int = 384) -> list[float]:
    tokens = re.findall(r"[\w'-]+", text.casefold())
    features = tokens + [f"{token[i : i + 3]}#3" for token in tokens for i in range(max(1, len(token) - 2))]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        vector[int.from_bytes(digest[:4], "little") % dimensions] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[\w'-]+", text.casefold()) if len(term) >= 3}


@dataclass
class KnowledgeBase:
    path: Path
    collection_name: str = "riverwash_safeops_runbooks"

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.path))
        self._collection = self._client.get_or_create_collection(
            self.collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._collection.upsert(
            ids=[item["id"] for item in RUNBOOKS],
            documents=[item["text"] for item in RUNBOOKS],
            metadatas=[{"topic": item["topic"]} for item in RUNBOOKS],
            embeddings=[_embed(item["text"]) for item in RUNBOOKS],
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        result = self._collection.query(
            query_embeddings=[_embed(query)],
            n_results=self.count,
            include=["documents", "metadatas", "distances"],
        )
        query_terms = _terms(query)
        ranked: list[dict[str, Any]] = []
        for doc_id, document, metadata, distance in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
            strict=True,
        ):
            lexical = len(query_terms & _terms(document)) / max(1, len(query_terms))
            score = 0.55 * max(0.0, 1.0 - float(distance)) + 0.45 * lexical
            ranked.append(
                {"id": doc_id, "topic": metadata["topic"], "text": document, "score": round(score, 4)}
            )
        ranked.sort(key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]

    def catalog(self) -> list[dict[str, str]]:
        return [{"id": item["id"], "topic": item["topic"]} for item in RUNBOOKS]
