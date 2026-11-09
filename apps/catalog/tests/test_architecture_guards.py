import ast
import re
from pathlib import Path

from django.test import SimpleTestCase


WRITE_METHODS = {
    "add",
    "bulk_create",
    "clear",
    "create",
    "delete",
    "get_or_create",
    "remove",
    "set",
    "update",
    "update_or_create",
}


def _dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def scan_stock_writes(source):
    tree = ast.parse(source)
    violations = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            targets = node.targets if isinstance(node, ast.Assign) else [
                node.target if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else None
            ]
            if isinstance(node, ast.Delete):
                targets = node.targets
            for target in targets:
                if target is not None and any(
                    isinstance(child, ast.Attribute) and child.attr == "stock_quantity"
                    for child in ast.walk(target)
                ):
                    violations.append(node.lineno)

        if isinstance(node, ast.Call):
            method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if method in {"update", "create", "bulk_create"} and any(
                keyword.arg == "stock_quantity" for keyword in node.keywords
            ):
                violations.append(node.lineno)
            if _dotted_name(node.func).split(".")[-1] == "F" and node.args:
                argument = node.args[0]
                if (
                    isinstance(argument, ast.Constant) and argument.value == "stock_quantity"
                ) or (isinstance(argument, ast.Name) and argument.id == "stock_quantity"):
                    violations.append(node.lineno)

    return violations


def scan_pricing_tier_writes(source):
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in WRITE_METHODS:
            continue
        receiver = ast.unparse(node.func.value)
        if re.search(r"\bPricingTier\.objects\b", receiver) or re.search(
            r"\.pricing_tiers\b", receiver
        ):
            violations.append(node.lineno)
    return violations


def scan_stocklog_creations(source):
    tree = ast.parse(source)
    violations = []
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    constructed_names = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == "StockLog":
            parent = parents.get(node)
            if (
                isinstance(parent, ast.Attribute)
                and parent.attr == "save"
                and isinstance(parents.get(parent), ast.Call)
                and parents[parent].func is parent
            ):
                violations.append(node.lineno)
            elif isinstance(parent, (ast.Assign, ast.AnnAssign)):
                targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
                constructed_names.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "save"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in constructed_names
        ):
            violations.append(node.lineno)
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"create", "bulk_create"}:
            receiver = ast.unparse(node.func.value)
            if re.search(r"\bStockLog\.objects\b", receiver):
                violations.append(node.lineno)
    return violations


def scan_pricing_imports(source):
    tree = ast.parse(source)
    violations = []

    class ModuleImportScanner(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            return

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Import(self, node):
            if any(
                alias.name == "django.db"
                or alias.name.startswith("django.db.")
                or alias.name == "apps.catalog.models"
                for alias in node.names
            ):
                violations.append(node.lineno)

        def visit_ImportFrom(self, node):
            module = node.module or ""
            if (
                module == "django.db"
                or module.startswith("django.db.")
                or module == "apps.catalog.models"
                or (node.level and any(alias.name == "models" for alias in node.names))
            ):
                violations.append(node.lineno)

    scanner = ModuleImportScanner()
    for node in tree.body:
        scanner.visit(node)
    return violations


def scan_float_usage(source):
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            violations.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
            violations.append(node.lineno)
    return violations


def _source_files(repo_root):
    for path in (repo_root / "apps").rglob("*.py"):
        if "tests" not in path.parts and "migrations" not in path.parts:
            yield path


class ArchitectureGuardScannerTests(SimpleTestCase):
    def test_stock_scanner_detects_assignment_keyword_and_f_expression(self):
        good = "variant.name = 'Rack'\nF('name')\n"
        bad = (
            "variant.stock_quantity = 3\n"
            "ProductVariant.objects.update(stock_quantity=4)\n"
            "F('stock_quantity')\n"
        )
        self.assertEqual(scan_stock_writes(good), [])
        self.assertEqual(len(scan_stock_writes(bad)), 3)

    def test_tier_scanner_detects_model_and_related_manager_writes(self):
        good = "variant.pricing_tiers.all()\nPricingTier.objects.filter(pk=1).values()\n"
        bad = "PricingTier.objects.bulk_create(rows)\nvariant.pricing_tiers.clear()\n"
        self.assertEqual(scan_pricing_tier_writes(good), [])
        self.assertEqual(len(scan_pricing_tier_writes(bad)), 2)

    def test_stocklog_scanner_detects_manager_and_instance_creation(self):
        good = "StockLog.objects.filter(pk=1)\nentry = StockLog(change=1)\n"
        bad = (
            "StockLog.objects.bulk_create(rows)\n"
            "StockLog(change=1).save()\n"
            "entry = StockLog(change=2)\nentry.save()\n"
        )
        self.assertEqual(scan_stocklog_creations(good), [])
        self.assertEqual(len(scan_stocklog_creations(bad)), 3)

    def test_import_and_float_scanners_detect_bad_source(self):
        good_import = "def f():\n    from apps.catalog.models import Product\n"
        bad_import = (
            "if True:\n    import django.db.models\n"
            "import apps.catalog.models\n"
            "from . import models\n"
        )
        good_numeric = "price = 100\n"
        bad_numeric = "ratio = 1.5\nvalue = float('2')\n"
        self.assertEqual(scan_pricing_imports(good_import), [])
        self.assertEqual(len(scan_pricing_imports(bad_import)), 3)
        self.assertEqual(scan_float_usage(good_numeric), [])
        self.assertEqual(len(scan_float_usage(bad_numeric)), 2)


class CatalogArchitectureGuards(SimpleTestCase):
    def test_application_source_obeys_write_and_numeric_boundaries(self):
        repo_root = Path(__file__).resolve().parents[3]
        violations = []
        for path in _source_files(repo_root):
            relative = path.relative_to(repo_root).as_posix()
            source = path.read_text(encoding="utf-8")
            if relative != "apps/catalog/inventory.py":
                violations.extend((relative, line, "stock write") for line in scan_stock_writes(source))
            if relative != "apps/catalog/pricing.py":
                violations.extend((relative, line, "pricing tier write") for line in scan_pricing_tier_writes(source))
            if relative != "apps/catalog/inventory.py":
                violations.extend((relative, line, "StockLog creation") for line in scan_stocklog_creations(source))

        for relative in (
            "apps/catalog/pricing.py",
            "apps/catalog/inventory.py",
            "apps/catalog/constants.py",
            "apps/catalog/services.py",
        ):
            source = (repo_root / relative).read_text(encoding="utf-8")
            violations.extend((relative, line, "float usage") for line in scan_float_usage(source))

        pricing_source = (repo_root / "apps/catalog/pricing.py").read_text(encoding="utf-8")
        violations.extend(
            ("apps/catalog/pricing.py", line, "module-level database import")
            for line in scan_pricing_imports(pricing_source)
        )
        self.assertEqual(violations, [])
