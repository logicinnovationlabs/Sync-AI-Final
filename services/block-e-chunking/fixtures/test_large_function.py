"""
Test fixture for truncation at ceiling.
Contains a function exceeding 2048 tokens.
"""

def very_large_function():
    """This function is intentionally large to test truncation."""
    # Generate a lot of code to exceed 2048 tokens
    result = []
    for i in range(1000):
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
    
    # More processing
    processed = []
    for item in result:
        processed_item = {
            'original': item,
            'transformed': item['value'] * 10,
            'normalized': item['value'] / 100.0,
            'formatted': f"{item['value']:0.2f}",
            'flags': {
                'is_even': item['value'] % 2 == 0,
                'is_prime': item['value'] in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47],
                'is_fibonacci': item['value'] in [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
            }
        }
        processed.append(processed_item)
    
    # Final aggregation
    summary = {
        'total_items': len(processed),
        'sum_values': sum(p['transformed'] for p in processed),
        'average': sum(p['normalized'] for p in processed) / len(processed),
        'max_value': max(p['transformed'] for p in processed),
        'min_value': min(p['transformed'] for p in processed)
    }
    
    return summary
