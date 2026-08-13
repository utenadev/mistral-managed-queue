#!/usr/bin/env python3
"""Translate README.md (EN) → README.ja.md / README.fr.md via mmq.

Preserves fenced code blocks (line-based FSM) and inline code. Uses the
shared Mistral free-tier queue (``execute_mistral_queue_async``).

Usage (from repo root)::

    export MISTRAL_API_KEY=...
    python scripts/translate_readme.py
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

SRC = ROOT / "README.md"
TARGETS = {
    "ja": ROOT / "README.ja.md",
    "fr": ROOT / "README.fr.md",
}
LANG_NAMES = {"ja": "Japanese", "fr": "French"}

# Fixed language switcher (never sent to the model)
SWITCHER = "[English](README.md) | [日本語](README.ja.md) | [Français](README.fr.md)"

INLINE_CODE = re.compile(r"`[^`\n]+`")
BLOCK_TOKEN = re.compile(r"<!-- MMQ_BLOCK_(\d+) -->")
PLACEHOLDER = "<!-- MMQ_BLOCK_{i} -->"

SYSTEM = """You translate technical README markdown for a software project.
Rules:
- Translate prose only (headings, paragraphs, list items, table cells).
- Do NOT translate: fenced code, inline code, URLs, model IDs, CLI flags,
  JSON keys, env var names, package names, badge markup, HTML comments.
- Keep every placeholder exactly as-is, including spelling and digits:
  e.g. <!-- MMQ_BLOCK_0 -->  (copy unchanged; do not invent or drop any).
- Keep markdown structure: same heading levels, list markers, table column counts.
- Do not add a preamble or explanation. Output markdown only.
- Leave the product name "mcp-mistral-queue" and command "mmq" unchanged.
"""


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
        # Unclosed fence: keep as opaque block
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
    # Also accept if model stripped spaces in comment
    for i, block in enumerate(parts):
        token = PLACEHOLDER.format(i=i)
        if token in text:
            text = text.replace(token, block)
        else:
            # try without surrounding whitespace variants
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


def assemble_output(h1_and_rest: str, translated_body: str) -> str:
    """Rebuild file: H1, fixed switcher, rest of translation without duplicate H1/switcher."""
    # translated_body may still contain H1 + content; strip leading H1 and switcher if present
    lines = translated_body.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    if lines and lines[0].startswith("# "):
        out.append(lines[0])
        i = 1
        if i < len(lines) and lines[i].strip() == "":
            out.append(lines[i])
            i += 1
    else:
        # fallback: use source H1 from h1_and_rest
        src_lines = h1_and_rest.splitlines(keepends=True)
        if src_lines:
            out.append(src_lines[0])
            if not out[0].endswith("\n"):
                out[0] += "\n"
            out.append("\n")

    out.append(SWITCHER + "\n")
    out.append("\n")

    # skip blank lines and a switcher line if model re-emitted them
    while i < len(lines):
        if lines[i].strip() == "":
            i += 1
            continue
        if "README.ja.md" in lines[i] and "README.fr.md" in lines[i]:
            i += 1
            continue
        break
    out.extend(lines[i:])
    text = "".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


def validate_markdown(text: str, _n_blocks: int = 0) -> None:
    if SWITCHER not in text:
        raise RuntimeError("Language switcher line missing or altered")
    fence_marks = text.count("```")
    if fence_marks % 2 != 0:
        raise RuntimeError(f"Unbalanced code fences (``` count={fence_marks})")
    # Source README may document the *wrong* form as a counter-example; do not
    # reject that. Require the correct form to appear at least once.
    if "uvx --from mcp-mistral-queue mmq" not in text:
        raise RuntimeError(
            "Expected correct entry-point form "
            "`uvx --from mcp-mistral-queue mmq` missing from output"
        )


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


async def run_one(lang: str, src: str, dry_run: bool) -> None:
    path = TARGETS[lang]
    print(f"→ {path.name} ({LANG_NAMES[lang]})")
    # Drop switcher from source body before protect/translate
    lines = src.splitlines(keepends=True)
    body_lines: list[str] = []
    for line in lines:
        if "README.ja.md" in line and "README.fr.md" in line:
            continue
        body_lines.append(line)
    body = "".join(body_lines)

    protected, parts = protect(body)
    raw = await translate_via_mmq(protected, lang)
    # Strip markdown fences if model wrapped the whole answer
    raw = raw.strip()
    if raw.startswith("```") and raw.endswith("```"):
        raw_lines = raw.splitlines()
        if len(raw_lines) >= 2:
            raw = "\n".join(raw_lines[1:-1]) + ("\n" if raw.endswith("\n") else "")

    restored = restore(raw, parts)
    final = assemble_output(body, restored)
    validate_markdown(final, len(parts))

    if dry_run:
        print(final[:2000])
        if len(final) > 2000:
            print(f"… ({len(final)} bytes total, dry-run)")
        return

    write_atomic(path, final)
    print(f"  wrote {path} ({len(final)} bytes, {len(parts)} protected segments)")


async def amain(langs: list[str], dry_run: bool) -> int:
    if not os.environ.get("MISTRAL_API_KEY"):
        print("MISTRAL_API_KEY is not set", file=sys.stderr)
        return 1
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    src = SRC.read_text(encoding="utf-8")
    for lang in langs:
        if lang not in TARGETS:
            print(f"unknown lang: {lang}", file=sys.stderr)
            return 1
        await run_one(lang, src, dry_run=dry_run)
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
        "--lang",
        action="append",
        choices=sorted(TARGETS),
        help="Language to generate (repeatable). Default: ja and fr.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Translate and print a preview; do not write files",
    )
    args = p.parse_args()
    langs = args.lang or list(TARGETS.keys())
    return asyncio.run(amain(langs, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
