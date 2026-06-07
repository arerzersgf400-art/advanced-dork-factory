"""
Advanced Dork Factory — Core Generation Engine

Performance-first design:
- Lazy keyword reading via generators (never loads full file into RAM)
- Pre-classified templates: static vs TLD-expandable to minimise str.replace() calls
- Batched disk I/O: 10,000-line chunks flushed at once
- Mix Mode: random template shuffle per keyword for rate-limit evasion
"""

import json
import random
import sys
from pathlib import Path
from typing import Iterator, Optional

# ── Constants ──────────────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE: int = 10_000
TEMPLATE_PATH: Path = Path(__file__).resolve().parent / "dork_templates.json"


# ── Template Loading & Classification ──────────────────────────────────────

def load_templates(path: Optional[Path] = None) -> dict[str, list[str]]:
    """Load the curated dork templates from JSON.

    Args:
        path: Path to dork_templates.json.  Defaults to <project>/dork_templates.json.

    Returns:
        Dict mapping category name → list of template strings.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is malformed.
    """
    src = Path(path) if path else TEMPLATE_PATH
    if not src.exists():
        raise FileNotFoundError(f"Template file not found: {src}")
    with open(src, encoding="utf-8") as fh:
        data: dict[str, list[str]] = json.load(fh)
    return data


def classify_templates(
    templates: list[str],
) -> tuple[list[str], list[str]]:
    """Split template list into static (no {tld}) and TLD-expandable ({tld} present).

    This pre-classification avoids redundant ``str.replace('{tld}', …)`` on
    templates that do not contain the TLD placeholder, saving ~50 % of
    string-replace operations on typical template sets.

    Args:
        templates: Raw template strings.

    Returns:
        (static_list, tld_list)
    """
    static: list[str] = []
    tldable: list[str] = []
    for t in templates:
        if "{tld}" in t:
            tldable.append(t)
        else:
            static.append(t)
    return static, tldable


def resolve_categories(
    all_templates: dict[str, list[str]],
    requested: Optional[set[str]] = None,
) -> list[str]:
    """Return a flat, deduplicated list of templates for the chosen categories.

    Args:
        all_templates: Full category→templates mapping.
        requested: Set of category names, or ``None`` for "all".

    Returns:
        Flat list of template strings.
    """
    if requested is None:
        cats = list(all_templates.keys())
    else:
        available = set(all_templates.keys())
        cats = [c for c in requested if c in available]

    merged: list[str] = []
    seen: set[str] = set()
    for cat in cats:
        for t in all_templates[cat]:
            if t not in seen:
                seen.add(t)
                merged.append(t)
    return merged


# ── Keyword Iterator ───────────────────────────────────────────────────────

def read_keywords(
    path: Path,
    sample: Optional[int] = None,
) -> Iterator[str]:
    """Lazily read keywords from a file, one stripped line at a time.

    Never loads the full file into RAM — suitable for multi‑GB wordlists.

    Args:
        path: Path to keyword file.
        sample: If set, stop after yielding this many keywords.

    Yields:
        Lowercased, stripped, non‑empty keyword strings.
    """
    if not path.exists():
        raise FileNotFoundError(f"Keyword file not found: {path}")

    yielded: int = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            kw = raw.strip().lower()
            if not kw:
                continue
            yielded += 1
            yield kw
            if sample is not None and yielded >= sample:
                return


# ── Dork Generator ─────────────────────────────────────────────────────────

def generate_dorks(
    keywords: Iterator[str],
    static_templates: list[str],
    tld_templates: list[str],
    tlds: list[str],
    *,
    mix: bool = False,
    max_limit: Optional[int] = None,
) -> Iterator[str]:
    """Generate dork strings by expanding templates against keywords and TLDs.

    For every keyword, each template in *static_templates* yields one dork, and
    each template in *tld_templates* yields one dork **per TLD**.

    Args:
        keywords: Iterator of keyword strings.
        static_templates: Templates that do **not** contain ``{tld}``.
        tld_templates: Templates that **do** contain ``{tld}``.
        tlds: List of TLDs to expand (e.g. ``['com', 'org']``).
        mix: If True, shuffle the template list for every keyword.
        max_limit: Hard cap on total dorks produced (``None`` = unlimited).

    Yields:
        Fully‑rendered dork strings.
    """
    generated: int = 0

    for kw in keywords:
        if max_limit is not None and generated >= max_limit:
            return

        # ── Static templates (no TLD expansion) ──
        st = static_templates[:]
        if mix:
            random.shuffle(st)
        for tmpl in st:
            yield tmpl.replace("{keyword}", kw)
            generated += 1
            if max_limit is not None and generated >= max_limit:
                return

        # ── TLD‑expandable templates ──
        tt = tld_templates[:]
        if mix:
            random.shuffle(tt)
        for tmpl in tt:
            for tld in tlds:
                dork = tmpl.replace("{keyword}", kw).replace("{tld}", tld)
                yield dork
                generated += 1
                if max_limit is not None and generated >= max_limit:
                    return


# ── Batched File Writer ────────────────────────────────────────────────────

def write_batched(
    dorks: Iterator[str],
    output_path: Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Write dork strings to disk in large batches for maximum throughput.

    Accumulates *batch_size* lines in a list before a single ``.writelines()``
    call, minimising syscall overhead.

    Args:
        dorks: Iterator of dork strings.
        output_path: Destination file path.
        batch_size: Lines to buffer before flushing (default 10 000).

    Returns:
        Total number of lines written.
    """
    total: int = 0
    buffer: list[str] = []
    _append = buffer.append  # local binding – micro‑optimisation

    with open(output_path, "w", encoding="utf-8", buffering=1024 * 1024) as fh:
        for dork in dorks:
            _append(dork + "\n")
            if len(buffer) >= batch_size:
                fh.writelines(buffer)
                total += len(buffer)
                buffer.clear()
        # Final flush
        if buffer:
            fh.writelines(buffer)
            total += len(buffer)

    return total


# ── High‑Level Orchestration ───────────────────────────────────────────────

def run(
    keyword_path: Path,
    output_path: Path,
    *,
    categories: Optional[set[str]] = None,
    tlds: Optional[list[str]] = None,
    sample: Optional[int] = None,
    max_limit: Optional[int] = None,
    mix: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    template_path: Optional[Path] = None,
) -> int:
    """Orchestrate an end‑to‑end dork generation run.

    Args:
        keyword_path: Path to keyword file.
        output_path: Where to write the generated dorks.
        categories: Optional set of category names (``None`` = all).
        tlds: TLDs for expansion (default ``['com']``).
        sample: Limit keyword processing to first N.
        max_limit: Cap total dorks produced.
        mix: Random template shuffle per keyword.
        batch_size: Lines per disk‑flush chunk.
        template_path: Custom template JSON path.

    Returns:
        Total dorks written.

    Raises:
        FileNotFoundError: If keyword or template file missing.
        ValueError: If no matching templates found for requested categories.
    """
    if tlds is None:
        tlds = ["com"]

    # 1. Load & classify templates
    all_tmpl = load_templates(template_path)
    raw = resolve_categories(all_tmpl, categories)
    if not raw:
        available = ", ".join(sorted(all_tmpl.keys()))
        raise ValueError(
            f"No templates matched the requested categories. "
            f"Available: {available}"
        )
    static, tldable = classify_templates(raw)

    # 2. Keyword iterator
    keywords = read_keywords(keyword_path, sample=sample)

    # 3. Generate
    dorks = generate_dorks(
        keywords,
        static_templates=static,
        tld_templates=tldable,
        tlds=tlds,
        mix=mix,
        max_limit=max_limit,
    )

    # 4. Write
    total = write_batched(dorks, output_path, batch_size=batch_size)
    return total
