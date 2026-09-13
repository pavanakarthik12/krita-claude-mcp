"""
CharacterLockModel: loads an existing character_lock_*.json file and
exposes it as typed objects, WITHOUT altering any existing field.

Every key already produced by the earlier tracing/locking work
(components_geometry, checksum, pivots_px, hierarchy, measurements, ratios,
and whatever else a given lock happens to carry) is preserved exactly as
loaded, byte-for-byte, in self.raw. This class only *additionally* exposes
the new skeleton/attachments/heading/views keys as Bone/Attachment objects
when present - it never requires them (a lock with no "skeleton" key still
loads successfully, satisfying backward compatibility).

The lock is treated as immutable after loading: nothing in this module
writes back to the source file, and no method mutates self.raw in place.
"""
import hashlib
import json

from .bone import Bone, Attachment


class CharacterLockModel:
    def __init__(self, raw: dict):
        self.raw = raw  # the untouched, fully-loaded JSON dict

        self.skeleton = {}
        for name, d in raw.get("skeleton", {}).items():
            self.skeleton[name] = Bone.from_dict(name, d)

        self.attachments = {}
        for name, d in raw.get("attachments", {}).items():
            self.attachments[name] = Attachment.from_dict(name, d)

        self.heading = raw.get("heading", {})
        self.views = raw.get("views", {})

    # --- existing fields, read-only passthrough, unchanged shape ---
    @property
    def components_geometry(self):
        return self.raw.get("components_geometry")

    @property
    def checksum(self):
        return self.raw.get("checksum")

    @property
    def pivots_px(self):
        return self.raw.get("pivots_px")

    @property
    def hierarchy(self):
        return self.raw.get("hierarchy")

    @property
    def measurements(self):
        return self.raw.get("measurements")

    @property
    def ratios(self):
        return self.raw.get("ratios")

    @property
    def character_id(self):
        return self.raw.get("character_id")

    # --- loading ---
    @classmethod
    def from_file(cls, path):
        with open(path, "r") as f:
            raw = json.load(f)
        return cls(raw)

    # --- integrity ---
    def compute_geometry_checksum(self):
        """Recompute the SAME checksum formula used when the lock was built
        (sha256 of components_geometry, sorted keys, truncated to 16 hex
        chars) - see build_character_lock.py / walker2_build_lock.py."""
        geometry = self.components_geometry
        if geometry is None:
            return None
        return hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()[:16]

    def checksum_valid(self):
        """True if a stored checksum matches a freshly recomputed one, or if
        no checksum was stored at all (nothing to validate against) - a
        lock missing a checksum is not treated as corrupt, just unverifiable."""
        stored = self.checksum
        if stored is None:
            return True
        return stored == self.compute_geometry_checksum()

    # --- skeleton structure ---
    def root_bones(self):
        return [b for b in self.skeleton.values() if b.parent is None]

    def children_of(self, bone_name):
        return [b for b in self.skeleton.values() if b.parent == bone_name]

    def validate_skeleton(self):
        """Returns a list of problem strings; empty list = valid. Checks:
        every bone's parent (if any) exists, no cycles, exactly the bones
        reachable from a root (no orphans silently ignored)."""
        problems = []
        names = set(self.skeleton.keys())
        for bone in self.skeleton.values():
            if bone.parent is not None and bone.parent not in names:
                problems.append(f"bone '{bone.name}' has unknown parent '{bone.parent}'")

        # cycle check: walk parent chain from every bone, bounded by len(names)
        for bone in self.skeleton.values():
            seen = set()
            cur = bone.name
            steps = 0
            while cur is not None:
                if cur in seen:
                    problems.append(f"cycle detected involving bone '{bone.name}'")
                    break
                seen.add(cur)
                parent = self.skeleton[cur].parent if cur in self.skeleton else None
                cur = parent
                steps += 1
                if steps > len(names) + 1:
                    problems.append(f"parent chain too long starting at '{bone.name}' (likely a cycle)")
                    break
        return problems
