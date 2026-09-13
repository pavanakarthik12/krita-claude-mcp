"""
Phase 1 of the general 2D character animation engine.

Scope of this package (see animation/README.md for the full report):
  - CharacterLockModel: loads/validates existing character_lock_*.json files,
    unchanged fields preserved exactly.
  - Bone / Attachment: generic skeleton data structures, arbitrary depth.
  - TransformEvaluator: generic top-down FK, dispatching to the existing,
    already-validated articulation_lib.py functions per bone strategy.
  - Pose: minimal input structure for the evaluator (not an Action system).

This package has NO dependency on Krita, the MCP server, httpx, or fastmcp.
It is importable and testable standalone. See tests/test_no_krita_dependency.py.
"""
