#!/usr/bin/env python3
"""Browse existing research documents/tables locally without writing artifacts.

Standard library only. No evaluation modules or model clients are imported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Path("docs/research/result_catalog.json")
ASSET = Path("assets/research_browser.html")


def safe_path(root: Path, relative: str) -> Path:
    """Resolve catalog paths inside this checkout, including symlink checks."""
    path = (root / relative).resolve()
    path.relative_to(root.resolve())
    return path


def read_catalog(root: Path) -> dict:
    data = json.loads(safe_path(root, str(CATALOG)).read_text(encoding="utf-8"))
    ids = set()
    for item in data["items"]:
        if item["id"] in ids:
            raise ValueError(f"Duplicate catalog id: {item['id']}")
        ids.add(item["id"])
        if "table" in item:
            item["path"] = (
                f"{data['comparison_root']}/tables/table_model_comparison_{item['table']}.md"
            )
        safe_path(root, item["path"])
        if "spec" in item:
            safe_path(root, item["spec"])
    for relative in data.get("resources", []):
        safe_path(root, relative)
    return data


def parse_tables(text: str) -> list[dict]:
    """Expose stored Markdown cells as text; never calculate research metrics."""
    def cells(line: str) -> list[str]:
        parts, cell, quoted = [], [], False
        previous = ""
        for char in line.strip().strip("|"):
            if char == "`" and previous != "\\":
                quoted = not quoted
            if char == "|" and previous != "\\" and not quoted:
                parts.append("".join(cell).strip().replace(r"\|", "|"))
                cell = []
            else:
                cell.append(char)
            previous = char
        parts.append("".join(cell).strip().replace(r"\|", "|"))
        return parts

    lines = text.splitlines()
    tables = []
    i = 0
    while i + 1 < len(lines):
        if not lines[i].lstrip().startswith("|"):
            i += 1
            continue
        headers = cells(lines[i])
        separator = cells(lines[i + 1])
        if len(separator) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", c) for c in separator):
            i += 1
            continue
        rows = []
        i += 2
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            row = cells(lines[i])
            if len(row) != len(headers):
                raise ValueError("Markdown table has an inconsistent number of cells")
            rows.append(row)
            i += 1
        tables.append({"headers": headers, "rows": rows})
    return tables


def allowed_files(root: Path, data: dict) -> set[Path]:
    """Only human-facing Markdown and exact registered tables/CSVs are served."""
    allowed = {p.resolve() for p in (root / "docs").rglob("*.md") if p.resolve().is_relative_to(root.resolve())}
    allowed.add((root / "README.md").resolve())
    for item in data["items"]:
        path = safe_path(root, item["path"])
        allowed.add(path)
        if "table" in item:
            allowed.add(safe_path(root, str(Path(item["path"]).with_suffix(".csv"))))
    for relative in data.get("resources", []):
        allowed.add(safe_path(root, relative))
    return allowed


def source_payload(root: Path, relative: str, allowed: set[Path]) -> dict:
    path = safe_path(root, relative)
    if path not in allowed or path.suffix != ".md":
        raise PermissionError("Source is not registered for this viewer")
    content = path.read_bytes()
    text = content.decode("utf-8")
    return {"path": relative, "text": text, "tables": parse_tables(text),
            "sha256": hashlib.sha256(content).hexdigest()}


def check_catalog(root: Path, data: dict) -> list[str]:
    issues = []
    allowed = allowed_files(root, data)
    for relative in data.get("resources", []):
        if not safe_path(root, relative).is_file():
            issues.append(f"resource: missing {relative}")
    for item in data["items"]:
        for key in ("path", "spec"):
            if key in item and not safe_path(root, item[key]).is_file():
                issues.append(f"{item['id']}: missing {item[key]}")
        if not safe_path(root, item["path"]).is_file():
            continue
        try:
            tables = source_payload(root, item["path"], allowed)["tables"]
            if "table" in item:
                if not tables:
                    issues.append(f"{item['id']}: no Markdown table")
                else:
                    missing = set(item.get("columns", [])) - set(tables[0]["headers"])
                    if missing:
                        issues.append(f"{item['id']}: missing columns {sorted(missing)}")
                if not safe_path(root, str(Path(item["path"]).with_suffix(".csv"))).is_file():
                    issues.append(f"{item['id']}: missing CSV download source")
        except (ValueError, UnicodeError) as error:
            issues.append(f"{item['id']}: {error}")
    return issues


def make_handler(root: Path):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, content: bytes, content_type: str, status: int = 200,
                       filename: str = "") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, value: dict, status: int = 200) -> None:
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"),
                            "application/json; charset=utf-8", status)

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            try:
                if url.path == "/":
                    self.send_bytes(safe_path(root, str(ASSET)).read_bytes(), "text/html; charset=utf-8")
                    return
                data = read_catalog(root)
                allowed = allowed_files(root, data)
                if url.path == "/api/catalog":
                    for item in data["items"]:
                        item["available"] = safe_path(root, item["path"]).is_file()
                    data["sources"] = sorted(str(p.relative_to(root.resolve())) for p in allowed)
                    self.send_json(data)
                elif url.path == "/api/source":
                    relative = parse_qs(url.query).get("path", [""])[0]
                    self.send_json(source_payload(root, relative, allowed))
                elif url.path.startswith("/download/"):
                    relative = unquote(url.path[len("/download/"):])
                    path = safe_path(root, relative)
                    if path not in allowed or path.suffix not in (".md", ".csv", ".json"):
                        raise PermissionError("Download is not registered")
                    content_type = {".csv": "text/csv", ".md": "text/markdown", ".json": "application/json"}[path.suffix] + "; charset=utf-8"
                    self.send_bytes(path.read_bytes(), content_type, filename=path.name)
                else:
                    self.send_json({"error": "Not found"}, 404)
            except FileNotFoundError:
                self.send_json({"error": "参照ファイルが未配置です。結果の保存先を確認してください。"}, 404)
            except (ValueError, PermissionError):
                self.send_json({"error": "この閲覧ビューの対象外のファイルです。"}, 403)
            except (OSError, UnicodeError) as error:
                self.send_json({"error": f"読み取りに失敗しました: {type(error).__name__}"}, 500)

        def log_message(self, format: str, *args) -> None:
            pass

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="既存の研究文書・評価表を読む専用ビュー（API呼び出し・書き込みなし）")
    parser.add_argument("--port", type=int, default=8522, help="localhostのポート（既定8522）")
    parser.add_argument("--open", action="store_true", help="起動後にブラウザを開く")
    parser.add_argument("--check", action="store_true", help="参照ファイル・表の列名を検査して終了")
    args = parser.parse_args()
    data = read_catalog(ROOT)
    if args.check:
        issues = check_catalog(ROOT, data)
        for issue in issues:
            print(issue)
        print(f"Catalog: {len(data['items'])} entries, {len(issues)} issue(s)")
        return int(bool(issues))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ROOT))
    except OSError as error:
        parser.exit(1, f"起動できません: {error}. --port 8523 など別のポートを指定してください。\n")
    with server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"研究結果ビュー: {url}\n終了: Ctrl+C", flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
