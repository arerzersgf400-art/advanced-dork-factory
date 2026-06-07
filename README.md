# Advanced Dork Factory

**Professional CLI Google Dork Generator for Authorized OSINT Research**

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-red.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-50%20passed-brightgreen.svg)](test_generator.py)
[![Templates](https://img.shields.io/badge/templates-347-orange.svg)](dork_templates.json)

---

## ⚖️ Ethical Use Disclaimer

> **This tool is intended exclusively for:**
>
> - Authorized penetration testing with **written permission**
> - Bug bounty programs within **explicitly defined scope**
> - Defensive OSINT & threat intelligence gathering
> - Academic and educational security research
>
> **Unauthorized use against systems you do not own or have explicit permission to test is illegal.**
> The author assumes no liability for misuse, damages, or legal consequences arising from use of this software.
> If you are unsure whether your use is authorized, consult a qualified legal professional first.

---

## Overview

Advanced Dork Factory generates **multi-operator Google dork queries** from a curated collection of 347 templates across 10 OSINT categories. It is built for performance — capable of producing **500,000+ dorks in under 5 seconds** — using lazy evaluation, batched I/O, and minimal string operations.

### Key Features

- **10 OSINT Categories**: SQL injection, XSS, LFI, exposed documents, open redirects, subdomain discovery, cloud buckets, Jenkins dashboards, Git repository exposure, backup files
- **Performance-First Design**: Lazy keyword file reading (never loads full file into RAM), 10k-line batch disk flushes, template pre-classification (static vs TLD-expandable)
- **Mix Mode**: Randomly shuffles template ordering per keyword to evade Google rate-limiting heuristics
- **TLD Expansion**: Multi-TLD support (`--tld com,org,net`) for country-specific dorking
- **Built-in Validation**: Post-generation `validate` command that checks operator presence, unresolved placeholders, and operator frequency distribution
- **Pydantic Validation**: Template JSON is structurally validated on load — no silent failures
- **50-strong Test Suite**: Full pytest coverage including end-to-end integration tests

---

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/advanced-dork-factory.git
cd advanced-dork-factory

# Install dependencies
pip install -r requirements.txt
```

### Requirements

- Python 3.9+
- `typer[all]` — Modern CLI framework
- `rich` — Beautiful terminal output
- `pydantic` — Schema validation
- `tqdm` — Progress indicators
- `httpx` — HTTP client (template sourcing only)
- `pytest` — Test runner

---

## Quick Start

```bash
# Generate dorks for SQL injection with a single keyword file
python main.py generate -i keywords.txt -c sql-injection -o dorks.txt

# Validate the output
python main.py validate dorks.txt

# List all available categories
python main.py list-categories
```

---

## CLI Reference

### `generate` — Generate Dork Queries

```
Usage: python main.py generate [OPTIONS]

Options:
  -i, --input PATH       Keyword file (one keyword per line)  [required]
  -o, --output PATH      Output file path  [default: dorks.txt]
  -c, --categories TEXT  Comma-separated categories or 'all'  [default: all]
  -t, --tld TEXT         Comma-separated TLDs  [default: com]
  -s, --sample INTEGER   Process only first N keywords
  -m, --max INTEGER      Hard limit on total generated dorks
  --mix / --no-mix       Randomly shuffle templates per keyword
  --batch-size INTEGER   Lines per disk flush  [default: 10000]
  --templates PATH       Custom dork_templates.json path
```

#### Examples

```bash
# All categories, single TLD
python main.py generate -i keywords.txt

# Specific categories, multiple TLDs
python main.py generate -i keywords.txt -c sql-injection,xss,lfi -t com,org,net

# Mix mode for rate-limit evasion (shuffles templates per keyword)
python main.py generate -i keywords.txt -c all -t com,org --mix

# Sample first 100 keywords (useful for testing)
python main.py generate -i huge_wordlist.txt -s 100 -o test_dorks.txt

# Hard cap at 50,000 dorks max
python main.py generate -i keywords.txt -m 50000 -o limited.txt

# Full production run with all bells and whistles
python main.py generate -i keywords.txt -c all -t com,org,net,io,co,uk --mix -m 1000000 -o massive_dork_list.txt
```

### `validate` — Validate Generated Dork File

```
Usage: python main.py validate [OPTIONS] DORK_FILE

Arguments:
  DORK_FILE  Generated dork file to validate  [required]

Options:
  -p, --preview INTEGER  Random lines to preview  [default: 10]
```

#### Example Output

```
╔══════════════════════════════════════════════════════════════╗
║        Advanced Dork Factory  —  OSINT Dork Generator        ║
║  ⚖️  FOR AUTHORIZED SECURITY RESEARCH ONLY                    ║
╚══════════════════════════════════════════════════════════════╝

Validating: dorks.txt

Total lines: 34,700

✔ Operator check     34,700 OK — all lines have operators
✔ Placeholders        All resolved — no {keyword} or {tld} remaining

          Operator Frequency
┌────────────────┬──────────┬───────┐
│ Operator       │    Count │     % │
├────────────────┼──────────┼───────┤
│ site           │   34,700 │ 100.0%│
│ inurl          │   17,350 │  50.0%│
│ intext         │   10,410 │  30.0%│
│ intitle        │    6,940 │  20.0%│
│ filetype       │    3,470 │  10.0%│
└────────────────┴──────────┴───────┘

              Random Preview (10 lines)
┌──┬────────────────────────────────────────────────────────┐
│ 1│ site:com inurl:admin/index.php?id= intitle:"admin login"│
│ 2│ site:org filetype:sql "mysql dump" "admin"              │
│...│                                                        │
└──┴────────────────────────────────────────────────────────┘

✔ VALIDATION PASSED
```

### `list-categories` — Show Available Categories

```
Usage: python main.py list-categories

Available Categories
┌────────────────────────┬───────────┐
│ Category               │ Templates │
├────────────────────────┼───────────┤
│ backup-files           │        35 │
│ cloud-buckets          │        35 │
│ exposed-documents      │        70 │
│ git-repo-exposure      │        26 │
│ jenkins-dashboard      │        22 │
│ lfi                    │        25 │
│ open-redirect          │        20 │
│ sql-injection          │        64 │
│ subdomain-discovery    │        30 │
│ xss                    │        20 │
└────────────────────────┴───────────┘
```

---

## Architecture

```
advanced-dork-factory/
├── main.py                 # Typer + Rich CLI (generate, validate, list-categories)
├── generator.py            # Core engine: template loading, keyword iterator, dork generation, batched writing
├── schemas.py              # Pydantic models for dork_templates.json validation
├── dork_templates.json     # 347 curated templates across 10 categories
├── test_generator.py       # 50-test pytest suite (unit + integration)
├── requirements.txt        # Python dependencies
└── README.md               # You are here
```

### Data Flow

```
keywords.txt  ──(lazy read)──>  Keyword Iterator
                                    │
dork_templates.json ──>  Load & Classify  ──>  Static + TLDable Templates
                                    │
                              ┌─────▼─────┐
                              │  generate  │──(yield)──> Batched Writer ──> dorks.txt
                              └───────────┘
```

---

## Performance

| Scenario | Keywords | Templates | TLDs | Output | Time | Throughput |
|----------|----------|-----------|------|--------|------|------------|
| Small | 100 | 347 | 1 | ~34,700 | ~0.3s | ~115k dorks/s |
| Medium | 1,000 | 347 | 3 | ~1,041,000 | ~2.0s | ~520k dorks/s |
| Large | 10,000 | 347 | 5 | ~17,350,000 | ~30s | ~578k dorks/s |

*Benchmarked on standard Ryzen 7 / NVMe SSD. Results depend on I/O throughput and CPU.*

### Why It's Fast

1. **Lazy Keyword Reading**: The file is never loaded into RAM — keywords are yielded one at a time via a generator
2. **Template Pre-Classification**: Templates without `{tld}` skip the TLD expansion loop entirely, saving ~50% of `str.replace()` calls
3. **Batched I/O**: 10,000 lines buffered before a single `writelines()` syscall, minimizing kernel round-trips
4. **Local Variable Binding**: Frequently called methods (`_append`) bound to local names to avoid attribute lookups in hot loops

---

## Mix Mode Explained

When `--mix` is active, the template list is **randomly shuffled** for each keyword before expansion. Without `--mix`, all 100 keywords receive templates in identical order:

```
Without --mix:
  keyword_0: template_0, template_1, template_2, ...
  keyword_1: template_0, template_1, template_2, ...  (same order)
  keyword_2: template_0, template_1, template_2, ...  (same order)

With --mix:
  keyword_0: template_7, template_2, template_5, ...
  keyword_1: template_1, template_9, template_0, ...  (different)
  keyword_2: template_4, template_3, template_8, ...  (different)
```

This variation makes automated dorking traffic patterns less predictable to Google's heuristic rate-limiters, reducing the likelihood of CAPTCHA triggers during authorized scanning.

---

## Template Categories

| Category | Count | Typical Operators Used |
|----------|-------|------------------------|
| `sql-injection` | 64 | `inurl:`, `intext:"error in your SQL syntax"`, `site:` |
| `xss` | 20 | `inurl:`, `intext:<script>`, `intitle:XSS` |
| `lfi` | 25 | `inurl:`, `inurl:../`, `filetype:php` |
| `exposed-documents` | 70 | `intitle:"index of"`, `filetype:pdf`, `intext:confidential` |
| `open-redirect` | 20 | `inurl:redirect`, `inurl:url=`, `inurl:next=` |
| `subdomain-discovery` | 30 | `site:`, `-www`, `inurl:` |
| `cloud-buckets` | 35 | `site:s3.amazonaws.com`, `inurl:bucket`, `site:storage.googleapis.com` |
| `jenkins-dashboard` | 22 | `intitle:"Dashboard [Jenkins]"`, `inurl:8080`, `site:` |
| `git-repo-exposure` | 26 | `inurl:.git/config`, `intitle:"index of" .git`, `filetype:git` |
| `backup-files` | 35 | `filetype:sql`, `intitle:"index of" backup`, `inurl:backup` |

---

## Testing

```bash
# Run the full test suite
python -m pytest test_generator.py -v

# Expected: 50 passed
```

Test coverage includes:
- Template loading & JSON parsing (missing file, corrupt data)
- Pydantic schema validation (missing keyword, unknown placeholders, empty data)
- Keyword file reading (dedup, cleanup, sample limits, lazy iteration)
- Dork generation logic (keyword/TLD replacement, max hard-cutoff)
- Batch writing integrity (small files, multi-batch, empty iterator)
- Mix Mode randomness verification
- Validation regex patterns (operator detection, unresolved placeholder detection)
- End-to-end integration (single keyword, multi-TLD, sample mode, max limit, mix mode, all categories)

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

## Credits

Template data curated from open-source OSINT collections:
- [cipher387/Dorks-collections-list](https://github.com/cipher387/Dorks-collections-list)
- [IvanGlinkin/AutoDork](https://github.com/IvanGlinkin/AutoDork)
- [BullsEye0/google_dork_list](https://github.com/BullsEye0/google_dork_list)
- [D4Vinci/Dr0p1t-Framework](https://github.com/D4Vinci/Dr0p1t-Framework)
- [Te-k/handbook](https://github.com/Te-k/handbook)

---

*Built with ❤️ for the OSINT community. Use responsibly.*
