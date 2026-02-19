from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_TEMPLATE = ROOT / "templates" / "upload.html"

WHITELIST = {"PDF", "JPG", "PNG", "JPEG", "WEBP"}
EN_PATTERN = re.compile(r"[A-Za-z]{2,}")
CN_PATTERN = re.compile(r"[\u4e00-\u9fff]")

UI_ATTRS = {
    "placeholder",
    "title",
    "aria-label",
    "aria-placeholder",
    "alt",
    "data-empty",
    "data-placeholder",
    "data-title",
    "data-label",
}

ATTR_RE = re.compile(
    r"(?P<attr>"
    + "|".join(re.escape(attr) for attr in sorted(UI_ATTRS))
    + r")\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE,
)
JINJA_RE = re.compile(r"\{[%#].*?[%#]\}|\{\{.*?\}\}")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
TAG_RE = re.compile(r"<[^>]+>")
ENTITY_RE = re.compile(r"&[a-zA-Z]+;")


def strip_template_expressions(text: str) -> str:
    return re.sub(r"\$\{[^}]*\}", "", text)


def find_unwhitelisted(text: str) -> str | None:
    cleaned = strip_template_expressions(text)
    cleaned = ENTITY_RE.sub("", cleaned)
    for match in EN_PATTERN.finditer(cleaned):
        token = match.group(0)
        if token.upper() in WHITELIST:
            continue
        return token
    return None


def record_issue(path: Path, lineno: int, token: str, issues: list[str]) -> None:
    rel = path.relative_to(ROOT)
    issues.append(f"{rel}:{lineno}: 发现英文片段 {token}")


def scan_text(text: str, path: Path, lineno: int, issues: list[str]) -> None:
    token = find_unwhitelisted(text)
    if token:
        record_issue(path, lineno, token, issues)


def scan_html_fragment(fragment: str, path: Path, lineno: int, issues: list[str]) -> None:
    cleaned = strip_template_expressions(fragment)
    for match in ATTR_RE.finditer(cleaned):
        scan_text(match.group("value"), path, lineno, issues)
    text = TAG_RE.sub(" ", cleaned)
    scan_text(text, path, lineno, issues)


def extract_string_literals(line: str) -> list[str]:
    literals: list[str] = []
    i = 0
    length = len(line)
    while i < length:
        ch = line[i]
        if ch not in {"'", '"', "`"}:
            i += 1
            continue
        quote = ch
        i += 1
        buf: list[str] = []
        while i < length:
            c = line[i]
            if c == "\\":
                if i + 1 < length:
                    buf.append(line[i + 1])
                    i += 2
                    continue
                i += 1
                continue
            if quote == "`" and c == "$" and i + 1 < length and line[i + 1] == "{":
                depth = 1
                i += 2
                while i < length and depth > 0:
                    if line[i] == "{":
                        depth += 1
                    elif line[i] == "}":
                        depth -= 1
                    i += 1
                continue
            if c == quote:
                i += 1
                break
            buf.append(c)
            i += 1
        literals.append("".join(buf))
    return literals


def scan_js_line(line: str, path: Path, lineno: int, issues: list[str]) -> None:
    literals = extract_string_literals(line)
    if not literals:
        return

    ui_context = bool(
        re.search(
            r"(alert|confirm|prompt)\s*\(|\.textContent\s*=|\.innerText\s*=|\.innerHTML\s*=|"
            r"insertAdjacentHTML\s*\(|setAttribute\s*\(",
            line,
        )
    )
    attr_match = re.search(r"setAttribute\(\s*['\"]([^'\"]+)['\"]", line)
    attr_name = attr_match.group(1).strip().lower() if attr_match else ""

    for match in re.finditer(r"\b(label|text|placeholder)\s*:\s*['\"]([^'\"]*)['\"]", line):
        scan_text(match.group(2), path, lineno, issues)

    for literal in literals:
        if not literal:
            continue
        has_cn = bool(CN_PATTERN.search(literal))
        if not ui_context and not has_cn:
            continue
        if "<" in literal and ">" in literal:
            scan_html_fragment(literal, path, lineno, issues)
            continue
        if "innerHTML" in line or "insertAdjacentHTML" in line:
            scan_html_fragment(literal, path, lineno, issues)
        elif "setAttribute" in line:
            if attr_name and attr_name not in UI_ATTRS:
                continue
            scan_text(literal, path, lineno, issues)
        else:
            scan_text(literal, path, lineno, issues)


def scan_html_file(path: Path, issues: list[str]) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_script = False
    in_style = False
    in_tag = False
    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line
        if "<script" in line:
            in_script = True
        if "<style" in line:
            in_style = True

        if in_script:
            scan_js_line(line, path, lineno, issues)
            if "</script>" in line:
                in_script = False
            continue
        if in_style:
            if "</style>" in line:
                in_style = False
            continue

        cleaned = JINJA_RE.sub("", line)
        cleaned = HTML_COMMENT_RE.sub("", cleaned)
        for match in ATTR_RE.finditer(cleaned):
            scan_text(match.group("value"), path, lineno, issues)
        if in_tag:
            if ">" in line:
                in_tag = False
            continue
        if "<" in line and ">" not in line:
            in_tag = True
            continue
        text = TAG_RE.sub(" ", cleaned)
        scan_text(text, path, lineno, issues)


def scan_js_file(path: Path, issues: list[str]) -> None:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for lineno, line in enumerate(lines, start=1):
        scan_js_line(line, path, lineno, issues)


def collect_static_refs(upload_html: str) -> set[Path]:
    refs: set[Path] = set()
    for match in re.finditer(r"url_for\(\s*['\"]static['\"],\s*filename=['\"]([^'\"]+)['\"]", upload_html):
        refs.add(Path(match.group(1)))
    for match in re.finditer(r"['\"]/static/([^'\"]+)['\"]", upload_html):
        refs.add(Path(match.group(1)))
    paths: set[Path] = set()
    for ref in refs:
        if "vendor" in ref.parts:
            continue
        target = ROOT / "static" / ref
        if target.suffix.lower() != ".js":
            continue
        if target.exists():
            paths.add(target)
    return paths


def main() -> int:
    if not UPLOAD_TEMPLATE.exists():
        print("未找到 templates/upload.html", file=sys.stderr)
        return 2

    issues: list[str] = []
    scan_html_file(UPLOAD_TEMPLATE, issues)

    upload_text = UPLOAD_TEMPLATE.read_text(encoding="utf-8", errors="replace")
    for js_path in sorted(collect_static_refs(upload_text)):
        scan_js_file(js_path, issues)

    if issues:
        for item in issues:
            print(item)
        return 1
    print("检查通过：未发现未白名单英文片段。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
