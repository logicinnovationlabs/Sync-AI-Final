"""
Test fixture for truncation at ceiling - sized for chunker's estimation method.
Chunker uses _estimate_tokens() = len(text) // 3, so 6144 chars = 2048 estimated tokens.
This fixture is sized to exceed the 2048 threshold using the chunker's own estimation.
"""

def very_large_function():
    """This function is intentionally large to test truncation using chunker's estimation method."""
    # Massive repetitive code to exceed 6144 characters
    result = []
    for i in range(5000):
        result.append({
            'index': i,
            'value': i * 2,
            'squared': i ** 2,
            'cubed': i ** 3,
            'description': f"This is item number {i} in the list with some additional text to make it longer",
            'metadata': {
                'created_at': '2024-01-01',
                'updated_at': '2024-01-02',
                'status': 'active',
                'priority': 'high',
                'category': 'test',
                'subcategory': 'subcategory',
                'tags': ['tag1', 'tag2', 'tag3', 'tag4', 'tag5']
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
            },
            'additional_info': f"Additional information for item {i} to increase character count significantly"
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

# Add more functions to increase size
def helper_function_1():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_2():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_3():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_4():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_5():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_6():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_7():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_8():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_9():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_10():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_11():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_12():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_13():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_14():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_15():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_16():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_17():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_18():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_19():
    x = 1
    y = 2
    z = x + y
    return z

def helper_function_20():
    x = 1
    y = 2
    z = x + y
    return z
