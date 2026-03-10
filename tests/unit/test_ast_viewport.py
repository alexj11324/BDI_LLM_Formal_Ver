"""Unit tests for ``bdi_llm.swe_bench.ast_viewport``."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import pytest

from bdi_llm.swe_bench.ast_viewport import (
    extract_entity,
    extract_test_function,
    file_skeleton,
    file_skeleton_with_context,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SOURCE = textwrap.dedent("""\
    import os
    from pathlib import Path

    CONSTANT = 42

    class Card:
        \"\"\"Represents a FITS header card.\"\"\"

        _len = 80

        def __init__(self, keyword='', value=None):
            \"\"\"Create a new Card.\"\"\"
            self._keyword = keyword
            self._value = value
            self._image = None

        def _parse(self, image):
            \"\"\"Parse the card image.\"\"\"
            self._image = image
            return self

        async def async_method(self, x: int) -> str:
            \"\"\"An async method.\"\"\"
            return str(x)

    class Verification:
        \"\"\"Utility for verifying cards.\"\"\"

        def verify(self, card):
            \"\"\"Verify a single card.\"\"\"
            return True

    def module_function(a, b):
        \"\"\"A module-level function.\"\"\"
        return a + b

    def another_function():
        pass
""")

SYNTAX_ERROR_SOURCE = textwrap.dedent("""\
    import os
    class Broken
        def foo(self):
            pass
    def bar():
        pass
""")

TEST_SOURCE = textwrap.dedent("""\
    import pytest

    class TestCard:
        def test_init(self):
            card = Card()
            assert card._keyword == ''

        def test_parse(self):
            card = Card()
            card._parse('image')
            assert card._image == 'image'

    def test_module_function():
        assert module_function(1, 2) == 3

    class TestVerification:
        def test_verify(self):
            v = Verification()
            assert v.verify(None) is True
""")


# ---------------------------------------------------------------------------
# file_skeleton
# ---------------------------------------------------------------------------

class TestFileSkeleton:
    """Tests for ``file_skeleton``."""

    def test_includes_imports(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "import os" in skeleton
        assert "from pathlib import Path" in skeleton

    def test_includes_module_constant(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "CONSTANT = 42" in skeleton

    def test_includes_class_signatures(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "class Card:" in skeleton
        assert "class Verification:" in skeleton

    def test_includes_method_signatures(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "def __init__" in skeleton
        assert "def _parse" in skeleton
        assert "async def async_method" in skeleton

    def test_includes_docstrings(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "Represents a FITS header card." in skeleton
        assert "Create a new Card." in skeleton

    def test_body_replaced_with_ellipsis(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "..." in skeleton
        # Full body should NOT be present
        assert "self._image = image" not in skeleton

    def test_compact_output(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        line_count = len(skeleton.strip().splitlines())
        # Should be much shorter than original
        assert line_count < len(SAMPLE_SOURCE.splitlines())

    def test_includes_module_functions(self):
        skeleton = file_skeleton(SAMPLE_SOURCE)
        assert "def module_function" in skeleton
        assert "def another_function" in skeleton

    def test_syntax_error_fallback(self):
        skeleton = file_skeleton(SYNTAX_ERROR_SOURCE)
        assert "import os" in skeleton
        assert "class Broken" in skeleton
        assert "def foo" in skeleton
        assert "def bar" in skeleton


# ---------------------------------------------------------------------------
# extract_entity
# ---------------------------------------------------------------------------

class TestExtractEntity:
    """Tests for ``extract_entity``."""

    def test_extract_class(self):
        code = extract_entity(SAMPLE_SOURCE, "Card")
        assert "class Card:" in code
        assert "def __init__" in code
        assert "def _parse" in code
        assert "self._image = image" in code  # full body present

    def test_extract_function(self):
        code = extract_entity(SAMPLE_SOURCE, "module_function")
        assert "def module_function" in code
        assert "return a + b" in code

    def test_extract_method(self):
        code = extract_entity(SAMPLE_SOURCE, "_parse")
        assert "def _parse" in code
        assert "self._image = image" in code

    def test_fuzzy_match(self):
        code = extract_entity(SAMPLE_SOURCE, "module_func")
        assert "def module_function" in code

    def test_not_found_returns_empty(self):
        code = extract_entity(SAMPLE_SOURCE, "nonexistent_entity")
        assert code == ""

    def test_empty_name_returns_empty(self):
        code = extract_entity(SAMPLE_SOURCE, "")
        assert code == ""

    def test_syntax_error_returns_empty(self):
        code = extract_entity(SYNTAX_ERROR_SOURCE, "foo")
        assert code == ""


# ---------------------------------------------------------------------------
# file_skeleton_with_context
# ---------------------------------------------------------------------------

class TestFileSkeletonWithContext:
    """Tests for ``file_skeleton_with_context``."""

    def test_contains_skeleton_header(self):
        result = file_skeleton_with_context(SAMPLE_SOURCE, "Card")
        assert "=== FILE SKELETON ===" in result

    def test_contains_target_header(self):
        result = file_skeleton_with_context(SAMPLE_SOURCE, "Card")
        assert "=== TARGET: Card ===" in result

    def test_target_has_full_body(self):
        result = file_skeleton_with_context(SAMPLE_SOURCE, "_parse")
        assert "self._image = image" in result

    def test_missing_entity_fallback(self):
        result = file_skeleton_with_context(SAMPLE_SOURCE, "nonexistent")
        assert "not found" in result
        # Should include first 4000 chars of source as fallback
        assert "import os" in result


# ---------------------------------------------------------------------------
# extract_test_function
# ---------------------------------------------------------------------------

class TestExtractTestFunction:
    """Tests for ``extract_test_function``."""

    def test_simple_function(self):
        code = extract_test_function(TEST_SOURCE, "test_module_function")
        assert "def test_module_function" in code
        assert "assert module_function(1, 2) == 3" in code

    def test_class_method_double_colon(self):
        code = extract_test_function(TEST_SOURCE, "TestCard::test_init")
        assert "def test_init" in code
        assert "card._keyword" in code

    def test_class_method_dot(self):
        code = extract_test_function(TEST_SOURCE, "TestCard.test_parse")
        assert "def test_parse" in code

    def test_not_found_returns_empty(self):
        code = extract_test_function(TEST_SOURCE, "nonexistent_test")
        assert code == ""

    def test_empty_name_returns_empty(self):
        code = extract_test_function(TEST_SOURCE, "")
        assert code == ""
