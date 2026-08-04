import csv
from typing import List, Dict, Any

class CSVReader:
    """CSV file reader."""
    
    def __init__(self, filepath: str):
        self.filepath = filepath
    
    def read(self) -> List[Dict[str, Any]]:
        """Read CSV file and return list of dictionaries."""
        rows = []
        try:
            with open(self.filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(dict(row))
        except Exception:
            pass
        return rows
    
    def read_with_header(self) -> Tuple[List[str], List[List[str]]]:
        """Read CSV file and return header and rows."""
        header = []
        rows = []
        try:
            with open(self.filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader)
                for row in reader:
                    rows.append(row)
        except Exception:
            pass
        return header, rows
