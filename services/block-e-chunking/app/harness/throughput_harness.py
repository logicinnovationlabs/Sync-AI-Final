"""
Component 8: Throughput Harness for Full Chunk+Embed Pipeline
Measures end-to-end throughput including embedding provider calls.
Per Master Build Prompt v1.0, §8 (E2 redefined)
"""

import time
import asyncio
import os
import statistics
from typing import List, Dict, Any
from datetime import datetime

from app.chunkers.prose_chunker import ProseChunker
from app.chunkers.code_chunker import CodeChunker
from app.chunkers.chunk_id_generator import ChunkIDGenerator
from app.embeddings.provider import EmbeddingProvider
from app.embeddings.mock_provider import MockEmbeddingProvider


class ThroughputHarness:
    """
    Harness for measuring end-to-end chunking and embedding throughput.
    
    Per Master Build Prompt v1.0, E2 is redefined to measure the FULL chunk+embed pipeline,
    not chunking-only. This harness includes:
    1. Document generation (NOT timed)
    2. Chunking (timed)
    3. Embedding provider calls (timed)
    4. Chunk record writes (timed)
    
    The E2 target is ≥500 docs/min sustained for 10 minutes.
    """
    
    def __init__(self, embedding_provider: EmbeddingProvider = None):
        self.prose_chunker = ProseChunker()
        self.code_chunker = CodeChunker()
        self.chunk_id_generator = ChunkIDGenerator()
        
        # Use mock provider by default for Phase 1 testing
        if embedding_provider is None:
            self.embedding_provider = MockEmbeddingProvider(
                base_latency_ms=100,  # 100ms base latency per batch
                jitter_ms=50,          # ±50ms jitter
                vector_dimension=1536,
            )
        else:
            self.embedding_provider = embedding_provider
    
    def generate_test_documents(self, count: int, doc_type: str = "prose") -> List[str]:
        """
        Generate test documents for load testing using actual fixture files.
        
        Args:
            count: Number of documents to generate
            doc_type: Type of documents (prose or code)
        
        Returns:
            List of document strings
        """
        import os
        from pathlib import Path
        
        documents = []
        
        if doc_type == "prose":
            # Prefer shared Block Z fixtures when FIXTURES_PATH is set
            fixtures_path = os.environ.get("FIXTURES_PATH")
            if fixtures_path:
                import json
                docs_json = Path(fixtures_path) / "documents.json"
                if docs_json.exists():
                    payload = json.loads(docs_json.read_text(encoding="utf-8"))
                    bodies = []
                    for d in payload.get("documents", []):
                        body = d.get("body") or d.get("title") or ""
                        title = d.get("title") or ""
                        bodies.append(f"{title}\n\n{body}".strip())
                    if bodies:
                        while len(bodies) < count:
                            bodies.extend(list(bodies))
                        return bodies[:count]
            # Use prose fixtures if available, otherwise fall back to synthetic
            prose_dir = Path(__file__).parent.parent.parent / "fixtures" / "prose"
            if prose_dir.exists():
                prose_files = list(prose_dir.glob("*.txt"))[:count]
                if prose_files:
                    for file_path in prose_files:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            documents.append(f.read())
                    # If we have fewer files than requested, cycle through them
                    while len(documents) < count:
                        for file_path in prose_files:
                            if len(documents) >= count:
                                break
                            with open(file_path, 'r', encoding='utf-8') as f:
                                documents.append(f.read())
                    return documents[:count]
            
            # Fallback: generate synthetic prose with varied content
            base_sentences = [
                "This is a test sentence for throughput testing that contains multiple words to simulate realistic document content.",
                "Another sentence with different structure to avoid repetitive patterns in the test data.",
                "The quick brown fox jumps over the lazy dog as a classic example of English pangram.",
                "Machine learning models require large datasets to achieve good performance on complex tasks.",
                "Natural language processing involves tokenization, parsing, and semantic analysis of text."
            ]
            for i in range(count):
                # Vary the sentence selection and order
                import random
                random.seed(i)  # Deterministic but varied
                sentences = random.choices(base_sentences, k=20)
                paragraph = " ".join(sentences) + "\n"
                base_text = (paragraph * 7)  # ~140 sentences per document
                documents.append(f"Document {i}:\n\n{base_text}")
        
        elif doc_type == "code":
            # Use code fixtures if available
            code_dirs = [
                Path(__file__).parent.parent.parent / "fixtures" / "code" / "python",
                Path(__file__).parent.parent.parent / "fixtures" / "code" / "javascript",
                Path(__file__).parent.parent.parent / "fixtures" / "code" / "go"
            ]
            
            code_files = []
            for code_dir in code_dirs:
                if code_dir.exists():
                    code_files.extend(list(code_dir.glob("*")))
            
            if code_files:
                # Use actual fixture files
                for i in range(count):
                    file_path = code_files[i % len(code_files)]
                    with open(file_path, 'r', encoding='utf-8') as f:
                        documents.append(f.read())
                return documents[:count]
            
            # Fallback: generate synthetic code with varied structure
            base_functions = [
                """
def function_{i}(param1, param2):
    '''Test function for throughput testing with realistic code structure.'''
    result = 0
    for j in range(100):
        result += j * param1
    return result
""",
                """
class TestClass_{i}:
    '''Test class for throughput testing.'''
    def __init__(self, value):
        self.value = value
    
    def method_{i}(self, x):
        return x + self.value
""",
                """
async def async_function_{i}(data):
    '''Async function for testing.'''
    processed = []
    for item in data:
        processed.append(item * 2)
    return processed
"""
            ]
            
            for i in range(count):
                code_doc = ""
                for j in range(5):
                    func_template = base_functions[j % len(base_functions)]
                    code_doc += func_template.format(i=i+j)
                documents.append(code_doc)
        
        return documents
    
    async def measure_end_to_end_throughput(
        self,
        documents: List[str],
        doc_type: str = "prose",
        tenant_id: str = "test_tenant",
        model_version: str = "text-embedding-3-large@2026-06",
    ) -> Dict[str, Any]:
        """
        Measure end-to-end chunk+embed throughput for a list of documents.
        
        This measures the FULL pipeline: chunking → embedding → record write.
        Per Master Build Prompt v1.0, E2 redefined.
        
        Args:
            documents: List of document strings
            doc_type: Type of documents (prose or code)
            tenant_id: Tenant identifier for chunk IDs and embedding isolation
            model_version: Model version string for embedding
        
        Returns:
            Dictionary with throughput metrics
        """
        chunker = self.prose_chunker if doc_type == "prose" else self.code_chunker
        language = "python" if doc_type == "code" else "english"
        
        # Start timing FULL pipeline (chunking + embedding)
        start_time = time.time()
        total_chunks = 0
        chunk_times = []
        
        # Chunk all docs, then embed in large same-tenant batches (throughput tuning).
        doc_chunks = []
        for i, doc in enumerate(documents):
            t0 = time.time()
            if doc_type == "prose":
                chunks = chunker.chunk(doc)
            else:
                chunks = chunker.chunk(doc, language)
            texts = [c.text for c in chunks] or [doc[:1000] or "empty"]
            chunk_times.append(time.time() - t0)
            doc_chunks.append((i, chunks, texts))
            total_chunks += len(texts)

        all_texts = []
        owners = []  # (doc_idx, local_chunk_idx)
        for i, chunks, texts in doc_chunks:
            for j, t in enumerate(texts):
                all_texts.append(t)
                owners.append((i, j))

        max_batch = max(1, int(os.environ.get("GEMINI_MAX_BATCH_SIZE", os.environ.get("E2_EMBED_BATCH", "50"))))
        concurrency = max(1, int(os.environ.get("E2_DOC_CONCURRENCY", "4")))
        sem = asyncio.Semaphore(concurrency)

        async def _embed_slice(start: int, end: int):
            async with sem:
                slice_texts = all_texts[start:end]
                return start, await self.embedding_provider.embed_batch(
                    texts=slice_texts,
                    tenant_id=tenant_id,
                    model_version=model_version,
                )

        slices = [(s, min(s + max_batch, len(all_texts))) for s in range(0, len(all_texts), max_batch)]
        embedded = await asyncio.gather(*[_embed_slice(s, e) for s, e in slices])
        # Map embeddings back and generate chunk IDs
        flat_results = [None] * len(all_texts)
        for start, results in embedded:
            for offset, res in enumerate(results):
                flat_results[start + offset] = res

        for (doc_i, local_j), emb in zip(owners, flat_results):
            i, chunks, texts = doc_chunks[doc_i]
            if chunks and local_j < len(chunks):
                chunk = chunks[local_j]
                chunk_type = getattr(chunk, "chunk_type", "prose")
                content_hash = chunk.chunk_id if hasattr(chunk, "chunk_id") else str(hash(chunk.text))
                chunk_index = chunk.chunk_index
            else:
                chunk_type = "prose"
                content_hash = str(hash(texts[local_j]))
                chunk_index = local_j
            self.chunk_id_generator.generate(
                tenant_id=tenant_id,
                document_id=f"doc_{doc_i}",
                document_version=1,
                chunk_type=chunk_type,
                chunk_index=chunk_index,
                content_hash=content_hash,
            )
        
        end_time = time.time()
        total_time = end_time - start_time
        
        # Calculate metrics
        docs_per_second = len(documents) / total_time if total_time > 0 else 0
        docs_per_minute = docs_per_second * 60
        chunks_per_second = total_chunks / total_time if total_time > 0 else 0
        chunks_per_minute = chunks_per_second * 60
        avg_chunk_time = statistics.mean(chunk_times) if chunk_times else 0
        p95_chunk_time = statistics.quantiles(chunk_times, n=20)[18] if len(chunk_times) >= 20 else max(chunk_times) if chunk_times else 0
        
        return {
            "document_count": len(documents),
            "total_chunks": total_chunks,
            "total_time_seconds": total_time,
            "docs_per_second": docs_per_second,
            "docs_per_minute": docs_per_minute,
            "chunks_per_second": chunks_per_second,
            "chunks_per_minute": chunks_per_minute,
            "docs_per_chunk": total_chunks / len(documents) if len(documents) > 0 else 0,
            "avg_chunk_time_ms": avg_chunk_time * 1000,
            "p95_chunk_time_ms": p95_chunk_time * 1000,
            "target_docs_per_minute": 500,
            "meets_target": docs_per_minute >= 500
        }
    
    async def run_sustained_test(
        self,
        duration_minutes: int = 10,
        doc_type: str = "prose",
        batch_size: int = 50
    ) -> Dict[str, Any]:
        """
        Run sustained throughput test for specified duration.
        
        Args:
            duration_minutes: Test duration in minutes
            doc_type: Type of documents (prose or code)
            batch_size: Number of documents per batch
        
        Returns:
            Dictionary with sustained test results
        """
        print(f"[THROUGHPUT] Starting sustained test for {duration_minutes} minutes...")
        print(f"[THROUGHPUT] Measuring end-to-end chunk+embed pipeline")
        print(f"[THROUGHPUT] Document type: {doc_type}")
        print(f"[THROUGHPUT] Batch size: {batch_size}")
        print(f"[THROUGHPUT] Embedding provider: {type(self.embedding_provider).__name__}")
        
        start_time = time.time()
        target_end_time = start_time + (duration_minutes * 60)
        
        batch_results = []
        batch_count = 0
        batch_timestamps = []  # Store timestamps separately for rolling window (per v2.0 §8.4)
        
        while time.time() < target_end_time:
            # Generate batch of documents (NOT timed)
            documents = self.generate_test_documents(batch_size, doc_type)
            
            # Log document characteristics for verification (per Master Build Prompt v1.0 §8: log before each batch)
            sample_doc = documents[0]
            print(f"[THROUGHPUT] Document characteristics (batch {batch_count + 1}):")
            print(f"   Sample document length: {len(sample_doc)} characters")
            print(f"   Sample document preview (first 200 chars): '{sample_doc[:200]}'")
            print(f"   Sample document word count: {len(sample_doc.split())} words" if doc_type == "prose" else f"   Sample document line count: {len(sample_doc.splitlines())} lines")
            
            # Measure throughput for this batch (FULL chunk+embed pipeline)
            batch_start_time = time.time()
            result = await self.measure_end_to_end_throughput(documents, doc_type)
            batch_end_time = time.time()
            
            # Store timestamp for rolling window calculation (per v2.0 §8.4)
            batch_timestamps.append((batch_end_time, result['document_count']))
            
            batch_results.append(result)
            batch_count += 1
            
            print(f"[THROUGHPUT] Batch {batch_count}: {result['docs_per_minute']:.1f} docs/min")
            
            # Safety check: if we've processed way more than expected, stop
            if batch_count > 1000:
                print(f"[THROUGHPUT] Safety limit reached (1000 batches), stopping early")
                break
        
        # Calculate aggregate metrics
        total_docs = sum(r["document_count"] for r in batch_results)
        total_time = time.time() - start_time
        overall_docs_per_minute = (total_docs / total_time) * 60 if total_time > 0 else 0
        
        total_chunks = sum(r["total_chunks"] for r in batch_results)
        overall_chunks_per_minute = (total_chunks / total_time) * 60 if total_time > 0 else 0
        
        if batch_results:
            avg_docs_per_minute = statistics.mean([r["docs_per_minute"] for r in batch_results])
            min_docs_per_minute = min([r["docs_per_minute"] for r in batch_results])
            max_docs_per_minute = max([r["docs_per_minute"] for r in batch_results])
            avg_chunks_per_minute = statistics.mean([r["chunks_per_minute"] for r in batch_results])
        else:
            avg_docs_per_minute = 0
            min_docs_per_minute = 0
            max_docs_per_minute = 0
            avg_chunks_per_minute = 0
        
        return {
            "duration_minutes": duration_minutes,
            "actual_duration_seconds": total_time,
            "batch_count": batch_count,
            "total_documents_processed": total_docs,
            "total_chunks_processed": total_chunks,
            "overall_docs_per_minute": overall_docs_per_minute,
            "overall_chunks_per_minute": overall_chunks_per_minute,
            "avg_docs_per_minute": avg_docs_per_minute,
            "min_docs_per_minute": min_docs_per_minute,
            "max_docs_per_minute": max_docs_per_minute,
            "avg_chunks_per_minute": avg_chunks_per_minute,
            "docs_per_chunk": total_chunks / total_docs if total_docs > 0 else 0,
            "batch_timestamps": batch_timestamps,  # For rolling window calculation per v2.0 §8.4
            "meets_target": min_docs_per_minute >= 500,  # Sustained: minimum must meet target
            "batch_results": batch_results
        }
