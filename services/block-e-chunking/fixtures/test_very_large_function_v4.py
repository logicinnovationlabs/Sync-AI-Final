"""
Test fixture for truncation at ceiling - sized for chunker's estimation method.
Chunker uses _estimate_tokens() = len(text) // 3, so 6144 chars = 2048 estimated tokens.
This fixture is sized to exceed the 2048 threshold using the chunker's own estimation.
"""

def very_large_function():
    """This function is intentionally large to test truncation using chunker's estimation method."""
    # Generate massive code to exceed 2048 estimated tokens (6144+ characters)
    # Using repetitive code to ensure we cross the threshold
    code_block = """
    def helper_function_%d():
        x = %d
        y = %d
        z = x + y
        w = x * y
        v = x / y if y != 0 else 0
        u = x - y
        t = x ** 2
        r = x % 10
        q = str(x)
        f = float(x)
        b = bytes(str(x), 'utf-8')
        l = [x, x*2, x*3, x*4, x*5]
        d = {'a': x, 'b': x*2, 'c': x*3}
        e = (x, x*2, x*3, x*4)
        g = {x, x*2, x*3, x*4}
        h = [i for i in range(10)]
        j = {k: k*2 for k in range(10)}
        k = [x for x in range(100)]
        m = {n: n*2 for n in range(100)}
        n = list(range(1000))
        o = tuple(range(1000))
        p = set(range(1000))
        return z
    """
    
    # Generate 200 helper functions to ensure we exceed threshold
    exec_code = ""
    for i in range(200):
        exec_code += code_block % (i, i*2, i*3)
    
    exec(exec_code)
    
    # More processing
    result = []
    for i in range(100):
        result.append({
            'index': i,
            'value': i * 2,
            'squared': i ** 2,
            'cubed': i ** 3,
            'description': f"This is item number {i} in the list",
            'metadata': {
                'created_at': '2024-01-01',
                'updated_at': '2024-01-02',
                'status': 'active',
                'priority': 'high',
                'category': 'test'
            },
            'nested_data': {
                'level1': {
                    'level2': {
                        'level3': {
                            'value': i,
                            'label': f'label_{i}'
                        }
                    }
                }
            }
        })
    
    # Final aggregation
    summary = {
        'total_items': len(result),
        'sum_values': sum(p['transformed'] for p in result),
        'average': sum(p['normalized'] for p in result) / len(result),
        'max_value': max(p['transformed'] for p in result),
        'min_value': min(p['transformed'] for p in result)
    }
    
    return summary
