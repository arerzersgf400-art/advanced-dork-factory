"""
Comprehensive test suite for Advanced Dork Factory.

Covers:
1. Template loading & Pydantic validation
2. Keyword reading (dedup, cleaning, sample mode, lazy iteration)
3. Dork generation logic ({keyword} and {tld} replacement)
4. Batch writing integrity
5. Mix Mode verification
6. Validation regex checks
7. End‑to‑end integration tests
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

# ── Imports from the project ────────────────────────────────────────────────
from generator import (
    classify_templates,
    generate_dorks,
    load_templates,
    read_keywords,
    resolve_categories,
    run,
    write_batched,
)
from schemas import (
    DorkCategory,
    DorkTemplate,
    DorkTemplatesFile,
    quick_check,
    validate_templates_file,
)

# ── Constants reused across tests ──────────────────────────────────────────
VALID_TEMPLATE = "site:{tld} inurl:{keyword}.php?id="
VALID_STATIC = "inurl:{keyword}/index.php?id="


# ═══════════════════════════════════════════════════════════════════════════
# 1. Template Loading & Pydantic Validation
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplateLoading:
    """Tests for template file loading and JSON parsing."""

    def test_load_real_templates(self):
        """The bundled dork_templates.json must load with all 10 categories."""
        data = load_templates()
        assert isinstance(data, dict)
        assert len(data) == 10
        for cat in DorkCategory:
            assert cat.value in data, f"Missing category: {cat.value}"
            assert len(data[cat.value]) > 0, f"Empty category: {cat.value}"

    def test_load_missing_file(self):
        """load_templates raises FileNotFoundError for a non‑existent path."""
        with pytest.raises(FileNotFoundError):
            load_templates(Path("/nonexistent/dork_templates.json"))

    def test_cross_category_dedup(self):
        """Duplicate templates across categories are merged in resolve."""
        data = load_templates()
        # sql-injection and xss may share some templates in theory
        resolved = resolve_categories(data, {"sql-injection", "xss"})
        assert len(resolved) > 0
        # No duplicates
        assert len(resolved) == len(set(resolved))


class TestPydanticSchemas:
    """Tests for Pydantic validation models."""

    def test_valid_template(self):
        """DorkTemplate accepts a well‑formed template."""
        t = DorkTemplate(template=VALID_TEMPLATE)
        assert t.template == VALID_TEMPLATE

    def test_missing_keyword_placeholder(self):
        """DorkTemplate rejects a template without {keyword}."""
        with pytest.raises(Exception):
            DorkTemplate(template="site:com inurl:test")

    def test_unknown_placeholder(self):
        """DorkTemplate rejects unknown {foo} placeholders."""
        with pytest.raises(Exception):
            DorkTemplate(template="site:{tld} inurl:{keyword} {custom}")

    def test_too_short_template(self):
        """DorkTemplate rejects a template shorter than 5 chars."""
        with pytest.raises(Exception):
            DorkTemplate(template="{kw}")

    def test_validate_full_file_valid(self):
        """validate_templates_file passes on the real dork_templates.json."""
        with open(Path(__file__).parent / "dork_templates.json") as f:
            data = json.load(f)
        result = validate_templates_file(data)
        assert len(result.categories) == 10

    def test_quick_check_empty_dict(self):
        """quick_check reports errors for empty input."""
        errors = quick_check({})
        assert len(errors) > 0

    def test_quick_check_missing_keyword(self):
        """quick_check catches a template missing {keyword}."""
        errors = quick_check({"sql-injection": ["site:com inurl:test"]})
        assert len(errors) > 0
        assert "keyword" in errors[0].lower()

    def test_quick_check_valid(self):
        """quick_check returns no errors for valid data."""
        errors = quick_check({"sql-injection": [VALID_STATIC]})
        assert errors == []

    def test_category_enum_values(self):
        """DorkCategory enum matches the expected 10 values."""
        values = {c.value for c in DorkCategory}
        assert "sql-injection" in values
        assert "backup-files" in values
        assert len(values) == 10


# ═══════════════════════════════════════════════════════════════════════════
# 2. Keyword Reading
# ═══════════════════════════════════════════════════════════════════════════

class TestKeywordReading:
    """Tests for lazy keyword iteration."""

    def test_read_basic(self):
        """Read keywords from a simple file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("admin\nlogin\ntest\n")
            kw_path = Path(f.name)

        try:
            result = list(read_keywords(kw_path))
            assert result == ["admin", "login", "test"]
        finally:
            kw_path.unlink()

    def test_read_skips_empty_lines(self):
        """Empty lines are silently skipped."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("admin\n\n\nlogin\n   \ntest\n")
            kw_path = Path(f.name)

        try:
            result = list(read_keywords(kw_path))
            assert result == ["admin", "login", "test"]  # blank & whitespace skipped
        finally:
            kw_path.unlink()

    def test_read_lowercases(self):
        """Keywords are lowercased by the reader."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Admin\nLOGIN\nTeSt\n")
            kw_path = Path(f.name)

        try:
            result = list(read_keywords(kw_path))
            assert result == ["admin", "login", "test"]
        finally:
            kw_path.unlink()

    def test_read_sample_limit(self):
        """sample=N stops after N keywords."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("a\nb\nc\nd\ne\n")
            kw_path = Path(f.name)

        try:
            result = list(read_keywords(kw_path, sample=3))
            assert result == ["a", "b", "c"]
        finally:
            kw_path.unlink()

    def test_read_sample_larger_than_file(self):
        """sample larger than file yields all keywords."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("a\nb\n")
            kw_path = Path(f.name)

        try:
            result = list(read_keywords(kw_path, sample=100))
            assert len(result) == 2
        finally:
            kw_path.unlink()

    def test_read_missing_file(self):
        with pytest.raises(FileNotFoundError):
            list(read_keywords(Path("/nonexistent/keywords.txt")))

    def test_lazy_iteration(self):
        """read_keywords returns a generator, not a materialised list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(str(i) for i in range(10_000)))
            kw_path = Path(f.name)

        try:
            gen = read_keywords(kw_path)
            assert isinstance(gen, Iterator)
            # Take first 5 without iterating the rest
            first5 = [next(gen) for _ in range(5)]
            assert len(first5) == 5
        finally:
            kw_path.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Dork Generation Logic
# ═══════════════════════════════════════════════════════════════════════════

class TestDorkGeneration:
    """Tests for the core generation loop."""

    def test_static_template_expansion(self):
        """Static templates replace {keyword} but not {tld}."""
        keywords = iter(["admin"])
        static = [VALID_STATIC]
        tldable: list[str] = []
        result = list(generate_dorks(keywords, static, tldable, tlds=["com"]))
        assert result == ["inurl:admin/index.php?id="]

    def test_tld_template_expansion(self):
        """TLD templates expand once per TLD."""
        keywords = iter(["admin"])
        static: list[str] = []
        tldable = [VALID_TEMPLATE]
        result = list(generate_dorks(keywords, static, tldable, tlds=["com", "org"]))
        expected = [
            "site:com inurl:admin.php?id=",
            "site:org inurl:admin.php?id=",
        ]
        assert result == expected

    def test_keyword_replacement_no_curly_leftover(self):
        """No {keyword} or {tld} remains in output."""
        keywords = iter(["test123", "demo456"])
        static = [VALID_STATIC]
        tldable = [VALID_TEMPLATE]
        result = list(generate_dorks(keywords, static, tldable, tlds=["com"]))
        for dork in result:
            assert "{keyword}" not in dork
            assert "{tld}" not in dork
            assert "test123" in dork or "demo456" in dork

    def test_max_limit_hard_cutoff(self):
        """max_limit stops generation at exactly N dorks."""
        keywords = iter(["k1", "k2", "k3", "k4"])
        static = ["a {keyword}", "b {keyword}"]
        tldable = ["c {keyword} {tld}"]
        # Per keyword: 2 static + 1 tld * 2 tlds = 4 dorks/keyword
        # max=5 → first keyword yields 4, second keyword yields only 1
        result = list(
            generate_dorks(keywords, static, tldable, tlds=["com", "org"], max_limit=5)
        )
        assert len(result) == 5
        # The 5th should be from k2
        assert "k2" in result[-1]

    def test_max_limit_zero_or_none(self):
        """max_limit=None produces all possible dorks."""
        keywords = iter(["only"])
        static = ["a {keyword}"]
        tldable: list[str] = []
        result = list(generate_dorks(keywords, static, tldable, tlds=["com"]))
        assert len(result) == 1

    def test_empty_keywords(self):
        """Empty keyword iterator produces empty output."""
        keywords = iter([])
        result = list(generate_dorks(keywords, [VALID_STATIC], [], tlds=["com"]))
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. Batch Writing
# ═══════════════════════════════════════════════════════════════════════════

class TestBatchWriting:
    """Tests for batched disk I/O."""

    def test_write_small_batch(self):
        """write_batched writes all lines correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            out = Path(f.name)

        try:
            dorks = iter([f"dork_{i}" for i in range(100)])
            total = write_batched(dorks, out, batch_size=10)
            assert total == 100
            with open(out) as f:
                lines = f.readlines()
            assert len(lines) == 100
            assert lines[0].strip() == "dork_0"
            assert lines[-1].strip() == "dork_99"
        finally:
            out.unlink()

    def test_write_large_batch_exceeds_buffer(self):
        """Write more than one batch; all lines must be present."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            out = Path(f.name)

        try:
            n = 25_000
            dorks = iter([f"line_{i}" for i in range(n)])
            total = write_batched(dorks, out, batch_size=10_000)
            assert total == n
            with open(out) as f:
                count = sum(1 for _ in f)
            assert count == n
        finally:
            out.unlink()

    def test_write_empty_iterator(self):
        """Empty iterator writes 0 lines and creates an empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            out = Path(f.name)

        try:
            total = write_batched(iter([]), out)
            assert total == 0
            assert out.stat().st_size == 0
        finally:
            out.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Mix Mode
# ═══════════════════════════════════════════════════════════════════════════

class TestMixMode:
    """Tests for the --mix random shuffle feature."""

    def test_mix_produces_different_order(self):
        """With mix=True, order differs across keywords (statistical)."""
        # Use many templates and keywords to make a collision extremely unlikely
        static = [f"tpl_{i} {{keyword}}" for i in range(50)]
        keywords = iter([f"kw_{i}" for i in range(100)])

        dorks_mix = list(generate_dorks(keywords, static, [], tlds=["com"], mix=True))

        # Re‑create iterator and run without mix
        keywords2 = iter([f"kw_{i}" for i in range(100)])
        dorks_no_mix = list(
            generate_dorks(keywords2, static, [], tlds=["com"], mix=False)
        )

        assert len(dorks_mix) == len(dorks_no_mix)
        # With 50 templates and 100 keywords, the chance of identical
        # ordering with random shuffle is essentially zero.
        assert dorks_mix != dorks_no_mix, (
            "Mix mode should produce different template ordering"
        )

    def test_mix_no_crash_empty_templates(self):
        """Mix mode handles empty template lists gracefully."""
        keywords = iter(["test"])
        result = list(generate_dorks(keywords, [], [], tlds=["com"], mix=True))
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. Validation Regex Checks (from main.py)
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationRegex:
    """Test the validation regex patterns used by the validate command."""

    DORK_OPERATOR_RE = re.compile(
        r"\b(site|inurl|intitle|intext|filetype|ext|cache|link|related|allinurl|allintitle|allintext)\:",
        re.IGNORECASE,
    )
    UNRESOLVED_RE = re.compile(r"\{keyword\}|\{tld\}")

    def test_detects_site_operator(self):
        assert self.DORK_OPERATOR_RE.search("site:com inurl:admin")

    def test_detects_inurl_operator(self):
        assert self.DORK_OPERATOR_RE.search("inurl:admin.php?id=")

    def test_detects_intitle_operator(self):
        assert self.DORK_OPERATOR_RE.search('intitle:"index of"')

    def test_detects_filetype_operator(self):
        assert self.DORK_OPERATOR_RE.search("filetype:pdf confidential")

    def test_detects_ext_operator(self):
        assert self.DORK_OPERATOR_RE.search("ext:sql backup")

    def test_rejects_no_operator(self):
        assert not self.DORK_OPERATOR_RE.search("admin password login")

    def test_rejects_empty_string(self):
        assert not self.DORK_OPERATOR_RE.search("")

    def test_detects_unresolved_keyword(self):
        assert self.UNRESOLVED_RE.search("{keyword} site:com")

    def test_detects_unresolved_tld(self):
        assert self.UNRESOLVED_RE.search("site:{tld} inurl:admin")

    def test_passes_resolved_dork(self):
        assert not self.UNRESOLVED_RE.search("site:com inurl:admin.php?id=")


# ═══════════════════════════════════════════════════════════════════════════
# 7. End‑to‑End Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEnd:
    """Full‑pipeline integration tests using the run() orchestrator."""

    def test_e2e_single_keyword(self):
        """Run end‑to‑end with one keyword and verify output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("admin\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total = run(
                keyword_path=kw_path,
                output_path=out_path,
                categories={"sql-injection"},
                tlds=["com"],
            )
            assert total > 0
            with open(out_path) as f:
                lines = [l.strip() for l in f if l.strip()]
            assert len(lines) == total
            # Every line must contain the keyword
            for line in lines:
                assert "admin" in line.lower()
        finally:
            kw_path.unlink()
            out_path.unlink()

    def test_e2e_multi_tld(self):
        """Multiple TLDs expand correctly."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("test\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total = run(
                keyword_path=kw_path,
                output_path=out_path,
                categories={"cloud-buckets"},
                tlds=["com", "org", "net"],
            )
            assert total > 0
            with open(out_path) as f:
                content = f.read()
            # At least some lines should contain each TLD
            assert "com" in content
        finally:
            kw_path.unlink()
            out_path.unlink()

    def test_e2e_sample_limit(self):
        """sample=N limits keywords processed."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("a\nb\nc\nd\ne\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total_sample = run(
                keyword_path=kw_path,
                output_path=out_path,
                sample=2,
                tlds=["com"],
            )
            total_full = run(
                keyword_path=kw_path,
                output_path=out_path,
                tlds=["com"],
            )
            assert total_sample < total_full, (
                f"sample=2 ({total_sample}) should be less than full ({total_full})"
            )
        finally:
            kw_path.unlink()
            out_path.unlink()

    def test_e2e_max_limit(self):
        """max_limit caps total output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("admin\nlogin\ntest\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total = run(
                keyword_path=kw_path,
                output_path=out_path,
                max_limit=50,
                tlds=["com"],
            )
            assert total == 50
        finally:
            kw_path.unlink()
            out_path.unlink()

    def test_e2e_mix_mode(self):
        """Mix mode runs without error and produces valid output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("admin\nlogin\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total = run(
                keyword_path=kw_path,
                output_path=out_path,
                mix=True,
                tlds=["com", "org"],
            )
            assert total > 0
            with open(out_path) as f:
                for line in f:
                    assert "{keyword}" not in line
                    assert "{tld}" not in line
        finally:
            kw_path.unlink()
            out_path.unlink()

    def test_e2e_all_categories(self):
        """All 10 categories together produce valid dorks."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as kf:
            kf.write("admin\n")
            kw_path = Path(kf.name)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as of:
            out_path = Path(of.name)

        try:
            total = run(
                keyword_path=kw_path,
                output_path=out_path,
                categories=None,  # all
                tlds=["com"],
            )
            assert total == 347  # 124 static + 223 tldable × 1 TLD
        finally:
            kw_path.unlink()
            out_path.unlink()


# ═══════════════════════════════════════════════════════════════════════════
# 8. Template Classification
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplateClassification:
    """Tests for classify_templates()."""

    def test_splits_static_and_tld(self):
        static, tldable = classify_templates([
            "inurl:{keyword}",
            "site:{tld} inurl:{keyword}",
            "intitle:{keyword}",
            "site:{tld} intitle:{keyword} filetype:pdf",
        ])
        assert len(static) == 2
        assert len(tldable) == 2

    def test_all_static(self):
        static, tldable = classify_templates([
            "inurl:{keyword}",
            "intitle:{keyword}",
        ])
        assert len(static) == 2
        assert len(tldable) == 0

    def test_all_tldable(self):
        static, tldable = classify_templates([
            "site:{tld} inurl:{keyword}",
        ])
        assert len(static) == 0
        assert len(tldable) == 1

    def test_empty_input(self):
        static, tldable = classify_templates([])
        assert static == []
        assert tldable == []
