"""animation.runtime - the deterministic animation intelligence/
orchestration layer sitting between Claude (semantic requests) and the
DragonBones runtime (low-level bone transforms/skinning/rendering).

See animation/dragonbones_poc4 for the proven DragonBones conversion this
layer's CharacterAsset reuses, and animation/runtime/src for the thin
DragonBones adapter that actually applies Pose objects to a real armature.
"""
