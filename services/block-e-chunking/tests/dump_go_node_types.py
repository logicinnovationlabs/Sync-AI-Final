"""
Dump actual AST node types from tree-sitter-go for a representative fixture.
This verifies the actual node types used by the grammar for function/class boundary detection.
Per v7.0 §3.2: Node-type mappings must be empirically derived from actual tree-sitter output,
not from documentation or prior knowledge.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tree_sitter

# Initialize Go parser
from tree_sitter_go import language as go_language
parser = tree_sitter.Parser(tree_sitter.Language(go_language()))

# Load representative Go fixture with all chunk-type cases
fixture_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "fixtures",
    "code",
    "go",
    "database.go"
)

with open(fixture_path, 'r', encoding='utf-8') as f:
    source = f.read()

# Parse
tree = parser.parse(bytes(source, 'utf8'))

# Recursively print all node types
def print_node_types(node, indent=0):
    print("  " * indent + f"- {node.type}")
    for child in node.children:
        print_node_types(child, indent + 1)

print("=" * 80)
print(f"All node types in fixture: {os.path.basename(fixture_path)}")
print("=" * 80)
print_node_types(tree.root_node)

# Specifically look for function-related nodes
def find_function_nodes(node, results):
    if 'function' in node.type.lower() or 'func' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_function_nodes(child, results)

function_nodes = []
find_function_nodes(tree.root_node, function_nodes)
print(f"\nFunction-related node types found: {set(function_nodes)}")

# Specifically look for class/struct-related nodes
def find_class_nodes(node, results):
    if 'class' in node.type.lower() or 'struct' in node.type.lower() or 'type' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_class_nodes(child, results)

class_nodes = []
find_class_nodes(tree.root_node, class_nodes)
print(f"Class/Struct-related node types found: {set(class_nodes)}")

# Specifically look for module-related nodes
def find_module_nodes(node, results):
    if 'module' in node.type.lower() or 'package' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_module_nodes(child, results)

module_nodes = []
find_module_nodes(tree.root_node, module_nodes)
print(f"Module/Package-related node types found: {set(module_nodes)}")

# Specifically look for import-related nodes
def find_import_nodes(node, results):
    if 'import' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_import_nodes(child, results)

import_nodes = []
find_import_nodes(tree.root_node, import_nodes)
print(f"Import-related node types found: {set(import_nodes)}")

# Specifically look for comment nodes
def find_comment_nodes(node, results):
    if 'comment' in node.type.lower():
        results.append(node.type)
    for child in node.children:
        find_comment_nodes(child, results)

comment_nodes = []
find_comment_nodes(tree.root_node, comment_nodes)
print(f"Comment-related node types found: {set(comment_nodes)}")

print("=" * 80)
print("This output is the evidence trail for Go node-type mapping per v7.0 §3.2")
print("Do not delete this file - it is regression evidence, not scratch work.")
print("=" * 80)
