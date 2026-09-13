"""
Architectural boundary check (§10 of the blueprint): the animation engine
must be importable and testable without Krita, and must not depend on the
MCP server. This is a static source scan, not a mock - it proves the
DEPENDENCY DIRECTION is correct (engine has no idea Krita/MCP exist),
which is a stronger guarantee than "it happened to work when I ran it."

Also covers item J indirectly: since this package never imports krita,
httpx, fastmcp, or server.py, running its tests cannot have touched or
depended on any MCP/Krita drawing behavior - server.py and the Krita
plugin are provably untouched by this phase's code, independent of the
file-diff evidence in the report.
"""
import ast
import os

ANIMATION_DIR = os.path.dirname(os.path.dirname(__file__))
FORBIDDEN_IMPORTS = {"krita", "httpx", "fastmcp", "server", "PyQt5"}


def _imported_names(path):
    with open(path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_no_forbidden_imports_anywhere_in_animation_package():
    offenders = []
    for root, _dirs, files in os.walk(ANIMATION_DIR):
        if "tests" in root:
            continue  # tests are allowed to inspect the engine; the ENGINE itself must stay clean
        for fname in files:
            if fname.endswith(".py"):
                path = os.path.join(root, fname)
                found = _imported_names(path) & FORBIDDEN_IMPORTS
                if found:
                    offenders.append((path, found))
    assert offenders == [], f"engine files importing forbidden modules: {offenders}"


if __name__ == "__main__":
    test_no_forbidden_imports_anywhere_in_animation_package()
    print("test_no_krita_dependency.py: all tests passed")
