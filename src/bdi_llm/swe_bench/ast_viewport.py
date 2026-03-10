"""AST-aware viewport utilities for SWE-bench code editing.

Provides functions to generate compact file skeletons and extract specific
code entities (classes/functions) by name.  These replace the naive
``content[:12000]`` truncation with a *focused viewport* — the model sees
the full structural outline of a file plus the complete source of the entity
it actually needs to modify.

Three public helpers:
- ``file_skeleton()``  – compact structural outline of a Python file
- ``extract_entity()`` – full source of a named class/function
- ``file_skeleton_with_context()`` – skeleton + expanded target entity
- ``extract_test_function()`` – extract a test function (supports TestClass::method)
"""

from __future__ import annotations

import ast

# ---------------------------------------------------------------------------
# file_skeleton
# ---------------------------------------------------------------------------

def file_skeleton(source: str) -> str:
    """Return a compact structural skeleton of a Python source file.

    The skeleton includes:
    - All ``import`` / ``from … import`` statements
    - Module-level variable assignments
    - ``class`` signatures with first-line docstrings
    - ``def`` / ``async def`` signatures with parameters and first-line docstrings
    - Function/method bodies replaced with ``...``

    If the source has syntax errors that prevent ``ast.parse``, we fall back
    to a regex-based extraction of ``class`` and ``def`` lines.

    Returns a string typically < 200 lines for most real-world files.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _regex_fallback_skeleton(source)

    lines = source.splitlines()
    parts: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # Emit the original import line(s)
            for ln in range(node.lineno - 1, node.end_lineno or node.lineno):
                parts.append(lines[ln])

        elif isinstance(node, ast.Assign):
            # Module-level variable assignments
            for ln in range(node.lineno - 1, node.end_lineno or node.lineno):
                parts.append(lines[ln])

        elif isinstance(node, (ast.AnnAssign,)):
            # Annotated assignments at module level
            for ln in range(node.lineno - 1, node.end_lineno or node.lineno):
                parts.append(lines[ln])

        elif isinstance(node, ast.ClassDef):
            parts.append("")  # blank separator
            parts.append(_class_skeleton(node, lines))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append("")  # blank separator
            parts.append(_func_skeleton(node, lines, indent=""))

    return "\n".join(parts)


def _class_skeleton(node: ast.ClassDef, lines: list[str]) -> str:
    """Build a skeleton for a class: signature + docstring + method sigs."""
    # Class declaration line
    class_line = lines[node.lineno - 1]
    parts = [class_line]

    # Docstring (first line only)
    docstring = _first_docstring_line(node)
    if docstring:
        parts.append(f'    """{docstring}"""')

    # Methods
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append("")
            parts.append(_func_skeleton(child, lines, indent="    "))
        elif isinstance(child, ast.Assign):
            # Class-level attributes
            for ln in range(child.lineno - 1, child.end_lineno or child.lineno):
                parts.append("    " + lines[ln].strip())

    return "\n".join(parts)


def _func_skeleton(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    lines: list[str],
    indent: str = "",
) -> str:
    """Build a skeleton for a function: signature + docstring + ``...``."""
    # Decorators
    parts: list[str] = []
    for decorator in node.decorator_list:
        dec_line = lines[decorator.lineno - 1]
        parts.append(dec_line)

    # Function signature (may span multiple lines)
    sig_lines: list[str] = []
    for ln in range(node.lineno - 1, (node.end_lineno or node.lineno)):
        line = lines[ln]
        sig_lines.append(line)
        if ":" in line and not line.rstrip().endswith(","):
            break
    parts.extend(sig_lines)

    # Docstring (first line only)
    docstring = _first_docstring_line(node)
    if docstring:
        parts.append(f'{indent}    """{docstring}"""')

    # Body placeholder
    parts.append(f"{indent}    ...")

    return "\n".join(parts)


def _first_docstring_line(node: ast.AST) -> str | None:
    """Extract the first line of a docstring from a class or function node."""
    if (
        node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    ):
        val = node.body[0].value
        raw = val.value
        if isinstance(raw, str):
            first = raw.strip().split("\n")[0].strip()
            return first
    return None


def _regex_fallback_skeleton(source: str) -> str:
    """Fallback skeleton using regex when AST parsing fails."""
    parts: list[str] = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if (
            stripped.startswith("class ")
            or stripped.startswith("def ")
            or stripped.startswith("async def ")
            or stripped.startswith("import ")
            or stripped.startswith("from ")
        ):
            parts.append(line)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# extract_entity
# ---------------------------------------------------------------------------

def extract_entity(source: str, entity_name: str) -> str:
    """Extract the full source of a named class or function from *source*.

    Parameters
    ----------
    source : str
        Complete Python source code of the file.
    entity_name : str
        Name of the class or function to extract.  If no exact match is
        found, we try a substring (fuzzy) match.

    Returns
    -------
    str
        The complete source code (from ``node.lineno`` to
        ``node.end_lineno``) of the matched entity, or ``""`` if not found.
    """
    if not entity_name:
        return ""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    lines = source.splitlines()

    # Pass 1: exact match (including nested classes/methods)
    match = _find_node(tree, entity_name, exact=True)
    if match:
        return _source_slice(lines, match)

    # Pass 2: fuzzy (substring) match
    match = _find_node(tree, entity_name, exact=False)
    if match:
        return _source_slice(lines, match)

    return ""


def _find_node(
    tree: ast.AST, name: str, *, exact: bool
) -> ast.AST | None:
    """DFS search for a class/function node matching *name*."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if exact and node.name == name:
                return node
            if not exact and name in node.name:
                return node
    return None


def _source_slice(lines: list[str], node: ast.AST) -> str:
    """Return the raw source lines for a given AST node."""
    start = node.lineno - 1  # 0-indexed
    end = node.end_lineno or node.lineno  # end_lineno is 1-indexed inclusive
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# file_skeleton_with_context
# ---------------------------------------------------------------------------

def file_skeleton_with_context(source: str, entity_name: str) -> str:
    """Return file skeleton plus the full source of *entity_name*.

    Format::

        === FILE SKELETON ===
        {skeleton}

        === TARGET: {entity_name} ===
        {entity_code}
    """
    skeleton = file_skeleton(source)
    entity_code = extract_entity(source, entity_name)

    parts = [f"=== FILE SKELETON ===\n{skeleton}"]
    if entity_code:
        parts.append(f"\n=== TARGET: {entity_name} ===\n{entity_code}")
    else:
        parts.append(
            f"\n=== TARGET: {entity_name} === (not found — showing first 4000 chars)\n"
            + source[:4000]
        )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# extract_test_function
# ---------------------------------------------------------------------------

def extract_test_function(test_file_source: str, test_name: str) -> str:
    """Extract a test function from *test_file_source* by *test_name*.

    Supports ``::`` separators: e.g. ``TestClass::test_method`` will first
    find ``TestClass`` and then look for ``test_method`` inside it.

    Parameters
    ----------
    test_file_source : str
        Full source of the test file.
    test_name : str
        Name of the test function, optionally qualified with
        ``ClassName::method_name`` or ``ClassName.method_name``.

    Returns
    -------
    str
        Complete source of the matched test function, or ``""`` if not found.
    """
    if not test_name:
        return ""

    try:
        tree = ast.parse(test_file_source)
    except SyntaxError:
        return ""

    lines = test_file_source.splitlines()

    # Handle `TestClass::test_method` or `TestClass.test_method` notation
    sep = "::" if "::" in test_name else ("." if "." in test_name else None)
    if sep:
        parts_list = test_name.split(sep)
        if len(parts_list) == 2:
            class_name, method_name = parts_list
            return _extract_class_method(tree, lines, class_name, method_name)

    # Simple function name lookup
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == test_name:
                return _source_slice(lines, node)

    # Fuzzy fallback
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if test_name in node.name:
                return _source_slice(lines, node)

    return ""


def _extract_class_method(
    tree: ast.AST,
    lines: list[str],
    class_name: str,
    method_name: str,
) -> str:
    """Extract a method from a specific class."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == method_name:
                        return _source_slice(lines, child)
            # Fuzzy method match
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if method_name in child.name:
                        return _source_slice(lines, child)
            break

    # Fallback: try fuzzy class match
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and class_name in node.name:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == method_name or method_name in child.name:
                        return _source_slice(lines, child)
            break

    return ""
