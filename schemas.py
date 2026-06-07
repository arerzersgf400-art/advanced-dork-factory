"""
Pydantic models for validating the Advanced Dork Factory configuration.

Every template in ``dork_templates.json`` must match the ``DorkTemplate``
schema on load, ensuring the file is well‑formed before it reaches the
generation engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)


# ── Category Enum ──────────────────────────────────────────────────────────

class DorkCategory(str, Enum):
    """Recognised dork categories (must match keys in dork_templates.json)."""

    SQL_INJECTION = "sql-injection"
    XSS = "xss"
    LFI = "lfi"
    EXPOSED_DOCUMENTS = "exposed-documents"
    OPEN_REDIRECT = "open-redirect"
    SUBDOMAIN_DISCOVERY = "subdomain-discovery"
    CLOUD_BUCKETS = "cloud-buckets"
    JENKINS_DASHBOARD = "jenkins-dashboard"
    GIT_REPO_EXPOSURE = "git-repo-exposure"
    BACKUP_FILES = "backup-files"


# ── Single Template ────────────────────────────────────────────────────────

class DorkTemplate(BaseModel):
    """A single dork template string.

    Must contain at least ``{keyword}`` and may optionally contain ``{tld}``.
    """

    template: str = Field(
        ...,
        min_length=5,
        description="Dork template with {keyword} (required) and optional {tld}",
    )

    @field_validator("template")
    @classmethod
    def must_have_keyword(cls, v: str) -> str:
        if "{keyword}" not in v:
            raise ValueError('Template must contain the "{keyword}" placeholder')
        return v

    @field_validator("template")
    @classmethod
    def no_unknown_placeholders(cls, v: str) -> str:
        """Flag any placeholder that is NOT {keyword} or {tld}."""
        import re

        found = set(re.findall(r"\{(\w+)\}", v))
        allowed = {"keyword", "tld"}
        unknown = found - allowed
        if unknown:
            raise ValueError(
                f"Unknown placeholder(s) in template: {unknown}. "
                f"Only {{keyword}} and {{tld}} are allowed."
            )
        return v


# ── Templates File Schema ──────────────────────────────────────────────────

class DorkTemplatesFile(BaseModel):
    """Full schema for ``dork_templates.json``.

    The JSON root must be a dictionary mapping category names (str) to lists
    of template strings.
    """

    categories: dict[str, list[str]] = Field(
        ...,
        min_length=1,
        description="Mapping of category name → list of template strings",
    )

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        if not v:
            raise ValueError("At least one category is required")

        valid_categories = {c.value for c in DorkCategory}
        for cat_name, templates in v.items():
            # Warn but don't reject unknown categories (forward‑compat)
            if not isinstance(templates, list):
                raise ValueError(
                    f"Category '{cat_name}' must contain a list of templates, "
                    f"got {type(templates).__name__}"
                )
            if len(templates) == 0:
                raise ValueError(f"Category '{cat_name}' has zero templates")

            for i, t in enumerate(templates):
                if not isinstance(t, str):
                    raise ValueError(
                        f"Template {i} in '{cat_name}' must be a string, "
                        f"got {type(t).__name__}"
                    )
                if "{keyword}" not in t:
                    raise ValueError(
                        f"Template {i} in '{cat_name}' is missing "
                        f"'{{keyword}}' placeholder: {t!r}"
                    )

        return v


# ── Helper: validate on load ───────────────────────────────────────────────

def validate_templates_file(data: dict[str, Any]) -> DorkTemplatesFile:
    """Validate a loaded ``dork_templates.json`` dict against the schema.

    Args:
        data: Raw dict from ``json.load()``.

    Returns:
        Validated ``DorkTemplatesFile`` instance.

    Raises:
        pydantic.ValidationError: If the data fails validation.
    """
    return DorkTemplatesFile(categories=data)


def quick_check(data: dict[str, Any]) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    try:
        validate_templates_file(data)
        return []
    except ValidationError as e:
        return [str(err) for err in e.errors()]
