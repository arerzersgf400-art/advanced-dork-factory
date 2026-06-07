#!/usr/bin/env python3
"""
Advanced Dork Factory — Professional CLI for Google Dork Generation

Built with Typer + Rich.  Generates multi‑operator Google dork strings from
curated templates across 10 OSINT categories.

Usage:
    python main.py generate -i keywords.txt -o dorks.txt -c sql-injection,xss -t com,org --mix
    python main.py validate dorks.txt
"""

from __future__ import annotations

import random
import re
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from generator import (
    DEFAULT_BATCH_SIZE,
    load_templates,
    resolve_categories,
    run as generate_run,
)

# ── Rich console ───────────────────────────────────────────────────────────
console = Console()
app = typer.Typer(
    name="dork-factory",
    help="Advanced Dork Factory — generate & validate Google dork queries.",
    add_completion=False,
)

# ── Constants ──────────────────────────────────────────────────────────────
CATEGORY_NAMES: list[str] = [
    "sql-injection",
    "xss",
    "lfi",
    "exposed-documents",
    "open-redirect",
    "subdomain-discovery",
    "cloud-buckets",
    "jenkins-dashboard",
    "git-repo-exposure",
    "backup-files",
]

# Regex: must contain at least one valid Google dork operator
DORK_OPERATOR_RE = re.compile(
    r"\b(site|inurl|intitle|intext|filetype|ext|cache|link|related|allinurl|allintitle|allintext)\:",
    re.IGNORECASE,
)

# Detect unresolved placeholders
UNRESOLVED_PLACEHOLDER_RE = re.compile(r"\{keyword\}|\{tld\}")


# ── Disclaimer banner ──────────────────────────────────────────────────────

def show_banner() -> None:
    """Display ethical‑use disclaimer and project banner."""
    banner = Text.from_markup(
        "[bold cyan]╔══════════════════════════════════════════════════════════╗\n"
        "║        [bold yellow]Advanced Dork Factory[/bold yellow]  —  OSINT Dork Generator        ║\n"
        "╠══════════════════════════════════════════════════════════╣\n"
        "║  [dim]⚖️  FOR AUTHORIZED SECURITY RESEARCH ONLY[/dim]                ║\n"
        "║  [dim]• Bug Bounty programs with explicit scope[/dim]               ║\n"
        "║  [dim]• Penetration testing with written permission[/dim]           ║\n"
        "║  [dim]• Defensive OSINT & threat intelligence[/dim]                 ║\n"
        "║  [dim]• Educational research[/dim]                                  ║\n"
        "╠══════════════════════════════════════════════════════════╣\n"
        "║  [bold red]⚠️  UNAUTHORIZED USE IS ILLEGAL[/bold red]                           ║\n"
        "║  [dim]The author assumes no liability for misuse.[/dim]              ║\n"
        "╚══════════════════════════════════════════════════════════╝[/bold cyan]"
    )
    console.print(banner)
    console.print()


# ── Helper: parse CLI category argument ────────────────────────────────────

def parse_categories(raw: Optional[str]) -> Optional[set[str]]:
    """Convert a comma‑separated category string into a set.

    ``"all"`` or ``None`` returns ``None`` (meaning all categories).
    """
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if cleaned in ("", "all"):
        return None
    cats = {c.strip() for c in cleaned.split(",") if c.strip()}
    return cats if cats else None


# ── `generate` command ─────────────────────────────────────────────────────

@app.command()
def generate(
    input_file: Path = typer.Option(
        ..., "--input", "-i",
        exists=True, file_okay=True, dir_okay=False, readable=True,
        help="Path to keyword file (one keyword per line).",
    ),
    output_file: Path = typer.Option(
        Path("dorks.txt"), "--output", "-o",
        help="Output file path (default: dorks.txt).",
    ),
    categories: Optional[str] = typer.Option(
        None, "--categories", "-c",
        help="Comma-separated category names or 'all' (default: all).",
    ),
    tld: Optional[str] = typer.Option(
        "com", "--tld", "-t",
        help="Comma-separated TLDs (default: com).",
    ),
    sample: Optional[int] = typer.Option(
        None, "--sample", "-s", min=1,
        help="Process only the first N keywords.",
    ),
    max_dorks: Optional[int] = typer.Option(
        None, "--max", "-m", min=1,
        help="Hard limit on total generated dorks.",
    ),
    mix: bool = typer.Option(
        False, "--mix",
        help="Randomly shuffle templates per keyword (rate-limit evasion).",
    ),
    batch_size: int = typer.Option(
        DEFAULT_BATCH_SIZE, "--batch-size",
        help="Lines per disk flush (default: 10 000).",
    ),
    template_path: Optional[Path] = typer.Option(
        None, "--templates",
        exists=True,
        help="Custom dork_templates.json path.",
    ),
) -> None:
    """Generate Google dork queries from keywords and curated templates."""
    show_banner()

    # Parse TLDs
    tlds = [t.strip().lower() for t in (tld or "com").split(",") if t.strip()]

    # Parse categories
    cat_set = parse_categories(categories)
    cat_label = ", ".join(sorted(cat_set)) if cat_set else "all"

    # Template summary
    all_tmpl = load_templates(template_path)
    resolved = resolve_categories(all_tmpl, cat_set)

    # Pre‑flight info
    info = Table(title="Generation Parameters", show_header=False, box=None)
    info.add_row("[bold]Keyword file[/bold]", str(input_file))
    info.add_row("[bold]Output file[/bold]", str(output_file))
    info.add_row("[bold]Categories[/bold]", cat_label)
    info.add_row("[bold]Templates[/bold]", str(len(resolved)))
    info.add_row("[bold]TLDs[/bold]", ", ".join(tlds))
    info.add_row("[bold]Mix mode[/bold]", "ON" if mix else "OFF")
    if sample:
        info.add_row("[bold]Sample[/bold]", str(sample))
    if max_dorks:
        info.add_row("[bold]Max dorks[/bold]", f"{max_dorks:,}")
    console.print(info)
    console.print()

    # ── Run generation ──────────────────────────────────────────────────
    t0 = time.perf_counter()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("[cyan]Generating dorks...", total=None)
        try:
            total = generate_run(
                keyword_path=input_file,
                output_path=output_file,
                categories=cat_set,
                tlds=tlds,
                sample=sample,
                max_limit=max_dorks,
                mix=mix,
                batch_size=batch_size,
                template_path=template_path,
            )
        except Exception as exc:
            console.print(f"\n[bold red]✗ Error:[/bold red] {exc}")
            raise typer.Exit(code=1)

    elapsed = time.perf_counter() - t0

    # ── Results ─────────────────────────────────────────────────────────
    rate = total / elapsed if elapsed > 0 else float("inf")
    size_mb = output_file.stat().st_size / (1024 * 1024) if output_file.exists() else 0

    results = Table(title="Generation Complete", show_header=False, box=None)
    results.add_row("[bold green]Total dorks[/bold green]", f"{total:,}")
    results.add_row("[bold]Elapsed[/bold]", f"{elapsed:.2f} s")
    results.add_row("[bold]Throughput[/bold]", f"{rate:,.0f} dorks/s")
    results.add_row("[bold]File size[/bold]", f"{size_mb:.2f} MB")
    results.add_row("[bold]Output[/bold]", str(output_file.resolve()))
    console.print()
    console.print(results)
    console.print("\n[green]✔ Done.[/green]")


# ── `validate` command ─────────────────────────────────────────────────────

@app.command()
def validate(
    dork_file: Path = typer.Argument(
        ..., exists=True, file_okay=True, dir_okay=False, readable=True,
        help="Generated dork file to validate.",
    ),
    preview_lines: int = typer.Option(
        10, "--preview", "-p", min=1, max=100,
        help="Number of random lines to preview (default: 10).",
    ),
) -> None:
    """Validate a generated dork file for quality and correctness."""
    show_banner()

    console.print(f"[bold]Validating:[/bold] {dork_file}\n")

    # Read all lines (validation is a small‑file operation)
    with open(dork_file, encoding="utf-8", errors="replace") as fh:
        lines = [line.rstrip("\n") for line in fh if line.strip()]

    total = len(lines)
    console.print(f"[bold]Total lines:[/bold] {total:,}\n")

    # ── 1. Operator presence check ──────────────────────────────────────
    missing_ops: list[int] = []
    for i, line in enumerate(lines, 1):
        if not DORK_OPERATOR_RE.search(line):
            missing_ops.append(i)

    # ── 2. Unresolved placeholder check ─────────────────────────────────
    unresolved: list[int] = []
    for i, line in enumerate(lines, 1):
        if UNRESOLVED_PLACEHOLDER_RE.search(line):
            unresolved.append(i)

    # ── 3. Stats ────────────────────────────────────────────────────────
    operator_counts: dict[str, int] = {}
    for line in lines:
        for m in DORK_OPERATOR_RE.finditer(line):
            op = m.group(1).lower()
            operator_counts[op] = operator_counts.get(op, 0) + 1

    # ── Report ──────────────────────────────────────────────────────────
    report = Table(title="Validation Report", show_header=False, box=None)
    report.add_row("[bold]Total lines[/bold]", f"{total:,}")

    ok_ops = total - len(missing_ops)
    if missing_ops:
        report.add_row(
            "[bold red]✗ Operator check[/bold red]",
            f"{ok_ops:,} OK / {len(missing_ops):,} missing (lines: {missing_ops[:5]}{'...' if len(missing_ops) > 5 else ''})",
        )
    else:
        report.add_row("[bold green]✔ Operator check[/bold green]", f"{ok_ops:,} OK — all lines have operators")

    if unresolved:
        report.add_row(
            "[bold red]✗ Unresolved placeholders[/bold red]",
            f"{len(unresolved):,} lines (lines: {unresolved[:5]}{'...' if len(unresolved) > 5 else ''})",
        )
    else:
        report.add_row("[bold green]✔ Placeholders[/bold green]", "All resolved — no {keyword} or {tld} remaining")

    console.print(report)

    # ── Operator frequency ──────────────────────────────────────────────
    if operator_counts:
        op_table = Table(title="Operator Frequency", show_header=True, box=None)
        op_table.add_column("Operator", style="cyan")
        op_table.add_column("Count", justify="right")
        op_table.add_column("%", justify="right")
        for op, count in sorted(operator_counts.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            op_table.add_row(op, f"{count:,}", f"{pct:.1f}%")
        console.print()
        console.print(op_table)

    # ── Random preview ──────────────────────────────────────────────────
    console.print()
    preview = random.sample(lines, min(preview_lines, total))
    prev_table = Table(title=f"Random Preview ({len(preview)} lines)", show_lines=True, box=None)
    prev_table.add_column("#", style="dim", justify="right")
    prev_table.add_column("Dork", style="white")
    for i, dork in enumerate(preview, 1):
        prev_table.add_row(str(i), dork[:120] + ("…" if len(dork) > 120 else ""))
    console.print(prev_table)

    # ── Final verdict ───────────────────────────────────────────────────
    console.print()
    if not missing_ops and not unresolved:
        console.print("[bold green]✔ VALIDATION PASSED[/bold green]")
    else:
        console.print("[bold yellow]⚠ VALIDATION COMPLETE — see issues above[/bold yellow]")


# ── `list-categories` command ──────────────────────────────────────────────

@app.command("list-categories")
def list_categories(
    template_path: Optional[Path] = typer.Option(
        None, "--templates",
        exists=True,
        help="Custom dork_templates.json path.",
    ),
) -> None:
    """List available dork categories with template counts."""
    all_tmpl = load_templates(template_path)
    table = Table(title="Available Categories", show_header=True, box=None)
    table.add_column("Category", style="cyan")
    table.add_column("Templates", justify="right")
    for cat in sorted(all_tmpl.keys()):
        table.add_row(cat, str(len(all_tmpl[cat])))
    console.print(table)


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
