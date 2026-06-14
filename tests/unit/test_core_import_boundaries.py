from __future__ import annotations

import ast
import importlib.util as importlib_util
from pathlib import Path

PACKAGE_ROOT = "thucthengay"
CORE_PACKAGES = {
    "models",
    "config",
    "workspace",
    "ingestion",
    "download",
    "gis",
    "render",
    "validation",
    "export",
    "jobs",
    "utils",
}


def package_context_for_source(package_root: Path, source: Path) -> str:
    relative = source.relative_to(package_root).with_suffix("")
    parts = relative.parts[:-1]
    return ".".join((PACKAGE_ROOT, *parts))


def resolve_import_from(package_context: str, node: ast.ImportFrom) -> set[str]:
    if node.level == 0:
        return {node.module} if node.module else set()

    package_parts = package_context.split(".")
    base_parts = package_parts[: max(len(package_parts) - node.level + 1, 0)]
    if node.module:
        base_parts.extend(node.module.split("."))

    resolved = ".".join(base_parts)
    modules = {resolved} if resolved else set()
    modules.update(f"{resolved}.{alias.name}" for alias in node.names if resolved)
    return modules


def constant_string_arg(node: ast.Call) -> str | None:
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return None
    if not isinstance(node.args[0].value, str):
        return None
    return node.args[0].value


def constant_package_arg(node: ast.Call, package_context: str | None) -> str | None:
    for keyword in node.keywords:
        if keyword.arg == "package" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                return keyword.value.value
        if keyword.arg == "package" and isinstance(keyword.value, ast.Name):
            if keyword.value.id == "__package__":
                return package_context

    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
        if isinstance(node.args[1].value, str):
            return node.args[1].value
    if len(node.args) > 1 and isinstance(node.args[1], ast.Name):
        if node.args[1].id == "__package__":
            return package_context

    return None


def resolve_dynamic_import_name(name: str, package: str | None) -> str:
    if name.startswith(".") and package:
        return importlib_util.resolve_name(name, package)
    return name


def dynamic_import_target(
    node: ast.Call,
    importlib_names: set[str],
    import_module_names: set[str],
    package_context: str | None = None,
) -> str | None:
    target = constant_string_arg(node)
    if target is None:
        return None

    if isinstance(node.func, ast.Name) and node.func.id == "__import__":
        return target
    if isinstance(node.func, ast.Name) and node.func.id in import_module_names:
        return resolve_dynamic_import_name(target, constant_package_arg(node, package_context))
    if isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
        if isinstance(node.func.value, ast.Name) and node.func.value.id in importlib_names:
            return resolve_dynamic_import_name(target, constant_package_arg(node, package_context))

    return None


def importlib_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    importlib_names = {"importlib"}
    import_module_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)

    return importlib_names, import_module_names


def imported_modules(package_root: Path, source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imports: set[str] = set()
    package_context = package_context_for_source(package_root, source)
    importlib_names, import_module_names = importlib_aliases(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(resolve_import_from(package_context, node))
        elif isinstance(node, ast.Call):
            if target := dynamic_import_target(
                node,
                importlib_names,
                import_module_names,
                package_context,
            ):
                imports.add(target)

    return imports


def test_relative_imports_are_resolved_to_absolute_module_names() -> None:
    tree = ast.parse("from ..editor import widgets\nfrom .. import editor\n")
    import_from_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

    modules = set()
    for node in import_from_nodes:
        modules.update(resolve_import_from("thucthengay.models", node))

    assert "thucthengay.editor" in modules
    assert "thucthengay.editor.widgets" in modules


def test_package_init_relative_imports_use_package_context() -> None:
    package_root = Path("/repo/src/thucthengay")
    package_context = package_context_for_source(package_root, package_root / "models/__init__.py")
    tree = ast.parse("from ..editor import widgets\n")
    import_from = next(node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))

    modules = resolve_import_from(package_context, import_from)

    assert package_context == "thucthengay.models"
    assert "thucthengay.editor" in modules
    assert "thucthengay.editor.widgets" in modules


def test_constant_string_dynamic_imports_are_detected() -> None:
    tree = ast.parse(
        "import importlib\n"
        "import importlib as il\n"
        "from importlib import import_module\n"
        "from importlib import import_module as im\n"
        "importlib.import_module('thucthengay.editor.widgets')\n"
        "il.import_module('thucthengay.editor.models')\n"
        "import_module('thucthengay.editor.delegates')\n"
        "im('.widgets', package='thucthengay.editor')\n"
        "il.import_module('..editor.widgets', __package__)\n"
        "__import__('PySide6.QtWidgets')\n"
    )
    importlib_names, import_module_names = importlib_aliases(tree)

    modules = {
        target
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        if (
            target := dynamic_import_target(
                node,
                importlib_names,
                import_module_names,
                "thucthengay.models",
            )
        )
    }

    assert "thucthengay.editor.widgets" in modules
    assert "thucthengay.editor.models" in modules
    assert "thucthengay.editor.delegates" in modules
    assert "PySide6.QtWidgets" in modules


def test_core_packages_do_not_import_qt_or_editor_modules() -> None:
    package_root = Path(__file__).parents[2] / "src" / "thucthengay"
    violations: list[str] = []

    for package_name in sorted(CORE_PACKAGES):
        for source in (package_root / package_name).rglob("*.py"):
            for module_name in imported_modules(package_root, source):
                if module_name == "PySide6" or module_name.startswith("PySide6."):
                    violations.append(f"{source}: imports {module_name}")
                if module_name == "thucthengay.editor" or module_name.startswith(
                    "thucthengay.editor."
                ):
                    violations.append(f"{source}: imports {module_name}")

    assert violations == []
