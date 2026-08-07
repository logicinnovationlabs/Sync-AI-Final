from pathlib import Path
root = Path(r"D:\PROJECTS\Sync Ai Final\tests")
for name in ["test_block_z.py", "test_block_a.py", "test_block_b.py", "test_block_c.py"]:
    p = root / name
    raw = p.read_bytes()
    text = raw.decode("utf-16") if b"\x00" in raw else raw.decode("utf-8")
    p.write_text(text, encoding="utf-8")
    print("fixed", name)
for letter, fname in [("z", "test_block_z.py"), ("a", "test_block_a.py"), ("b", "test_block_b.py"), ("c", "test_block_c.py")]:
    sp = root / "test_blocks" / fname
    sp.write_text(
        f"\"\"\"Thin re-export shim - prefer tests.test_block_{letter}.\"\"\"\n\nfrom tests.test_block_{letter} import *  # noqa: F401,F403\n",
        encoding="utf-8",
    )
    print("shim", fname)
for p in list(root.glob("test_block_*.py")) + list((root / "test_blocks").glob("test_block_[abcz].py")):
    assert b"\x00" not in p.read_bytes(), p
print("all clean utf-8")