from pathlib import Path
root = Path(r"D:\PROJECTS\Sync Ai Final\tests")
for name in ["test_block_z.py", "test_block_a.py", "test_block_b.py", "test_block_c.py"]:
    p = root / name
    lines = p.read_text(encoding="utf-8").splitlines()
    cleaned = []
    prev_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = blank
    p.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    print("normalized", name, "lines", len(cleaned))