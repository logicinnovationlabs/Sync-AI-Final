"""
ACL inheritance computation.

Computes inherited permissions from container ancestors.
Deny entries on nearer ancestors override allow entries from farther ancestors.
"""

import logging
from typing import List, Dict, Tuple
from uuid import UUID
from datetime import datetime, timezone

from app.core.models import (
    CanonicalDocument,
    ACLEntry,
    ContainerACLEntry,
    PermissionLevel,
)
from app.acl.container_service import ContainerService

logger = logging.getLogger(__name__)


async def compute_inherited_entries(
    document: CanonicalDocument,
    container_service: ContainerService,
) -> List[ACLEntry]:
    """
    Compute inherited ACL entries for a document.
    
    For each parent container, walk ancestors (cycle-safe) and collect permissions.
    Deny entries on nearer ancestors override allow entries from farther ancestors
    for the same principal/group.
    
    Args:
        document: CanonicalDocument with parent_ids
        container_service: Container service for hierarchy traversal
        
    Returns:
        List of inherited ACLEntry objects
    """
    inherited_entries: List[ACLEntry] = []
    
    # Track (principal_id/group_id, nearest_deny) to implement deny-override
    deny_map: Dict[Tuple[str, str], int] = {}  # {(id_type, id_value): distance}
    allow_map: Dict[Tuple[str, str], Tuple[int, ACLEntry]] = {}  # {(id_type, id_value): (distance, entry)}
    
    for parent_id in document.parent_ids:
        # Get ancestors (cycle-safe)
        ancestors = await container_service.get_ancestors(
            parent_id, document.tenant_id
        )
        
        # Include the parent itself at distance 0
        all_containers = [parent_id] + ancestors
        
        for distance, container_id in enumerate(all_containers):
            # Get direct permissions on this container
            container_perms = await container_service.get_container_permissions(
                container_id, document.tenant_id
            )
            
            for cperm in container_perms:
                # Identify principal or group
                if cperm.principal_id:
                    id_key = ("principal", str(cperm.principal_id))
                elif cperm.group_id:
                    id_key = ("group", str(cperm.group_id))
                else:
                    logger.warning(
                        f"ContainerACLEntry with neither principal_id nor group_id: {cperm}"
                    )
                    continue
                
                # Handle deny entries
                if cperm.is_deny:
                    # Track nearest deny
                    if id_key not in deny_map or distance < deny_map[id_key]:
                        deny_map[id_key] = distance
                    continue
                
                # Handle allow entries
                if id_key not in allow_map or distance < allow_map[id_key][0]:
                    # Create inherited ACL entry
                    entry = ACLEntry(
                        document_id=document.id,
                        principal_id=cperm.principal_id,
                        group_id=cperm.group_id,
                        permission=cperm.permission,
                        granted_via="inherited",
                        source_container_id=container_id,
                        is_deny=False,
                        source_type=document.source_type,
                        tenant_id=document.tenant_id,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    allow_map[id_key] = (distance, entry)
    
    # Apply deny-override: remove allows that have a nearer or equal deny
    for id_key, (distance, entry) in allow_map.items():
        deny_distance = deny_map.get(id_key)
        if deny_distance is not None and deny_distance <= distance:
            # Deny wins — skip this allow entry
            logger.debug(
                f"Deny override: skipping inherited allow for {id_key} at distance {distance} "
                f"due to deny at distance {deny_distance}"
            )
            continue
        
        inherited_entries.append(entry)
    
    return inherited_entries
