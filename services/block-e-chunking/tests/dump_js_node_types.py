"""
Dump actual AST node types from tree-sitter-javascript for a class with shorthand methods.
This verifies whether 'property_method' is a real node type or if 'method_definition' covers it.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tree_sitter

# Initialize JavaScript parser
from tree_sitter_javascript import language as js_language
parser = tree_sitter.Parser(tree_sitter.Language(js_language()))

# Test JavaScript code with class shorthand methods
test_js = """
class APIHandler {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async get(endpoint) {
        return fetch(this.baseUrl + endpoint);
    }

    async post(endpoint, data) {
        return fetch(this.baseUrl + endpoint, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    // Regular method with function keyword
    delete: function(endpoint) {
        return fetch(this.baseUrl + endpoint, { method: 'DELETE' });
    }
}
"""

# Parse
tree = parser.parse(bytes(test_js, 'utf8'))

# Recursively print all node types
def print_node_types(node, indent=0):
    print("  " * indent + f"- {node.type}")
    for child in node.children:
        print_node_types(child, indent + 1)

print("All node types in test JavaScript class:")
print_node_types(tree.root_node)

# Specifically look for method-related nodes
def find_method_nodes(node, results):
    if 'method' in node.type.lower() or 'function' in node.type.lower() or 'property' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_method_nodes(child, results)

method_nodes = []
find_method_nodes(tree.root_node, method_nodes)
print(f"\nMethod/Function/Property-related node types found: {set(method_nodes)}")
