"""
Test fixture for truncation at ceiling.
Contains a function with a very large body to exceed 2048 tokens.
"""

def function_with_large_body():
    # This function has a massive body to exceed 2048 tokens
    large_string = "This is a very long string that will help us exceed the 2048 token ceiling for testing truncation logic. " * 200
    return large_string
