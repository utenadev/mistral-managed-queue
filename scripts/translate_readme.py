#!/usr/bin/env python3
"""Translate markdown documentation via mmq queue.

Translates source files into locale variants (ja, fr) while preserving
fenced code blocks and inline code.

Usage (from repo root)::

    export MISTRAL_API_KEY=...
    # Default: main README
    python scripts/translate_readme.py

    # Specific docs
    python scripts/translate_readme.py --include docs/README_MCP
    python scripts/translate_readme.py --include docs/README_extras_Catalog

    # Multiple docs
    python scripts/translate_readme.py --include README --include docs/README_MCP

    # Custom source / output dir
    python scripts/translate_readme.py --src docs/README_MCP.md --output-dir docs/

    python scripts/translate_readme.py --lang ja
    python scripts/translate_readme.py --dry-run

Env:
    MISTRAL_API_KEY   required
    TRANSLATE_MODEL   default: mistral-small-latest
    MMQ_*             optional queue tuning (same as mmq)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCALE_DIR = ROOT
LANG_NAMES = {"ja": "Japanese", "fr": "French"}
LANGS = sorted(LANG_NAMES)

# Default source files: name -> (src_path, output_dir, has_switcher)
DEFAULT_INCLUDES = {
    "README": ("README.md", ROOT, True),
    "docs/README_MCP": ("docs/README_MCP.md", ROOT / "docs", False),
    "docs/README_extras_Catalog": ("docs/README_extras_Catalog.md", ROOT / "docs", False),
}

INLINE_CODE = re.compile(r'`[^`\n]+`')
BLOCK_TOKEN = re.compile(r"<!-- MMQ_BLOCK_(d+) -->")
PLACEHOLDER = "<!-- MMQ_BLOCK_{i} -->"

SYSTEM = ("""You translate technical README markdown for a software project.
Rules:
- Translate prose only (headings, paragraphs, list items, table cells).
- Do NOT translate: fenced code, inline code, URLs, model IDs, CLI flags,
  JSON keys, env var names, package names, badge markup, HTML comments.
- Keep every placeholder exactly as-is, including spelling and digits:
  e.g. <!-- MMQ_BLOCK_0 -->  (copy unchanged; do not invent or drop any).
- Keep markdown structure: same heading levels, list markers, table column counts.
- Do not add a preamble or explanation. Output markdown only.
- Leave the product name "mistral-managed-queue" and command "mmq" unchanged.
""")


def _src_path(src_arg: str, output_dir: Path) -> Path:
    """Resolve source path from argument."""
    p = Path(src_arg)
    if p.is_absolute():
        return p
    return (output_dir / p).resolve() if output_dir else (ROOT / p).resolve()


def _locale_path(src_path: Path, lang: str, output_dir: Path) -> Path:
    """Build locale output path: e.g. README.md -> README.ja.md."""
    stem = src_path.stem           # "README" or "README_MCP"
    suffix = src_path.suffix       # ".md"
    name = f"{stem}.{lang}{suffix}"
    if output_dir:
        return (output_dir / name).resolve()
    return (src_path.parent / name).resolve()


def _build_switcher(src_path: Path) -> str | None:
    """Build language switcher line for the main README, or None for other docs."""
    name = src_path.stem  # "README"
    if name != "README":
        return None
    return "[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)"


def protect_fences(text: str) -> tuple[str, list[str]]:
    """Replace fenced code blocks with placeholders (line FSM)."""
    parts: list[str] = []
    out: list[str] = []
    in_fence = False
    buf: list[str] = []

    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                buf = [line]
            else:
                buf.append(line)
                parts.append("".join(buf))
                out.append(f"{PLACEHOLDER.format(i=len(parts) - 1)}\n")
                in_fence = False
                buf = []
            continue
        if in_fence:
            buf.append(line)
        else:
            out.append(line)

    if in_fence and buf:
        parts.append("".join(buf))
        out.append(f"{PLACEHOLDER.format(i=len(parts) - 1)}\n")

    return "".join(out), parts


def protect_inline(text: str, start_index: int = 0) -> tuple[str, list[str]]:
    """Replace inline `code` outside fences with placeholders."""
    parts: list[str] = []

    def repl(m: re.Match[str]) -> str:
        parts.append(m.group(0))
        return PLACEHOLDER.format(i=start_index + len(parts) - 1)

    return INLINE_CODE.sub(repl, text), parts


def protect(text: str) -> tuple[str, list[str]]:
    mid, fence_parts = protect_fences(text)
    mid2, inline_parts = protect_inline(mid, start_index=len(fence_parts))
    return mid2, fence_parts + inline_parts


def restore(text: str, parts: list[str]) -> str:
    missing = [i for i in range(len(parts)) if PLACEHOLDER.format(i=i) not in text]
    for i, block in enumerate(parts):
        token = PLACEHOLDER.format(i=i)
        if token in text:
            text = text.replace(token, block)
        else:
            alt = f"<!--MMQ_BLOCK_{i}-->"
            if alt in text:
                text = text.replace(alt, block)
            else:
                raise RuntimeError(
                    f"Placeholder missing after translation: {token} "
                    f"(and {len(missing)} total missing). Aborting write."
                )
    leftover = BLOCK_TOKEN.findall(text)
    if leftover:
        raise RuntimeError(f"Unrestored placeholders remain: {leftover}")
    return text


def assemble_output(
    src_text: str, translated_body: str, switcher: str | None
) -> str:
    """Rebuild file: H1, optional language switcher, rest of translation."""
    lines = translated_body.splitlines(keepends=True)
    out: list[str] = []
    i = 0

    # H1
    if lines and lines[0].startswith("# "):
        out.append(lines[0])
        i = 1
        if i < len(lines) and lines[i].strip() == "":
            out.append(lines[i])
            i += 1
    else:
        src_lines = src_text.splitlines(keepends=True)
        if src_lines:
            out.append(src_lines[0])
            if not out[0].endswith("\n"):
                out[0] += "\n"
            out.append("\n")

    # Language switcher (only for main README)
    if switcher:
        out.append(switcher + "\n")
        out.append("\n")

    # Skip blank lines and any duplicate switcher the model re-emitted
    while i < len(lines):
        if lines[i].strip() == "":
            i += 1
            continue
        if switcher and "README.ja.md" in lines[i] and "README.fr.md" in lines[i]:
            i += 1
            continue
        break
    out.extend(lines[i:])
    text = "".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


def validate_markdown(text: str, switcher: str | None) -> None:
    if switcher and switcher not in text:
        raise RuntimeError("Language switcher line missing or altered")
    fence_marks = text.count("```")
    if fence_marks % 2 != 0:
        raise RuntimeError(f"Unbalanced code fences (``` count={fence_marks})")


async def translate_via_mmq(protected: str, lang: str) -> str:
    from mmq.core import MistralRequest, execute_mistral_queue_async

    model = os.environ.get("TRANSLATE_MODEL", "mistral-small-latest")
    user = (
        f"Translate the following README into {LANG_NAMES[lang]}.\n"
        "Copy every HTML comment placeholder <!-- MMQ_BLOCK_N --> unchanged.\n\n"
        f"{protected}"
    )
    return await execute_mistral_queue_async(
        MistralRequest(
            prompt=user,
            system_prompt=SYSTEM,
            model=model,
            priority=2,
        )
    )


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def run_one(
    src_path: Path, lang: str, dry_run: bool, output_dir: Path | None
) -> None:
    dst_path = _locale_path(src_path, lang, output_dir or src_path.parent)
    switcher = _build_switcher(src_path)
    print(f"→ {src_path.name} -> {dst_path.name} ({LANG_NAMES[lang]})")

    src = src_path.read_text(encoding="utf-8")

    # Drop language switcher from source (only for README)
    if switcher:
        lines = src.splitlines(keepends=True)
        body_lines: list[str] = []
        for line in lines:
            if "README.ja.md" in line and "README.fr.md" in line:
                continue
            body_lines.append(line)
        src = "".join(body_lines)

    protected, parts = protect(src)
    raw = await translate_via_mmq(protected, lang)
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw_lines = raw.splitlines()
        if len(raw_lines) >= 2:
            raw = "\n".join(raw_lines[1:-1]) + ("\n" if raw.endswith("\n") else "")

    restored = restore(raw, parts)
    final = assemble_output(src, restored, switcher)
    validate_markdown(final, switcher)

    if dry_run:
        print(final[:2000])
        if len(final) > 2000:
            print(f"… ({len(final)} bytes total, dry-run)")
        return

    write_atomic(dst_path, final)
    print(f"  wrote {dst_path} ({len(final)} bytes, {len(parts)} protected segments)")


async def amain(
    includes: list[str], langs: list[str], dry_run: bool
) -> int:
    if not os.environ.get("MISTRAL_API_KEY"):
        print("MISTRAL_API_KEY is not set", file=sys.stderr)
        return 1

    for include_name in includes:
        if include_name not in DEFAULT_INCLUDES:
            print(f"unknown include: {include_name}", file=sys.stderr)
            print(f"available: {', '.join(sorted(DEFAULT_INCLUDES))}", file=sys.stderr)
            return 1

        src_rel, output_dir, _ = DEFAULT_INCLUDES[include_name]
        src_path = ROOT / src_rel
        if not src_path.exists():
            print(f"missing {src_path}", file=sys.stderr)
            return 1

        for lang in langs:
            if lang not in LANG_NAMES:
                print(f"unknown lang: {lang}", file=sys.stderr)
                return 1
            await run_one(src_path, lang, dry_run, output_dir)

    return 0


def main() -> int:
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--include",
        action="append",
        choices=sorted(DEFAULT_INCLUDES),
        help=(
            "Document to translate (repeatable). "
            f"Default: all ({', '.join(sorted(DEFAULT_INCLUDES))})."
        ),
    )
    p.add_argument(
        "--lang",
        action="append",
        choices=LANGS,
        help="Language to generate (repeatable). Default: all.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Translate and print a preview; do not write files",
    )
    args = p.parse_args()
    includes = args.include or sorted(DEFAULT_INCLUDES)
    langs = args.lang or LANGS
    return asyncio.run(amain(includes, langs, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
