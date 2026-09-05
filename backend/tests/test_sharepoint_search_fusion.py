"""SharePoint lexical hits must not be buried under a concatenated indexed list."""

from app.api.v1.search.federated import _merge_and_rank


def test_rrf_keeps_lexical_only_sharepoint_in_top_results():
    indexed = [
        {"document_id": f"gmail-{i}", "title": f"Welcome {i}", "snippet": "email", "sources": ["indexed"]}
        for i in range(80)
    ]
    lexical = [
        {
            "document_id": "b!dev-fake-sharepoint-drive:01DEVFAKESHAREPOINTITEM0001",
            "title": "Q3 SharePoint Sync Verification.docx",
            "snippet": "Q3 SharePoint Sync Verification",
            "source_type": "sharepoint",
            "metadata": {"source": "sharepoint"},
            "score": 12.0,
        },
        {"document_id": "gmail-0", "title": "Welcome 0", "snippet": "email", "score": 3.0},
    ]
    merged = _merge_and_rank(lexical, [], size=20, indexed_results=indexed)
    ids = [item.document_id for item in merged]
    assert "b!dev-fake-sharepoint-drive:01DEVFAKESHAREPOINTITEM0001" in ids
    assert ids.index("b!dev-fake-sharepoint-drive:01DEVFAKESHAREPOINTITEM0001") < 5
    hit = next(item for item in merged if "sharepoint" in item.document_id)
    assert (hit.metadata or {}).get("source_type") == "sharepoint"
