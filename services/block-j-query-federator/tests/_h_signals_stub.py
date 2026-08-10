
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI()

class Req(BaseModel):
    tenant_id: str
    principal_id: str
    document_ids: List[str]

@app.get("/health")
def health():
    return {"status": "ok", "service": "h-signals-stub", "neo4j": "bolt://localhost:7688"}

@app.post("/graph/signals")
def signals(body: Req):
    # Phase 2: Neo4j is up (docker block-h-test-neo4j); Block H has no /graph/signals
    # route, so this stub provides the federator contract while marking H reachable.
    return {"signals": {d: {"total_boost": 0.0} for d in body.document_ids}}
