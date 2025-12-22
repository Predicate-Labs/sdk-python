"""
Tests for spec validation - ensure SDK matches spec/snapshot.schema.json
"""

import json
import pytest
from pathlib import Path
from sentience import SentienceBrowser, snapshot
from sentience.models import Snapshot as SnapshotModel


def load_schema():
    """Load JSON schema from spec directory"""
    # __file__ is sdk-python/tests/test_spec_validation.py
    # parent = sdk-python/tests/
    # parent.parent = sdk-python/
    repo_root = Path(__file__).parent.parent
    schema_path = repo_root / "spec" / "snapshot.schema.json"
    
    with open(schema_path) as f:
        return json.load(f)


def validate_against_schema(data: dict, schema: dict) -> list:
    """Simple schema validation (basic checks)"""
    errors = []
    
    # Check required fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    # Check status enum
    if "status" in data:
        allowed = schema["properties"]["status"]["enum"]
        if data["status"] not in allowed:
            errors.append(f"Invalid status: {data['status']}, must be one of {allowed}")
    
    # Check elements array
    if "elements" in data:
        if not isinstance(data["elements"], list):
            errors.append("elements must be an array")
        else:
            # Check element structure
            element_schema = schema["definitions"]["Element"]
            element_required = element_schema.get("required", [])
            
            for i, el in enumerate(data["elements"][:5]):  # Check first 5
                for field in element_required:
                    if field not in el:
                        errors.append(f"Element {i} missing required field: {field}")
                
                # Check role enum
                if "role" in el:
                    allowed_roles = element_schema["properties"]["role"]["enum"]
                    if el["role"] not in allowed_roles:
                        errors.append(f"Element {i} has invalid role: {el['role']}")
    
    return errors


@pytest.mark.requires_extension
def test_snapshot_matches_spec():
    """Test that snapshot response matches spec schema"""
    schema = load_schema()
    
    with SentienceBrowser() as browser:
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        
        snap = snapshot(browser)
        
        # Convert to dict
        data = snap.model_dump()
        
        # Validate
        errors = validate_against_schema(data, schema)
        
        if errors:
            pytest.fail(f"Schema validation errors:\n" + "\n".join(errors))
        
        # Also verify Pydantic model validation
        assert isinstance(snap, SnapshotModel)
        assert snap.status in ["success", "error"]
        assert len(snap.elements) > 0

