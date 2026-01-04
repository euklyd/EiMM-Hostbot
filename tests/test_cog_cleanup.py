"""Tests to ensure cogs properly clean up resources on unload.

These tests catch issues like unclosed aiohttp sessions or database connections
that can cause hangs on shutdown.
"""

import ast
import inspect
from pathlib import Path

import pytest

# Patterns that indicate a resource requiring cleanup
RESOURCE_PATTERNS = {
    "aiohttp.ClientSession()": "aiohttp session",
    "create_async_engine(": "async SQLAlchemy engine",
}

# Cogs that are known to not need cleanup (e.g., use context managers properly)
CLEANUP_EXCEPTIONS: set[str] = {
    "emoji_count",  # Uses `async with ClientSession()` - properly scoped
}


def get_cog_files() -> list[Path]:
    """Get all Python files in the cogs directory."""
    cogs_dir = Path(__file__).parent.parent / "cogs"
    return [f for f in cogs_dir.glob("*.py") if f.name != "__init__.py"]


def file_contains_pattern(filepath: Path, pattern: str) -> bool:
    """Check if a file contains a specific pattern."""
    content = filepath.read_text()
    return pattern in content


def get_cog_classes(filepath: Path) -> list[str]:
    """Get names of Cog classes defined in a file."""
    content = filepath.read_text()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    cog_classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it inherits from commands.Cog or similar
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if "Cog" in base_name:
                    cog_classes.append(node.name)
                    break
    return cog_classes


def class_has_method(filepath: Path, class_name: str, method_name: str) -> bool:
    """Check if a class in a file has a specific method."""
    content = filepath.read_text()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name == method_name:
                        return True
    return False


class TestCogResourceCleanup:
    """Verify cogs with resources have proper cleanup methods."""

    @pytest.mark.parametrize("cog_file", get_cog_files(), ids=lambda p: p.stem)
    def test_async_resources_have_cleanup(self, cog_file: Path) -> None:
        """Cogs with async resources must have cog_unload methods."""
        # Check if file uses any async resources
        uses_async_resources = False
        resource_types = []

        for pattern, resource_type in RESOURCE_PATTERNS.items():
            if file_contains_pattern(cog_file, pattern):
                uses_async_resources = True
                resource_types.append(resource_type)

        if not uses_async_resources:
            pytest.skip(f"{cog_file.stem} doesn't use async resources")

        if cog_file.stem in CLEANUP_EXCEPTIONS:
            pytest.skip(f"{cog_file.stem} is in cleanup exceptions")

        # Find cog classes
        cog_classes = get_cog_classes(cog_file)
        if not cog_classes:
            pytest.skip(f"{cog_file.stem} has no Cog classes")

        # Check each cog class has cog_unload
        for cog_class in cog_classes:
            has_unload = class_has_method(cog_file, cog_class, "cog_unload")
            assert has_unload, (
                f"{cog_file.stem}.{cog_class} uses {', '.join(resource_types)} "
                f"but has no cog_unload method. Add:\n\n"
                f"    async def cog_unload(self) -> None:\n"
                f"        # Close resources here\n"
                f"        await self.session.close()  # if using aiohttp\n"
                f"        await self.db.dispose()     # if using async engine\n"
            )


class TestCogUnloadImplementation:
    """Verify cog_unload methods actually clean up resources."""

    def test_scryfall_closes_session(self) -> None:
        """Scryfall cog_unload should close session and db."""
        from cogs.scryfall import Cards

        # Verify the method exists and has the right signature
        assert hasattr(Cards, "cog_unload")
        method = Cards.cog_unload
        assert inspect.iscoroutinefunction(method)

        # Check the source contains the expected cleanup calls
        source = inspect.getsource(method)
        assert "self.session.close()" in source, "cog_unload should close self.session"
        assert "self.db.dispose()" in source, "cog_unload should dispose self.db"
