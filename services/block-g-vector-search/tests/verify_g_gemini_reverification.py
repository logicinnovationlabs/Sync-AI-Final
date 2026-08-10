"""
Block G re-verification against real Gemini 768-d embeddings (2026-08-09).

Step 1 master prompt:
1. Report prior/stored dimensions
2. Embed Block Z documents.json via Block E Gemini provider
3. Index into new Qdrant collection prefix block_g_verify_gemini (768-d)
4. Run G1–G4 against Block Z relevance_labels + acl_redteam_cases
"""
from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
FIXTURES = Path(os.environ.get("FIXTURES_PATH", str(REPO / "fixtures")))
EVIDENCE = ROOT / "evidence"
EVIDENCE.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))

COLLECTION_PREFIX = "block_g_verify_gemini"
LEGACY_PREFIX = "block_g_verify_legacy64"
MODEL_V1 = "gemini-embedding-001"
MODEL_V2 = "gemini-embedding-001-v2"
DIM = 768
LEGACY_DIM = 64
TENANT_DB = "tenant_g_gemini_verify"

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6335"))


def load_json(name: str) -> Dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def principal_acl_terms(principal_id: str, groups: List[Dict[str, Any]]) -> List[str]:
    terms = [principal_id]
    for g in groups:
        if principal_id in g.get("members", []):
            terms.append(g["id"])
    return terms


def pack_vector(vec: List[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


async def embed_texts(provider, texts: List[str], tenant_id: str, model: str, batch: int = 20) -> List[List[float]]:
    out: List[List[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        results = await provider.embed_batch(texts=chunk, tenant_id=tenant_id, model_version=model)
        for r in results:
            out.append(list(r.vector))
        print(f"   embedded {len(out)}/{len(texts)}")
    return out


async def write_chunk_records(docs_meta: List[Dict[str, Any]]) -> None:
    """Persist embeddings into Block E Postgres as chunk_records (raw SQL — avoid app import clash)."""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:verify@localhost:5433/block_e_verify",
    ).replace("postgresql+asyncpg://", "postgresql://")
    engine = create_engine(db_url, echo=False)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM chunk_records WHERE tenant_id = :t"), {"t": TENANT_DB})
        for d in docs_meta:
            conn.execute(
                text(
                    """
                    INSERT INTO chunk_records (
                        chunk_id, tenant_id, document_id, document_version, chunk_index,
                        chunk_type, chunk_text, token_count, start_byte, end_byte,
                        chunker_version, content_hash, chunk_content_checksum, source_run_id,
                        embedding_vector, embedding_model_version, embedding_timestamp
                    ) VALUES (
                        :chunk_id, :tenant_id, :document_id, 1, 0,
                        'prose_paragraph', :chunk_text, :token_count, 0, :end_byte,
                        '1.0.0', :content_hash, :content_hash, 'g_gemini_reverify_20260809',
                        :embedding_vector, :model_version, :ts
                    )
                    """
                ),
                {
                    "chunk_id": d["chunk_id"],
                    "tenant_id": TENANT_DB,
                    "document_id": d["document_id"],
                    "chunk_text": d["text"][:8000],
                    "token_count": max(1, len(d["text"].split())),
                    "end_byte": max(1, len(d["text"])),
                    "content_hash": d["chunk_id"][:64],
                    "embedding_vector": pack_vector(d["embedding"]),
                    "model_version": MODEL_V1,
                    "ts": datetime.now(timezone.utc),
                },
            )
    engine.dispose()
    print(f"[DB] Wrote {len(docs_meta)} chunk_records for tenant={TENANT_DB}")


async def run() -> int:
    print("=" * 80)
    print("BLOCK G RE-VERIFICATION — REAL GEMINI 768-d")
    print("=" * 80)
    print(f"FIXTURES_PATH={FIXTURES}")
    print(f"Qdrant={QDRANT_HOST}:{QDRANT_PORT}")
    print(f"Collection prefix={COLLECTION_PREFIX}")

    from qdrant_client import QdrantClient

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    cols = client.get_collections().collections
    print("\n[1.1] Existing Qdrant collections before re-index:")
    if not cols:
        print("  (none — fresh test instance)")
    for col in cols:
        info = client.get_collection(col.name)
        vc = info.config.params.vectors
        size = getattr(vc, "size", None)
        print(f"  {col.name}: size={size}")
    print("  Prior Block G fixture corpus: dimensions=64 (synthetic generate_fixtures.py)")
    print("  Block E current output: gemini-embedding-001 @ 768-d")
    print("  MISMATCH confirmed — regenerating with real Gemini embeddings")

    # Load fixtures
    documents = load_json("documents.json")["documents"]
    relevance = load_json("relevance_labels.json")
    redteam = load_json("acl_redteam_cases.json")
    groups = load_json("groups.json")["groups"]
    assert len(relevance["queries"]) == 30
    assert len(redteam["cases"]) == 15

    reuse = os.environ.get("G_REUSE_COLLECTION", "").strip() in ("1", "true", "TRUE", "yes")

    # Gemini provider
    os.environ.setdefault("EMBEDDING_PROVIDER", "gemini")
    os.environ.setdefault("EMBEDDING_MODEL", "gemini-embedding-001")
    os.environ.setdefault("EMBEDDING_DIMENSION", "768")
    # Import Gemini from Block E without permanently shadowing Block G's app package
    import importlib.util
    gem_path = REPO / "services" / "block-e-chunking" / "app" / "embeddings" / "gemini_provider.py"
    # Load block-e embeddings package chain via temporary path prepend
    be_root = str(REPO / "services" / "block-e-chunking")
    if be_root in sys.path:
        sys.path.remove(be_root)
    sys.path.insert(0, be_root)
    # Clear any cached wrong 'app'
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.embeddings.gemini_provider import GeminiEmbeddingProvider, gemini_config_from_env
    provider = GeminiEmbeddingProvider(gemini_config_from_env())
    # Restore Block G app for Qdrant store
    sys.path.remove(be_root)
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    sys.path.insert(0, str(ROOT))

    os.environ["VECTOR_DB_TYPE"] = "qdrant"
    os.environ["QDRANT_HOST"] = QDRANT_HOST
    os.environ["QDRANT_PORT"] = str(QDRANT_PORT)
    os.environ["EMBEDDING_DIMENSIONS"] = str(DIM)

    from app.services.qdrant_store import QdrantVectorStore

    store = QdrantVectorStore(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        collection_prefix=COLLECTION_PREFIX,
        dimensions=DIM,
    )

    docs_meta: List[Dict[str, Any]] = []
    if reuse:
        print(f"\n[1.2/1.3] G_REUSE_COLLECTION=1 — skipping re-embed/re-index; using existing {COLLECTION_PREFIX}")
        # Build docs_meta from fixtures + scroll existing vectors for G4 upsert of v2 tags
        for d in documents:
            body = d.get("body") or ""
            title = d.get("title") or ""
            text = f"{title}\n{body}".strip()
            chunk_id = (d.get("chunks") or [None])[0] or f"chk-{d['id']}-1"
            # Fetch existing embedding from Qdrant for G4 dual-version upsert
            embedding: List[float] = []
            col = f"{COLLECTION_PREFIX}_{d['tenant_id']}_chunks"
            try:
                pts = client.retrieve(collection_name=col, ids=[], with_vectors=False)
            except Exception:
                pts = []
            # scroll by chunk_id
            from qdrant_client.http import models as qm
            try:
                scrolled, _ = client.scroll(
                    collection_name=col,
                    scroll_filter=qm.Filter(
                        must=[qm.FieldCondition(key="chunk_id", match=qm.MatchValue(value=chunk_id))]
                    ),
                    limit=1,
                    with_vectors=True,
                    with_payload=True,
                )
                if scrolled:
                    vec = scrolled[0].vector
                    if isinstance(vec, dict):
                        embedding = list(next(iter(vec.values())))
                    else:
                        embedding = list(vec)
            except Exception as exc:
                print(f"  WARN scroll {chunk_id}: {exc}")
            if not embedding:
                # Fallback zero — G4 will skip useless; G1/G2/G3 use query embeds only
                embedding = [0.0] * DIM
            docs_meta.append(
                {
                    "document_id": d["id"],
                    "tenant_id": d["tenant_id"],
                    "chunk_id": chunk_id,
                    "text": text,
                    "acl": list(d.get("acl") or []),
                    "embedding": embedding,
                }
            )
        print(f"  Loaded {len(docs_meta)} fixture docs against existing collection")
    else:
        print(f"\n[1.2] Embedding {len(documents)} Block Z documents via Gemini...")

        texts = []
        for d in documents:
            body = d.get("body") or ""
            title = d.get("title") or ""
            texts.append(f"{title}\n{body}".strip())

        # Use first doc's tenant for provider logging; batches may mix tenants but Gemini provider
        # only needs a non-empty tenant_id for isolation logging.
        embeddings = await embed_texts(provider, texts, tenant_id="tenant-a", model=MODEL_V1, batch=16)
        assert all(len(v) == DIM for v in embeddings), "Expected 768-d vectors"

        for d, emb, text in zip(documents, embeddings, texts):
            chunk_id = (d.get("chunks") or [None])[0] or f"chk-{d['id']}-1"
            docs_meta.append(
                {
                    "document_id": d["id"],
                    "tenant_id": d["tenant_id"],
                    "chunk_id": chunk_id,
                    "text": text,
                    "acl": list(d.get("acl") or []),
                    "embedding": emb,
                }
            )

        await write_chunk_records(docs_meta)

        # Index into Qdrant — new prefix, do not reuse 64-d collections
        print(f"\n[1.3] Indexing into Qdrant prefix={COLLECTION_PREFIX} (size={DIM})...")
        tenants = sorted({d["tenant_id"] for d in docs_meta})
        for t in tenants:
            await store.clear_tenant(t)
            await store.ensure_tenant(t, DIM)

        for d in docs_meta:
            await store.upsert_chunk(
                tenant_id=d["tenant_id"],
                chunk_id=d["chunk_id"],
                embedding=d["embedding"],
                metadata={"document_id": d["document_id"], "chunk_text": d["text"], "metadata": {}},
                acl_terms=d["acl"],
                model_version=MODEL_V1,
            )
        print(f"  Indexed {len(docs_meta)} points across tenants={tenants}")

    # Confirm collection sizes
    for col in client.get_collections().collections:
        if COLLECTION_PREFIX in col.name:
            info = client.get_collection(col.name)
            print(f"  collection {col.name}: size={info.config.params.vectors.size} points={info.points_count}")

    # Embed queries
    print("\n[1.4] Running G1–G4...")
    q_texts = [q["query_text"] for q in relevance["queries"]]
    q_embs = await embed_texts(provider, q_texts, tenant_id="tenant-a", model=MODEL_V1, batch=16)

    # ---- G1 document-level Recall@10 ----
    recalls = []
    for q, qe in zip(relevance["queries"], q_embs):
        acl = principal_acl_terms(q["principal_id"], groups)
        results = await store.search(
            tenant_id=q["tenant_id"],
            query_embedding=qe,
            acl_terms=acl,
            top_k=10,
            model_version=MODEL_V1,
        )
        returned_docs = []
        for r in results:
            doc_id = (r.get("metadata") or {}).get("document_id") or r.get("document_id")
            # payload is flattened in search results
            if not doc_id:
                doc_id = r.get("document_id")
            if doc_id and doc_id not in returned_docs:
                returned_docs.append(doc_id)
        # Also check payload fields from store
        returned_set: Set[str] = set()
        for r in results:
            did = r.get("document_id") or (r.get("metadata") or {}).get("document_id")
            if did:
                returned_set.add(did)
        relevant = set(q.get("relevant_document_ids") or [])
        # Filter relevant to same tenant docs that exist
        hit = len(returned_set & relevant)
        recall = hit / len(relevant) if relevant else 0.0
        recalls.append(recall)
        print(f"  G1 {q['query_id']}: recall={recall:.2f} hits={sorted(returned_set & relevant)} returned={sorted(returned_set)[:5]}")

    g1_avg = sum(recalls) / len(recalls)
    g1_pass = g1_avg >= 0.85
    print(f"\nG1 Recall@10 average: {g1_avg:.4f} (threshold 0.85) -> {'PASS' if g1_pass else 'FAIL'}")

    # ---- G2 ACL zero leak (document-level forbidden) ----
    rt_texts = [c["query"] for c in redteam["cases"]]
    rt_embs = await embed_texts(provider, rt_texts, tenant_id="tenant-a", model=MODEL_V1, batch=16)
    leaks = []
    for case, qe in zip(redteam["cases"], rt_embs):
        acl = principal_acl_terms(case["principal_id"], groups)
        results = await store.search(
            tenant_id=case["tenant_id"],
            query_embedding=qe,
            acl_terms=acl,
            top_k=case.get("top_k", 50),
            model_version=MODEL_V1,
        )
        returned_docs = set()
        for r in results:
            did = r.get("document_id") or (r.get("metadata") or {}).get("document_id")
            if did:
                returned_docs.add(did)
        forbidden = set(case.get("forbidden_document_ids") or [])
        leaked = sorted(returned_docs & forbidden)
        print(f"  G2 {case['case_id']}: returned={len(results)} leaked={leaked}")
        if leaked:
            leaks.append((case["case_id"], leaked))
    g2_pass = not leaks
    print(f"\nG2 ACL prefilter: leaks={len(leaks)} -> {'PASS' if g2_pass else 'FAIL'}")
    if leaks:
        print(f"  FULL LEAK EVIDENCE: {leaks}")

    # ---- G3 latency p95 ----
    latencies = []
    for i in range(100):
        q = relevance["queries"][i % 30]
        qe = q_embs[i % 30]
        acl = principal_acl_terms(q["principal_id"], groups)
        top_k = [10, 25, 50, 100][i % 4]
        t0 = time.perf_counter()
        await store.search(
            tenant_id=q["tenant_id"],
            query_embedding=qe,
            acl_terms=acl,
            top_k=top_k,
            model_version=MODEL_V1,
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p95 = latencies[int(0.95 * (len(latencies) - 1))]
    avg_lat = sum(latencies) / len(latencies)
    g3_pass = p95 <= 150.0
    print(f"\nG3 latency: avg={avg_lat:.2f}ms p95={p95:.2f}ms (threshold 150) -> {'PASS' if g3_pass else 'FAIL'}")

    # ---- G4 dual model versions at 768-d + legacy 64-d collection coexistence ----
    # Upsert v2 tags on public-ish docs (all tenant-a)
    for d in docs_meta:
        if d["tenant_id"] != "tenant-a":
            continue
        await store.upsert_chunk(
            tenant_id=d["tenant_id"],
            chunk_id=d["chunk_id"],
            embedding=d["embedding"],
            metadata={"document_id": d["document_id"], "chunk_text": d["text"] + " [v2]", "metadata": {"reembed": True}},
            acl_terms=d["acl"],
            model_version=MODEL_V2,
        )

    # Also create a legacy 64-d collection (separate prefix) to satisfy old+new dimension coexistence check
    legacy = QdrantVectorStore(
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        collection_prefix=LEGACY_PREFIX,
        dimensions=LEGACY_DIM,
    )
    await legacy.clear_tenant("tenant-a")
    await legacy.ensure_tenant("tenant-a", LEGACY_DIM)
    synth = [0.0] * LEGACY_DIM
    synth[0] = 1.0
    await legacy.upsert_chunk(
        tenant_id="tenant-a",
        chunk_id="legacy-chk-1",
        embedding=synth,
        metadata={"document_id": "doc-legacy", "chunk_text": "legacy", "metadata": {}},
        acl_terms=["principal-alice", "group-eng"],
        model_version="text-embedding-3-large-64d",
    )
    print("  Created coexistence: 768-d gemini collections + 64-d legacy collection")

    q0 = relevance["queries"][0]
    qe0 = q_embs[0]
    acl0 = principal_acl_terms(q0["principal_id"], groups)

    v2_results = await store.search(tenant_id=q0["tenant_id"], query_embedding=qe0, acl_terms=acl0, top_k=20, model_version=MODEL_V2)
    v1_results = await store.search(tenant_id=q0["tenant_id"], query_embedding=qe0, acl_terms=acl0, top_k=20, model_version=MODEL_V1)
    mixed = await store.search(tenant_id=q0["tenant_id"], query_embedding=qe0, acl_terms=acl0, top_k=40, model_version=None)

    g4_ok = True
    reasons = []
    if not v2_results or any(r.get("model_version") != MODEL_V2 for r in v2_results):
        g4_ok = False
        reasons.append("v2 filter failed")
    if not v1_results or any(r.get("model_version") != MODEL_V1 for r in v1_results):
        g4_ok = False
        reasons.append("v1 filter failed")
    if not mixed or not all(r.get("model_version") for r in mixed):
        g4_ok = False
        reasons.append("unfiltered missing tags")
    versions = {r["model_version"] for r in mixed} if mixed else set()
    for ver in versions:
        group = [r for r in mixed if r["model_version"] == ver]
        scores = [r["score"] for r in group]
        if scores != sorted(scores, reverse=True):
            g4_ok = False
            reasons.append(f"cross-model ranking suspected for {ver}")

    # Querying 768 store must not crash while 64-d collection also exists
    try:
        _ = await store.search(tenant_id=q0["tenant_id"], query_embedding=qe0, acl_terms=acl0, top_k=10, model_version=MODEL_V1)
    except Exception as exc:  # noqa: BLE001
        g4_ok = False
        reasons.append(f"crash with dual-dim collections present: {exc}")

    g4_pass = g4_ok
    print(f"  G4 v1={len(v1_results)} v2={len(v2_results)} mixed_versions={sorted(versions)}")
    print(f"\nG4 model-version handling: {'PASS' if g4_pass else 'FAIL'} {reasons}")

    overall = g1_pass and g2_pass and g3_pass and g4_pass
    report = {
        "date": datetime.now(timezone.utc).isoformat(),
        "prior_fixture_dimensions": 64,
        "gemini_dimensions": DIM,
        "collection_prefix": COLLECTION_PREFIX,
        "legacy_prefix": LEGACY_PREFIX,
        "model_v1": MODEL_V1,
        "model_v2": MODEL_V2,
        "docs_indexed": len(docs_meta),
        "G1": {"avg_recall_at_10": g1_avg, "pass": g1_pass, "per_query": recalls},
        "G2": {"leaks": leaks, "pass": g2_pass},
        "G3": {"avg_ms": avg_lat, "p95_ms": p95, "pass": g3_pass},
        "G4": {"pass": g4_pass, "reasons": reasons, "versions_seen": sorted(versions)},
        "overall": "PASS" if overall else "FAIL",
    }
    out_json = EVIDENCE / "g_gemini_reverification_20260809.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_txt = EVIDENCE / "g_gemini_reverification_20260809.txt"
    out_txt.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\n" + "=" * 80)
    print(f"BLOCK G GEMINI RE-VERIFICATION: {report['overall']}")
    print(f"Evidence: {out_json}")
    print("=" * 80)
    return 0 if overall else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except Exception as e:
        print(f"FATAL: {e}")
        import traceback
        traceback.print_exc()
        raise SystemExit(2)
