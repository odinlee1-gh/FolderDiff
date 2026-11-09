#!/usr/bin/env python3
"""
比對兩個目錄，列出兩邊不一致的項目。

用法：
    python filediff.py                           # 以 UI 選擇目錄 A、B
    python filediff.py <目錄A> <目錄B>          # 直接指定兩個目錄
    python filediff.py <目錄A> <目錄B> --hash   # 依內容雜湊判斷（較準確、較慢）
    python filediff.py <目錄A> <目錄B> --csv diff.csv  # 另存 CSV 報表
    python filediff.py <目錄A> <目錄B> --ignore .git __pycache__ .DS_Store Thumbs.db
    python filediff.py <目錄A> <目錄B> --outdir reports   # HTML 存到指定資料夾
    python filediff.py <目錄A> <目錄B> --no-html          # 不產生 HTML

每次執行預設會自動產生 HTML 報表，檔名為 dir_diff_YYYYMMDD_HHMMSS.html
"""
import argparse
import csv
import hashlib
import os
import sys
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog


def choose_directory(title: str, initial_dir: str | None = None) -> Path | None:
    """開啟一個目錄選擇 UI，回傳選擇的目錄路徑。"""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title=title, initialdir=initial_dir)
    root.destroy()
    return Path(selected).resolve() if selected else None


def scan(root: Path, ignore: set[str]) -> dict[str, os.stat_result]:
    """回傳 {相對路徑: stat}，只收檔案，路徑統一用 / 分隔。"""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for name in filenames:
            if name in ignore:
                continue
            if name.startswith("~"):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            try:
                files[rel] = full.stat()
            except OSError as e:
                print(f"[警告] 無法讀取 {full}: {e}", file=sys.stderr)
    return files


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def compare(a: Path, b: Path, use_hash: bool, ignore: set[str], tolerance: float = 2.0):
    fa, fb = scan(a, ignore), scan(b, ignore)
    only_a = sorted(fa.keys() - fb.keys())
    only_b = sorted(fb.keys() - fa.keys())
    diff = []

    for rel in sorted(fa.keys() & fb.keys()):
        sa, sb = fa[rel], fb[rel]
        if sa.st_size != sb.st_size:
            reason = "大小不同"
        elif use_hash:
            if file_hash(a / rel) == file_hash(b / rel):
                continue
            reason = "內容不同"
        elif abs(sa.st_mtime - sb.st_mtime) > tolerance:  # 容許 FAT/網路磁碟的時間誤差
            reason = "修改時間不同"
        else:
            continue
        newer = "A" if sa.st_mtime > sb.st_mtime else "B"
        diff.append((rel, reason, sa, sb, newer))

    return fa, fb, only_a, only_b, diff


def sort_rel_paths(paths):
    """依目錄層級排序：先根目錄項目，再逐層子目錄."""
    return sorted(paths, key=lambda p: (p.count("/"), p))


def write_html(path: Path, a: Path, b: Path, fa, fb, only_a, only_b, diff, use_hash: bool):
    from html import escape as e

    first_level_palette = ["#dfeaff", "#e8f5e9", "#fff1d6", "#f3e8ff", "#fde7f1", "#daf5f3"]
    second_level_palette = ["#b8d6ff", "#bfe7c6", "#ffdca8", "#d6b7f5", "#f7b7d0", "#a9e5e0"]

    def dir_color(rel: str, level: int) -> str:
        palette = first_level_palette if level == 1 else second_level_palette
        segments = rel.split("/")
        key = segments[level - 1] if len(segments) >= level else "(root)"
        idx = sum(ord(ch) for ch in key) % len(palette)
        return palette[idx]

    def render_rel_path(rel: str) -> str:
        parts = rel.split("/")
        if len(parts) == 1:
            return e(rel)

        first = parts[0]
        second = parts[1] if len(parts) > 1 else ""
        remaining = "/".join(parts[1:])

        html = (
            f'<span class="dir-chip" style="background:{dir_color(rel, 1)}; color:#111; font-weight:700; '
            f'border-radius:4px; padding:1px 6px; margin-right:4px;">{e(first)}/</span>'
        )

        if len(parts) >= 3:
            html += (
                f'<span class="dir-chip" style="background:{dir_color(rel, 2)}; color:#111; font-weight:700; '
                f'border-radius:4px; padding:1px 6px; margin-right:4px;">{e(second)}/</span>'
            )
            rest = "/".join(parts[2:])
            if rest:
                html += f'<span>{e(rest)}</span>'
            return html

        html += f'<span>{e(remaining)}</span>'
        return html

    def size(s):
        return f"{s.st_size:,}"

    only_a = sort_rel_paths(only_a)
    only_b = sort_rel_paths(only_b)
    diff = sorted(diff, key=lambda item: (item[0].count("/"), item[0]))

    rows_a = "".join(
        f"<tr><td>{render_rel_path(r)}</td><td class=n>{size(fa[r])}</td><td>{fmt_time(fa[r].st_mtime)}</td></tr>"
        for r in only_a)
    rows_b = "".join(
        f"<tr><td>{render_rel_path(r)}</td><td class=n>{size(fb[r])}</td><td>{fmt_time(fb[r].st_mtime)}</td></tr>"
        for r in only_b)
    rows_d = "".join(
        f"<tr><td>{render_rel_path(r)}</td><td>{e(reason)}</td>"
        f"<td class=n>{size(sa)}</td><td{' class=newer' if newer == 'A' else ''}>{fmt_time(sa.st_mtime)}</td>"
        f"<td class=n>{size(sb)}</td><td{' class=newer' if newer == 'B' else ''}>{fmt_time(sb.st_mtime)}</td>"
        f"<td>{newer}</td></tr>"
        for r, reason, sa, sb, newer in diff)
    empty = "<tr><td colspan=7 class=empty>無</td></tr>"

    doc = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>目錄差異報表 {datetime.now():%Y-%m-%d %H:%M}</title>
<style>
 body{{font-family:"Microsoft JhengHei","PingFang TC",system-ui,sans-serif;margin:24px;color:#222;background:#fafafa}}
 h1{{font-size:20px;margin:0 0 8px}} h2{{font-size:16px;margin:28px 0 8px}}
 .meta{{color:#555;font-size:13px;line-height:1.7}} code{{background:#eee;padding:1px 5px;border-radius:3px}}
 .cards{{display:flex;gap:12px;margin:16px 0;flex-wrap:wrap}}
 .card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px 16px;min-width:140px}}
 .card b{{display:block;font-size:24px}}
 .a b{{color:#1565c0}} .b b{{color:#2e7d32}} .d b{{color:#c62828}}
 input{{padding:6px 10px;width:320px;max-width:100%;border:1px solid #ccc;border-radius:6px}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
 th,td{{border:1px solid #ddd;padding:5px 8px;text-align:left}} th{{background:#f0f0f0;position:sticky;top:0}}
 td.n{{text-align:right;font-variant-numeric:tabular-nums}} td.newer{{background:#fff3cd}}
 .empty{{color:#999;text-align:center}}
 .dir-chip{{display:inline-block;box-shadow:inset 0 0 0 1px rgba(0,0,0,0.08);}}
</style></head><body>
<h1>目錄差異報表</h1>
<div class=meta>
 產生時間：{datetime.now():%Y-%m-%d %H:%M:%S}<br>
 A：<code>{e(str(a))}</code>（{len(fa)} 個檔案）<br>
 B：<code>{e(str(b))}</code>（{len(fb)} 個檔案）<br>
 比對方式：{"SHA-256 內容雜湊" if use_hash else "檔案大小＋修改時間"}
</div>
<div class=cards>
 <div class="card a">只在 A<b>{len(only_a)}</b></div>
 <div class="card b">只在 B<b>{len(only_b)}</b></div>
 <div class="card d">內容不一致<b>{len(diff)}</b></div>
</div>
<input id=q placeholder="篩選路徑…" oninput="f(this.value)">
<h2>只在 A 有（{len(only_a)}） - {e(str(a))}</h2>
<table><tr><th>相對路徑</th><th>大小 (bytes)</th><th>修改時間</th></tr>{rows_a or empty}</table>
<h2>只在 B 有（{len(only_b)}） - {e(str(b))}</h2>
<table><tr><th>相對路徑</th><th>大小 (bytes)</th><th>修改時間</th></tr>{rows_b or empty}</table>
<h2>兩邊都有但不一致（{len(diff)}）</h2>
<table><tr><th>相對路徑</th><th>原因</th><th>A 大小</th><th>A 修改時間</th><th>B 大小</th><th>B 修改時間</th><th>較新</th></tr>{rows_d or empty}</table>
<script>
function f(v){{v=v.toLowerCase();document.querySelectorAll('tr').forEach(r=>{{
 if(r.querySelector('th')||r.querySelector('.empty'))return;
 r.style.display=r.cells[0].textContent.toLowerCase().includes(v)?'':'none';}});}}
</script>
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description="比對兩個目錄的差異")
    p.add_argument("dir_a", nargs="?", help="目錄 A 路徑（可不填，則用 UI 選擇）")
    p.add_argument("dir_b", nargs="?", help="目錄 B 路徑（可不填，則用 UI 選擇）")
    p.add_argument("--hash", action="store_true", help="用 SHA-256 比對內容")
    p.add_argument("--csv", metavar="FILE", help="輸出 CSV 報表（Excel 可直接開）")
    p.add_argument("--outdir", default=".", help="HTML 報表輸出資料夾（預設為目前資料夾）")
    p.add_argument("--no-html", action="store_true", help="不輸出 HTML 報表")
    p.add_argument("--ignore", nargs="*", default=[], help="忽略的檔名或資料夾名")
    args = p.parse_args()

    if args.dir_a and args.dir_b:
        a, b = Path(args.dir_a).resolve(), Path(args.dir_b).resolve()
    else:
        a = choose_directory("選擇目錄 A")
        if not a:
            sys.exit("未選擇目錄 A")
        b = choose_directory("選擇目錄 B")
        if not b:
            sys.exit("未選擇目錄 B")

    for d in (a, b):
        if not d.is_dir():
            sys.exit(f"找不到目錄：{d}")

    fa, fb, only_a, only_b, diff = compare(a, b, args.hash, set(args.ignore))

    print(f"A = {a}  （{len(fa)} 個檔案）")
    print(f"B = {b}  （{len(fb)} 個檔案）\n")

    print(f"=== 只在 A 有（{len(only_a)}）===")
    for rel in only_a:
        print(f"  + {rel}")

    print(f"\n=== 只在 B 有（{len(only_b)}）===")
    for rel in only_b:
        print(f"  + {rel}")

    print(f"\n=== 兩邊都有但不一致（{len(diff)}）===")
    for rel, reason, sa, sb, newer in diff:
        print(f"  * {rel}  [{reason}，{newer} 較新]")
        print(f"      A: {sa.st_size:>12,} bytes  {fmt_time(sa.st_mtime)}")
        print(f"      B: {sb.st_size:>12,} bytes  {fmt_time(sb.st_mtime)}")

    if not (only_a or only_b or diff):
        print("\n兩個目錄完全一致。")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["狀態", "相對路徑", "A大小", "A修改時間", "B大小", "B修改時間", "較新"])
            for rel in only_a:
                s = fa[rel]
                w.writerow(["只在A", rel, s.st_size, fmt_time(s.st_mtime), "", "", ""])
            for rel in only_b:
                s = fb[rel]
                w.writerow(["只在B", rel, "", "", s.st_size, fmt_time(s.st_mtime), ""])
            for rel, reason, sa, sb, newer in diff:
                w.writerow([reason, rel, sa.st_size, fmt_time(sa.st_mtime),
                            sb.st_size, fmt_time(sb.st_mtime), newer])
        print(f"\nCSV 報表已輸出：{args.csv}")

    if not args.no_html:
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        html_path = outdir / f"dir_diff_{datetime.now():%Y%m%d_%H%M%S}.html"
        write_html(html_path, a, b, fa, fb, only_a, only_b, diff, args.hash)
        abs_html_path = html_path.resolve()
        print(f"\nHTML 報表已輸出：{abs_html_path}")
        webbrowser.open_new_tab(abs_html_path.as_uri())


if __name__ == "__main__":
    main()