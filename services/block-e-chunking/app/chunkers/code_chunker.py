"""
AST-based code chunker using tree-sitter.

Per v7.0 §3.2: Node-type mappings are empirically verified via dump scripts.
Per v7.0 §3.4: Implements min_tokens floor (20) and max_tokens ceiling (2048).
Per v7.0 §2.1: Implements 8KB object-storage threshold.
Per Phase 1.2 (Aug 4, 2026): Uses tiktoken for accurate token counting (cl100k_base encoding).
"""

from dataclasses import dataclass
from typing import List, Optional
import tree_sitter
import tiktoken


@dataclass
class CodeChunk:
    """Represents a code chunk per v7.0 §2.1."""
    text: str
    start_byte: int
    end_byte: int
    chunk_type: str
    chunk_index: int
    token_count: int
    node_type: Optional[str] = None  # AST node type (required per v7.0 §3.2)
    language: Optional[str] = None  # Programming language
    truncated: Optional[bool] = False  # Per v7.0 §3.4: flag for chunks exceeding ceiling


class CodeChunker:
    """
    AST-based code chunker using tree-sitter.
    
    Produces six chunk types per §10.4:
    - repo_metadata: Repository-level metadata (TODO: from repo context)
    - file_summary: File-level summary chunk
    - import_block: Import statements
    - function_method: Function and method definitions
    - class_module: Class and module definitions
    - comment_docstring: Comments and docstrings
    
    Never uses line-count-based splitting - always AST-based.
    Explicitly verifies parse success by checking for ERROR nodes.
    """
    
    def __init__(self):
        self.language_parsers = {}
        self.MIN_TOKENS = 20
        self.MAX_TOKENS = 2048
        self.INLINE_THRESHOLD = 8192
        self._initialize_languages()
        # Initialize tiktoken with cl100k_base encoding (matches Azure OpenAI text-embedding-3-large)
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
    
    def _initialize_languages(self):
        """Initialize tree-sitter language parsers for supported languages."""
        try:
            # Python
            from tree_sitter_python import language as python_language
            self.language_parsers['python'] = tree_sitter.Language(python_language())
            
            # JavaScript
            from tree_sitter_javascript import language as javascript_language
            self.language_parsers['javascript'] = tree_sitter.Language(javascript_language())
            
            # Go
            from tree_sitter_go import language as go_language
            self.language_parsers['go'] = tree_sitter.Language(go_language())
        except ImportError as e:
            print(f"Warning: Failed to load tree-sitter language: {e}")
    
    def _get_parser(self, language: str) -> Optional[tree_sitter.Parser]:
        """Get parser for given language."""
        if language not in self.language_parsers:
            return None
        
        parser = tree_sitter.Parser(self.language_parsers[language])
        return parser
    
    def _extract_text(self, source: str, node: tree_sitter.Node) -> str:
        """Extract text from source using node byte offsets."""
        return source[node.start_byte:node.end_byte]
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Count actual tokens using tiktoken (cl100k_base encoding).
        Per Phase 1.2 decision (Aug 4, 2026): replaced character-based estimate with real tokenizer.
        """
        return len(self.tokenizer.encode(text))
    
    def _extract_import_blocks(self, source: str, tree: tree_sitter.Tree, language: str) -> List[CodeChunk]:
        """Extract import block chunks."""
        chunks = []
        root = tree.root_node
        
        # Find import statements (empirically verified per v7.0 §3.2)
        import_nodes = []
        if language == 'python':
            self._find_nodes_by_type(root, ['import_statement', 'import_from_statement'], import_nodes)
        elif language == 'go':
            # Empirically verified per v7.0 §3.2 from dump_go_node_types.py
            self._find_nodes_by_type(root, ['import_declaration'], import_nodes)
        elif language == 'javascript':
            # Empirically verified per v7.0 §3.2 from dump_js_imports.py
            self._find_nodes_by_type(root, ['import_statement'], import_nodes)
        
        if import_nodes:
            # Group consecutive imports into a single block
            import_nodes.sort(key=lambda n: n.start_byte)
            
            start_byte = import_nodes[0].start_byte
            end_byte = import_nodes[-1].end_byte
            text = self._extract_text(source, tree.root_node)
            import_text = text[start_byte:end_byte]
            
            chunks.append(CodeChunk(
                text=import_text,
                start_byte=start_byte,
                end_byte=end_byte,
                chunk_type='import_block',
                chunk_index=0,
                token_count=self._estimate_tokens(import_text),
                node_type='import_block',
                language=language
            ))
        
        return chunks
    
    def _extract_functions(self, source: str, tree: tree_sitter.Tree, language: str) -> tuple[List[CodeChunk], List[tuple]]:
        """Extract function/method chunks."""
        chunks = []
        root = tree.root_node
        
        # Empirically verified per v7.0 §3.2 from dump_python_node_types.py: Python uses 'function_definition'
        function_nodes = []
        if language == 'python':
            self._find_nodes_by_type(root, ['function_definition'], function_nodes)
        elif language == 'go':
            self._find_nodes_by_type(root, ['function_declaration'], function_nodes)
        
        # Per v7.0 §3.4: Collect all function nodes, including those below floor
        # Small functions will be merged into parent class_module chunks later
        small_function_nodes = []
        for i, node in enumerate(function_nodes):
            text = self._extract_text(source, node)
            token_count = self._estimate_tokens(text)
            
            # Per v7.0 §3.4: Skip chunks below minimum token floor
            # These will be merged into parent class_module chunks
            if token_count < self.MIN_TOKENS:
                small_function_nodes.append((node, text, token_count))
                continue
            
            # Per v7.0 §3.4: Truncate chunks exceeding maximum ceiling
            truncated = False
            if token_count > self.MAX_TOKENS:
                # Truncate at ceiling - this is a last-resort measure
                # In practice, this should rarely happen with well-structured code
                text = text[:int(len(text) * (self.MAX_TOKENS / token_count))]
                token_count = self.MAX_TOKENS
                truncated = True
            
            chunks.append(CodeChunk(
                text=text,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                chunk_type='function_method',
                chunk_index=i,
                token_count=token_count,
                node_type=node.type,
                language=language,
                truncated=truncated
            ))
        
        return chunks, small_function_nodes
    
    def _extract_classes(self, source: str, tree: tree_sitter.Tree, language: str) -> List[CodeChunk]:
        """Extract class chunks."""
        chunks = []
        root = tree.root_node
        
        class_nodes = []
        if language == 'python':
            # Empirically verified per v7.0 §3.2 from dump_python_node_types.py
            self._find_nodes_by_type(root, ['class_definition'], class_nodes)
        elif language == 'go':
            # Empirically verified per v7.0 §3.2 from dump_go_node_types.py
            self._find_nodes_by_type(root, ['type_declaration'], class_nodes)
        elif language == 'javascript':
            # Empirically verified per v7.0 §3.2 from dump_js_imports.py
            self._find_nodes_by_type(root, ['class_declaration'], class_nodes)
        
        for i, node in enumerate(class_nodes):
            text = self._extract_text(source, node)
            token_count = self._estimate_tokens(text)
            
            # Per v7.0 §3.4: Truncate chunks exceeding maximum ceiling
            truncated = False
            if token_count > self.MAX_TOKENS:
                text = text[:int(len(text) * (self.MAX_TOKENS / token_count))]
                token_count = self.MAX_TOKENS
                truncated = True
            
            chunks.append(CodeChunk(
                text=text,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                chunk_type='class_module',
                chunk_index=i,
                token_count=token_count,
                node_type=node.type,
                language=language,
                truncated=truncated
            ))
        
        return chunks
    
    def _extract_modules(self, source: str, tree: tree_sitter.Tree, language: str) -> List[CodeChunk]:
        """Extract module-level chunks."""
        chunks = []
        root = tree.root_node
        
        module_nodes = []
        if language == 'python':
            self._find_nodes_by_type(root, ['module'], module_nodes)
        elif language == 'go':
            # Empirically verified per v7.0 §3.2 from dump_go_node_types.py
            self._find_nodes_by_type(root, ['package_clause'], module_nodes)
        elif language == 'javascript':
            # JavaScript module detection (to be verified)
            self._find_nodes_by_type(root, ['program', 'module'], module_nodes)
        
        for i, node in enumerate(module_nodes):
            text = self._extract_text(source, node)
            chunks.append(CodeChunk(
                text=text,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                chunk_type='class_module',
                chunk_index=i,
                token_count=self._estimate_tokens(text),
                node_type=node.type,
                language=language
            ))
        
        return chunks
    
    def _extract_comments(self, source: str, tree: tree_sitter.Tree, language: str) -> List[CodeChunk]:
        """Extract comment/docstring chunks."""
        chunks = []
        root = tree.root_node
        
        comment_nodes = []
        if language == 'python':
            # Empirically verified per v7.0 §3.2 from dump_python_node_types.py: Python uses 'string' for docstrings
            self._find_nodes_by_type(root, ['string', 'comment'], comment_nodes)
        elif language == 'go':
            # Go tree-sitter grammar doesn't have explicit comment nodes in the fixture
            # Comment extraction may need different approach
            pass
        elif language == 'javascript':
            # Empirically verified per v7.0 §3.2 from dump_js_node_types.py
            self._find_nodes_by_type(root, ['comment'], comment_nodes)
        
        for i, node in enumerate(comment_nodes):
            text = self._extract_text(source, node)
            chunks.append(CodeChunk(
                text=text,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                chunk_type='comment_docstring',
                chunk_index=i,
                token_count=self._estimate_tokens(text),
                node_type=node.type,
                language=language
            ))
        
        return chunks
    
    def _find_nodes_by_type(self, node: tree_sitter.Node, types: List[str], results: List):
        """Recursively find nodes of specified types."""
        if node.type in types:
            results.append(node)
        for child in node.children:
            self._find_nodes_by_type(child, types, results)
    
    def chunk(self, source: str, language: str) -> List[CodeChunk]:
        """
        Chunk code using AST-based parsing.
        
        Args:
            source: Source code text
            language: Programming language (python, javascript, go)
        
        Returns:
            List of CodeChunk objects
        
        Raises:
            ValueError: If parse fails or language not supported
        """
        parser = self._get_parser(language)
        if not parser:
            raise ValueError(f"Unsupported language: {language}")
        
        # Parse source code
        tree = parser.parse(bytes(source, 'utf8'))
        
        # Verify parse succeeded (no ERROR nodes)
        if not self._verify_parse(tree):
            error_nodes = []
            self._find_nodes_by_type(tree.root_node, ['ERROR'], error_nodes)
            error_msg = f"Parse failed for {language}: found {len(error_nodes)} ERROR nodes"
            print(f"ERROR: {error_msg}")
            raise ValueError(error_msg)
        
        chunks = []
        chunk_index = 0
        
        # Extract file-level summary (first 200 chars or first significant node)
        chunks.append(CodeChunk(
            text=source[:min(200, len(source))],
            start_byte=0,
            end_byte=min(200, len(source)),
            chunk_type='file_summary',
            chunk_index=chunk_index,
            token_count=self._estimate_tokens(source[:min(200, len(source))]),
            node_type='file_summary',
            language=language
        ))
        chunk_index += 1
        
        # Extract import blocks
        import_chunks = self._extract_import_blocks(source, tree, language)
        for chunk in import_chunks:
            chunk.chunk_index = chunk_index
            chunks.append(chunk)
            chunk_index += 1
        
        # Extract functions (including small ones for merging)
        function_chunks, small_function_nodes = self._extract_functions(source, tree, language)
        for chunk in function_chunks:
            chunk.chunk_index = chunk_index
            chunks.append(chunk)
            chunk_index += 1
        
        # Extract classes
        class_chunks = self._extract_classes(source, tree, language)
        
        # Per v7.0 §3.4: Merge small functions into parent class chunks
        # Find which class each small function belongs to and merge it
        for node, text, token_count in small_function_nodes:
            # Find the class that contains this function
            for class_chunk in class_chunks:
                if node.start_byte >= class_chunk.start_byte and node.end_byte <= class_chunk.end_byte:
                    # Function is inside this class - merge by appending to class text
                    # This is a simple merge strategy; could be refined to preserve structure
                    class_chunk.text += '\n\n' + text
                    class_chunk.token_count += token_count
                    class_chunk.end_byte = node.end_byte  # Extend class boundaries
                    break
        
        for chunk in class_chunks:
            chunk.chunk_index = chunk_index
            chunks.append(chunk)
            chunk_index += 1
        
        # Extract module-level chunk ONLY if file has multiple top-level definitions
        # This avoids duplication when a file contains only a single class
        # (the class chunk already covers the class content)
        module_chunks = self._extract_modules(source, tree, language)
        if module_chunks:
            # Check if file content is fully covered by class chunks
            # If there are class chunks that cover most of the file, skip module chunk
            class_coverage = sum(chunk.end_byte - chunk.start_byte for chunk in class_chunks)
            file_size = len(source)
            
            # If classes cover >80% of file, skip module chunk to avoid duplication
            # This handles the common case of single-class files
            if class_coverage < file_size * 0.8:
                for chunk in module_chunks:
                    chunk.chunk_index = chunk_index
                    chunks.append(chunk)
                    chunk_index += 1
            else:
                # File is primarily class definitions, module chunk would duplicate
                # Skip it to avoid downstream storage/embedding costs
                pass
        
        # Extract comments
        comment_chunks = self._extract_comments(source, tree, language)
        for chunk in comment_chunks:
            chunk.chunk_index = chunk_index
            chunks.append(chunk)
            chunk_index += 1
        
        return chunks
    
    def _verify_parse(self, tree: tree_sitter.Tree) -> bool:
        """Verify parse succeeded by checking for ERROR nodes."""
        error_nodes = []
        self._find_nodes_by_type(tree.root_node, ['ERROR'], error_nodes)
        return len(error_nodes) == 0
    
    def chunk_with_metadata(
        self,
        tenant_id: str,
        document_id: str,
        document_version: str,
        source: str,
        language: str,
        chunker_version: str
    ) -> List[dict]:
        """
        Chunk code with metadata for database insertion.
        
        Args:
            tenant_id: Tenant identifier
            document_id: Document identifier
            document_version: Document version
            source: Source code text
            language: Programming language
            chunker_version: Chunker version for content hash
        
        Returns:
            List of dictionaries ready for database insertion
        """
        from app.chunkers.chunk_id_generator import ChunkIDGenerator
        
        chunks = self.chunk(source, language)
        id_generator = ChunkIDGenerator(chunker_version=chunker_version)
        
        chunk_records = []
        for chunk in chunks:
            content_hash = id_generator.compute_content_hash(chunk.text)
            chunk_id = id_generator.generate(
                tenant_id=tenant_id,
                document_id=document_id,
                document_version=document_version,
                chunk_type=chunk.chunk_type,
                chunk_index=chunk.chunk_index,
                content_hash=content_hash
            )
            
            # Per v7.0 §2.1: Use object_store_ref if chunk_text exceeds 8KB threshold
            chunk_text = chunk.text
            object_store_ref = None
            if len(chunk_text.encode('utf-8')) > self.INLINE_THRESHOLD:
                # TODO: Write to object store and populate object_store_ref
                # For now, this is a placeholder - actual object storage integration
                # is a separate concern (Block D or external service)
                object_store_ref = f"s3://chunks/{chunk_id}"
                # Keep inline for now - this will be replaced with object store integration
                # chunk_text = None  # Uncomment when object storage is implemented
            
            chunk_records.append({
                'chunk_id': chunk_id,
                'tenant_id': tenant_id,
                'document_id': document_id,
                'document_version': document_version,
                'chunk_type': chunk.chunk_type,
                'chunk_index': chunk.chunk_index,
                'chunk_text': chunk_text,
                'token_count': chunk.token_count,
                'start_byte': chunk.start_byte,
                'end_byte': chunk.end_byte,
                'node_type': chunk.node_type,
                'language': chunk.language,
                'object_store_ref': object_store_ref,
                'truncated': chunk.truncated,
                'content_hash': content_hash,
                'chunker_version': chunker_version
            })
        
        return chunk_records
