"""
Connector registry: auto-discovery of connectors (blind orchestrator pattern).

This module discovers all BaseConnector subclasses in app/connectors/ without
ever importing them by name. Adding connector #11 requires zero core changes.

Block B updates:
- Recursive discovery (handles packages like google/ with multiple services inside)
- Manifest parsing (reads manifest.yaml for allowed_metadata_keys per service)

Critical for the "Blind Orchestrator Rule."
"""

from typing import Dict, Type, Optional, List
import importlib
import inspect
from pathlib import Path
import yaml

from app.core.base_connector import BaseConnector, TokenStore


class ConnectorManifest:
    """
    Connector manifest - parsed from manifest.yaml.
    
    Contains metadata about the connector and its services.
    """
    
    def __init__(self, data: Dict):
        """
        Initialize manifest from parsed YAML.
        
        Args:
            data: Manifest dict
        """
        self.data = data
        self.source_type = data.get("source_type")
        self.display_name = data.get("display_name")
        self.auth_type = data.get("auth_type")
        self.oauth_scopes = data.get("oauth_scopes", [])
        self.services = data.get("services", {})
    
    def get_allowed_metadata_keys(self, source_type: str) -> List[str]:
        """
        Get allowed metadata keys for a specific service.
        
        Args:
            source_type: Service source type (e.g., 'google_drive')
            
        Returns:
            List of allowed metadata keys
        """
        service_config = self.services.get(source_type, {})
        return service_config.get("allowed_metadata_keys", [])


class ConnectorRegistry:
    """
    Auto-discovery registry for connectors.
    
    Scans app/connectors/ recursively and registers all BaseConnector subclasses
    by source_type. Also parses manifest.yaml files for metadata allowlisting.
    
    The orchestrator (sync.py) never imports specific connectors by name.
    """

    def __init__(self):
        self._connectors: Dict[str, Type[BaseConnector]] = {}
        self._manifests: Dict[str, ConnectorManifest] = {}
        self._discovered = False

    def discover(self, connectors_path: Path = None) -> None:
        """
        Auto-discover all connectors in app/connectors/ recursively.
        
        Walks the directory tree, loads manifest.yaml files, and imports
        all Python modules to find BaseConnector subclasses.
        
        Args:
            connectors_path: Path to connectors directory (defaults to app/connectors/)
        """
        if self._discovered:
            return
        
        if connectors_path is None:
            connectors_path = Path(__file__).parent.parent / "connectors"
        
        if not connectors_path.exists():
            # No connectors yet (Block B will populate)
            self._discovered = True
            return
        
        # First pass: discover manifests
        for manifest_path in connectors_path.rglob("manifest.yaml"):
            try:
                with open(manifest_path, "r") as f:
                    manifest_data = yaml.safe_load(f)
                    manifest = ConnectorManifest(manifest_data)
                    
                    # Store manifest by package source_type
                    package_source_type = manifest.source_type
                    if package_source_type:
                        self._manifests[package_source_type] = manifest
            except Exception as e:
                # Log but don't fail discovery
                print(f"Warning: Failed to load manifest {manifest_path}: {e}")
        
        # Second pass: discover connector classes
        for file_path in connectors_path.rglob("*.py"):
            if file_path.name.startswith("_"):
                continue
            
            # Import the module
            try:
                # Build module path relative to app/
                rel_path = file_path.relative_to(connectors_path.parent.parent)
                module_path = str(rel_path).replace("/", ".").replace("\\", ".")[:-3]
                module = importlib.import_module(module_path)
            except Exception as e:
                # Skip modules that can't be imported
                continue
            
            # Find all BaseConnector subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseConnector) and obj is not BaseConnector:
                    # Instantiate with dummy config to get source_type
                    try:
                        dummy_instance = obj(config={}, token_store=DummyTokenStore())
                        source_type = dummy_instance.get_source_type()
                        self._connectors[source_type] = obj
                    except Exception:
                        # Skip connectors that can't be instantiated
                        pass
        
        self._discovered = True

    def get_connector(
        self,
        source_type: str,
        config: dict,
        token_store: TokenStore,
    ) -> BaseConnector:
        """
        Get a connector instance by source_type.
        
        Args:
            source_type: Source type identifier (e.g., 'google_drive')
            config: Connector configuration
            token_store: Token storage
            
        Returns:
            Connector instance.
            
        Raises:
            ValueError if source_type not found.
        """
        if not self._discovered:
            self.discover()
        
        connector_class = self._connectors.get(source_type)
        if not connector_class:
            raise ValueError(f"Unknown source_type: {source_type}")
        
        return connector_class(config=config, token_store=token_store)

    def get_allowed_metadata_keys(self, source_type: str) -> List[str]:
        """
        Get allowed metadata keys for a source type.
        
        Looks up the service in its package's manifest.yaml.
        
        Args:
            source_type: Source type identifier (e.g., 'google_drive')
            
        Returns:
            List of allowed metadata keys (empty if not found)
        """
        if not self._discovered:
            self.discover()
        
        # For services like 'google_drive', check if there's a 'google' package manifest
        # that defines this service
        for package_type, manifest in self._manifests.items():
            if source_type in manifest.services:
                return manifest.get_allowed_metadata_keys(source_type)
        
        # Legacy: check if there's a direct manifest for this source_type
        manifest = self._manifests.get(source_type)
        if manifest:
            return manifest.get_allowed_metadata_keys(source_type)
        
        return []

    def list_sources(self) -> list[str]:
        """
        List all registered source types.
        
        Returns:
            List of source type identifiers.
        """
        if not self._discovered:
            self.discover()
        return list(self._connectors.keys())


class DummyTokenStore(TokenStore):
    """Dummy token store for registry discovery."""
    
    def get_token(self, key: str) -> Optional[dict]:
        return None
    
    def set_token(self, key: str, token_data: dict) -> None:
        pass


# Global registry instance
connector_registry = ConnectorRegistry()
