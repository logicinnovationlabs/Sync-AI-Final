"""
Dump actual AST node types from tree-sitter for Go structs and JavaScript classes.
This verifies the class_module node type lists are correct.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tree_sitter

# Initialize parsers
from tree_sitter_javascript import language as js_language
from tree_sitter_go import language as go_language

js_parser = tree_sitter.Parser(tree_sitter.Language(js_language()))
go_parser = tree_sitter.Parser(tree_sitter.Language(go_language()))

# Test JavaScript class
test_js = """
class APIHandler {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
    }

    async get(endpoint) {
        return fetch(this.baseUrl + endpoint);
    }
}

class DatabaseManager {
    constructor(config) {
        this.config = config;
    }
}
"""

# Test Go struct
test_go = """
package main

type Database struct {
    Host string
    Port int
}

type Cache struct {
    Size int
    TTL  int
}

func (d *Database) Connect() error {
    return nil
}
"""

def print_node_types(node, indent=0):
    print("  " * indent + f"- {node.type}")
    for child in node.children:
        print_node_types(child, indent + 1)

print("=" * 80)
print("JavaScript class node types:")
print("=" * 80)
js_tree = js_parser.parse(bytes(test_js, 'utf8'))
print_node_types(js_tree.root_node)

def find_class_nodes(node, results):
    if 'class' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_class_nodes(child, results)

js_class_nodes = []
find_class_nodes(js_tree.root_node, js_class_nodes)
print(f"\nClass-related node types found in JavaScript: {set(js_class_nodes)}")

print("\n" + "=" * 80)
print("Go struct node types:")
print("=" * 80)
go_tree = go_parser.parse(bytes(test_go, 'utf8'))
print_node_types(go_tree.root_node)

def find_struct_nodes(node, results):
    if 'type' in node.type.lower() or 'struct' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_struct_nodes(child, results)

go_struct_nodes = []
find_struct_nodes(go_tree.root_node, go_struct_nodes)
print(f"\nStruct-related node types found in Go: {set(go_struct_nodes)}")
