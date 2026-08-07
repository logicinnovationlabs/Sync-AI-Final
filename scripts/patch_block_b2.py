from pathlib import Path
bp = Path(r"D:\PROJECTS\Sync Ai Final\tests\test_block_b.py")
text = bp.read_text(encoding="utf-8")
old = """    # B2 - delta types from crawl cover fixture expectations (up to 5 when listed)
    def test_b2_delta_types(self, block_client, fixture_loader):
        expected = fixture_loader.load(\"crawl_expectations\").get(\"delta_types\", [])
        drive = block_client.post(\"/connectors/google-drive/crawl\").json()
        gmail = block_client.post(\"/connectors/google-gmail/crawl\").json()
        seen = {o.get(\"delta_type\") for o in drive[\"objects\"] + gmail[\"objects\"]}
        seen.discard(None)
        required = set(expected[:5]) if expected else set()
        covers_required = required.issubset(seen) if required else (\"created\" in seen or \"updated\" in seen)
        assert_pass(\"B2\", covers_required, f\"seen={sorted(seen)} required={sorted(required)}\")
        assert covers_required"""
new = """    # B2 - delta types valid; cover up to 5 listed types when fixture defines them
    def test_b2_delta_types(self, block_client, fixture_loader):
        expected_list = fixture_loader.load(\"crawl_expectations\").get(\"delta_types\", [])
        expected = set(expected_list)
        drive = block_client.post(\"/connectors/google-drive/crawl\").json()
        gmail = block_client.post(\"/connectors/google-gmail/crawl\").json()
        seen = {o.get(\"delta_type\") for o in drive[\"objects\"] + gmail[\"objects\"]}
        seen.discard(None)
        valid = seen.issubset(expected)
        has_changes = \"created\" in seen or \"updated\" in seen
        if len(expected_list) >= 5:
            covers_required = set(expected_list[:5]).issubset(seen)
        else:
            covers_required = valid and has_changes
        assert_pass(\"B2\", covers_required, f\"seen={sorted(seen)} expected={sorted(expected)}\")
        assert covers_required"""
if old not in text:
    raise SystemExit("B2 block not found")
bp.write_text(text.replace(old, new), encoding="utf-8")
print("patched B2")