#!/usr/bin/env python3
"""UI 版本：選擇兩個目錄進行比對，並在預設瀏覽器中查看 HTML 報表。"""

import hashlib
import os
import queue
import sys
import threading
import time
import webbrowser
import tkinter as tk
from datetime import datetime
from html import escape as e
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk


REPORT_DIR = Path(__file__).resolve().parent
DEFAULT_IGNORE = ".git __pycache__ .DS_Store Thumbs.db"


# ───────────────────────────── 比對邏輯 ─────────────────────────────

def scan(root: Path, ignore: set[str]) -> dict[str, os.stat_result]:
    """回傳 {相對路徑: stat}，只收檔案，路徑統一用 / 分隔。"""
    files = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignore]
        for name in filenames:
            if name in ignore or name.startswith("~"):
                continue
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            try:
                files[rel] = full.stat()
            except OSError:
                pass
    return files


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{n:,} B" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{n:,} B"


def compare(a: Path, b: Path, use_hash: bool, ignore: set[str], tolerance: float = 2.0, progress=None):
    report = progress or (lambda msg: None)
    report("掃描目錄 A…")
    fa = scan(a, ignore)
    report(f"掃描目錄 B…（A 共 {len(fa):,} 個檔案）")
    fb = scan(b, ignore)

    only_a = sorted(fa.keys() - fb.keys())
    only_b = sorted(fb.keys() - fa.keys())
    common = sorted(fa.keys() & fb.keys())
    total = len(common)
    diff = []

    for i, rel in enumerate(common, 1):
        if i % 50 == 0 or i == total:
            report(f"比對共同檔案… {i:,} / {total:,}")
        sa, sb = fa[rel], fb[rel]
        if sa.st_size != sb.st_size:
            reason = "大小不同"
        elif use_hash:
            try:
                if file_hash(a / rel) == file_hash(b / rel):
                    continue
                reason = "內容不同"
            except OSError:
                reason = "無法讀取"
        elif abs(sa.st_mtime - sb.st_mtime) > tolerance:
            reason = "修改時間不同"
        else:
            continue
        newer = "A" if sa.st_mtime > sb.st_mtime else "B"
        diff.append((rel, reason, sa, sb, newer))

    return fa, fb, only_a, only_b, diff


def sort_rel_paths(paths):
    """依目錄層級排序：先根目錄項目，再逐層子目錄。"""
    return sorted(paths, key=lambda p: (p.count("/"), p))


# ───────────────────────────── HTML 報表 ─────────────────────────────

REPORT_CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--fg:#1f2328;--muted:#656d76;--line:#d8dee4;--head:#f0f2f5;
 --code:#eef1f4;--hover:#f3f6fb;--newer:#fff4cc;--a:#1f6feb;--b:#1a7f37;--d:#cf222e;--tb:58px}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--panel:#161b22;--fg:#e6edf3;--muted:#8d96a0;
 --line:#30363d;--head:#1c2128;--code:#21262d;--hover:#1c2533;--newer:#3d3418;--a:#4493f8;--b:#3fb950;--d:#f85149}}
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft JhengHei","PingFang TC",system-ui,sans-serif;font-size:14px;color:var(--fg);background:var(--bg)}
.wrap{max-width:1280px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 6px}
.meta{color:var(--muted);font-size:13px;line-height:1.9}
code{background:var(--code);padding:1px 6px;border-radius:4px;font-family:Consolas,monospace;word-break:break-all}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0 8px}
.card{display:block;text-decoration:none;color:inherit;background:var(--panel);border:1px solid var(--line);
 border-left:4px solid var(--c);border-radius:8px;padding:12px 16px}
.card:hover{background:var(--hover)}
.card b{display:block;font-size:28px;color:var(--c);font-variant-numeric:tabular-nums}
.a{--c:var(--a)} .b{--c:var(--b)} .d{--c:var(--d)}
.toolbar{position:sticky;top:0;z-index:3;height:var(--tb);display:flex;align-items:center;gap:12px;
 background:var(--bg);border-bottom:1px solid var(--line)}
#q{flex:1;max-width:420px;padding:7px 12px;font-size:14px;color:var(--fg);background:var(--panel);
 border:1px solid var(--line);border-radius:6px;outline:none}
#q:focus{border-color:var(--a);box-shadow:0 0 0 3px color-mix(in srgb,var(--a) 25%,transparent)}
.hint{color:var(--muted);font-size:12px}
kbd{border:1px solid var(--line);border-bottom-width:2px;border-radius:4px;padding:0 5px;font-size:11px}
section{margin-top:28px;scroll-margin-top:calc(var(--tb) + 8px)}
h2{display:flex;align-items:center;gap:8px;font-size:16px;margin:0 0 2px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--c)}
.count{font-size:12px;font-weight:600;padding:1px 9px;border-radius:10px;background:var(--code);color:var(--muted)}
.sub{color:var(--muted);font-size:12px;margin:0 0 8px 18px;word-break:break-all}
table{border-collapse:collapse;width:100%;background:var(--panel);font-size:13px;border:1px solid var(--line)}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{position:sticky;top:var(--tb);z-index:2;background:var(--head);font-weight:600;white-space:nowrap}
tbody tr:hover td{background:var(--hover)}
td.p{word-break:break-all;width:55%} td.t{white-space:nowrap}
.n{text-align:right!important;white-space:nowrap;font-variant-numeric:tabular-nums}
td.newer{background:var(--newer)} .c{text-align:center!important}
.empty td,.nomatch td{color:var(--muted);text-align:center;padding:14px}
.chip{display:inline-block;color:#111;font-weight:700;border-radius:4px;padding:0 6px;margin-right:4px;
 box-shadow:inset 0 0 0 1px rgba(0,0,0,.08)}
.badge{display:inline-block;min-width:24px;border-radius:10px;padding:0 8px;font-weight:700;color:#fff;background:var(--c)}
.reason{white-space:nowrap}
"""

REPORT_JS = """
const q=document.getElementById('q');
function f(){
 const v=q.value.trim().toLowerCase();
 document.querySelectorAll('section').forEach(s=>{
  const rows=s.querySelectorAll('tbody tr[data-p]');let n=0;
  rows.forEach(r=>{const ok=!v||r.dataset.p.includes(v);r.hidden=!ok;if(ok)n++;});
  s.querySelector('.count').textContent=v?`${n} / ${rows.length}`:rows.length;
  const nm=s.querySelector('.nomatch');if(nm)nm.hidden=!(v&&rows.length&&!n);
 });
}
q.addEventListener('input',f);
document.addEventListener('keydown',ev=>{
 if(ev.key==='/'&&document.activeElement!==q){ev.preventDefault();q.focus();q.select();}
 else if(ev.key==='Escape'&&document.activeElement===q){q.value='';f();q.blur();}
});
"""


def write_html(path: Path, a: Path, b: Path, fa, fb, only_a, only_b, diff, use_hash: bool):
    first_level_palette = ["#dfeaff", "#e8f5e9", "#fff1d6", "#f3e8ff", "#fde7f1", "#daf5f3"]
    second_level_palette = ["#b8d6ff", "#bfe7c6", "#ffdca8", "#d6b7f5", "#f7b7d0", "#a9e5e0"]

    def chip(name: str, palette: list[str]) -> str:
        color = palette[sum(ord(ch) for ch in name) % len(palette)]
        return f'<span class=chip style="background:{color}">{e(name)}/</span>'

    def render_rel_path(rel: str) -> str:
        parts = rel.split("/")
        if len(parts) == 1:
            return e(rel)
        html = chip(parts[0], first_level_palette)
        if len(parts) >= 3:
            html += chip(parts[1], second_level_palette)
            return html + e("/".join(parts[2:]))
        return html + e(parts[1])

    def size_td(st) -> str:
        return f'<td class=n title="{st.st_size:,} bytes">{human_size(st.st_size)}</td>'

    def row_attr(rel: str) -> str:
        return f'data-p="{e(rel.lower(), quote=True)}"'

    def body(rows: str, cols: int) -> str:
        if not rows:
            return f"<tbody><tr class=empty><td colspan={cols}>無</td></tr></tbody>"
        return f"<tbody>{rows}<tr class=nomatch hidden><td colspan={cols}>沒有符合篩選的項目</td></tr></tbody>"

    only_a = sort_rel_paths(only_a)
    only_b = sort_rel_paths(only_b)
    diff = sorted(diff, key=lambda item: (item[0].count("/"), item[0]))

    rows_a = "".join(
        f"<tr {row_attr(r)}><td class=p>{render_rel_path(r)}</td>{size_td(fa[r])}"
        f"<td class=t>{fmt_time(fa[r].st_mtime)}</td></tr>"
        for r in only_a)
    rows_b = "".join(
        f"<tr {row_attr(r)}><td class=p>{render_rel_path(r)}</td>{size_td(fb[r])}"
        f"<td class=t>{fmt_time(fb[r].st_mtime)}</td></tr>"
        for r in only_b)
    rows_d = "".join(
        f"<tr {row_attr(r)}><td class=p>{render_rel_path(r)}</td><td class=reason>{e(reason)}</td>"
        f"{size_td(sa)}<td class=\"t{' newer' if newer == 'A' else ''}\">{fmt_time(sa.st_mtime)}</td>"
        f"{size_td(sb)}<td class=\"t{' newer' if newer == 'B' else ''}\">{fmt_time(sb.st_mtime)}</td>"
        f"<td class=c><span class=\"badge {newer.lower()}\">{newer}</span></td></tr>"
        for r, reason, sa, sb, newer in diff)

    single_head = "<thead><tr><th>相對路徑</th><th class=n>大小</th><th>修改時間</th></tr></thead>"
    diff_head = ("<thead><tr><th>相對路徑</th><th>原因</th><th class=n>A 大小</th><th>A 修改時間</th>"
                 "<th class=n>B 大小</th><th>B 修改時間</th><th class=c>較新</th></tr></thead>")
    now = datetime.now()

    doc = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>目錄差異報表 {now:%Y-%m-%d %H:%M}</title>
<style>{REPORT_CSS}</style></head><body><div class=wrap>
<h1>目錄差異報表</h1>
<div class=meta>
 產生時間：{now:%Y-%m-%d %H:%M:%S}　·　比對方式：{"SHA-256 內容雜湊" if use_hash else "檔案大小＋修改時間"}<br>
 A：<code>{e(str(a))}</code>（{len(fa):,} 個檔案）<br>
 B：<code>{e(str(b))}</code>（{len(fb):,} 個檔案）
</div>
<div class=cards>
 <a class="card a" href="#sec-a">只在 A<b>{len(only_a):,}</b></a>
 <a class="card b" href="#sec-b">只在 B<b>{len(only_b):,}</b></a>
 <a class="card d" href="#sec-d">內容不一致<b>{len(diff):,}</b></a>
</div>
<div class=toolbar>
 <input id=q type=search placeholder="篩選路徑…" autocomplete=off>
 <span class=hint>按 <kbd>/</kbd> 搜尋，<kbd>Esc</kbd> 清除</span>
</div>
<section id=sec-a class=a>
 <h2><span class=dot></span>只在 A 有<span class=count>{len(only_a)}</span></h2>
 <div class=sub>{e(str(a))}</div>
 <table>{single_head}{body(rows_a, 3)}</table>
</section>
<section id=sec-b class=b>
 <h2><span class=dot></span>只在 B 有<span class=count>{len(only_b)}</span></h2>
 <div class=sub>{e(str(b))}</div>
 <table>{single_head}{body(rows_b, 3)}</table>
</section>
<section id=sec-d class=d>
 <h2><span class=dot></span>兩邊都有但不一致<span class=count>{len(diff)}</span></h2>
 <div class=sub>標示底色的修改時間為較新的一方</div>
 <table>{diff_head}{body(rows_d, 7)}</table>
</section>
</div>
<script>{REPORT_JS}</script>
</body></html>"""
    path.write_text(doc, encoding="utf-8")


def save_html(a: Path, b: Path, use_hash: bool, ignore: set[str], progress=None):
    """比對並寫出報表，回傳 (報表路徑, (只在A數, 只在B數, 不一致數))。"""
    fa, fb, only_a, only_b, diff = compare(a, b, use_hash, ignore, progress=progress)
    if progress:
        progress("產生 HTML 報表…")
    html_path = REPORT_DIR / f"dir_diff_ui_{datetime.now():%Y%m%d_%H%M%S}.html"
    write_html(html_path, a, b, fa, fb, only_a, only_b, diff, use_hash)
    return html_path, (len(only_a), len(only_b), len(diff))


# ───────────────────────────── 視窗 UI ─────────────────────────────

BG = "#f3f5f9"
CARD = "#ffffff"
BORDER = "#dde3ec"
FG = "#1f2328"
MUTED = "#656d76"
ACCENT = "#2d7d32"
ACCENT_HOVER = "#256a2a"
ACCENT_PRESSED = "#1f5a24"
COLOR_A = "#1565c0"
COLOR_B = "#2e7d32"
COLOR_D = "#c62828"


def enable_dpi_awareness():
    """Windows 高 DPI 螢幕下避免文字模糊，並讓工作列顯示本程式圖示（而非 Python 圖示）。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FileDiff.UI")
    except Exception:
        pass


def set_window_icon(root: tk.Tk) -> list[tk.PhotoImage]:
    """設定視窗左上角與工作列圖示（圖檔內嵌於 ICON_PNGS_B64）。回傳圖片以保留參照（避免被回收）。"""
    try:
        images = [tk.PhotoImage(data="".join(b64.split())) for b64 in ICON_PNGS_B64]
        root.iconphoto(True, *images)
        return images
    except tk.TclError:
        return []  # 圖示載入失敗時維持預設圖示，不影響主程式


class FileDiffUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("FileDiff 目錄比對")
        self.root.configure(bg=BG)
        self.icon_images = set_window_icon(root)

        families = set(tkfont.families(root))
        family = next((f for f in ("Microsoft JhengHei UI", "Microsoft JhengHei", "Segoe UI") if f in families),
                      "TkDefaultFont")
        self.font_body = (family, 10)
        self.font_small = (family, 9)
        self.font_bold = (family, 10, "bold")
        self.font_title = (family, 16, "bold")
        self.font_count = (family, 15, "bold")

        self.a_var = tk.StringVar()
        self.b_var = tk.StringVar()
        self.hash_var = tk.BooleanVar(value=False)
        self.ignore_var = tk.StringVar(value=DEFAULT_IGNORE)
        self.status_var = tk.StringVar(value="選擇兩個目錄後按「開始比對」（Enter）。")

        self.events: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_report: Path | None = None
        self.last_dir: str | None = None
        self.started = 0.0

        self._apply_style()
        self.build_ui()

        self.root.bind("<Return>", lambda _e: self.compare_dirs())
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_reqwidth(), self.root.winfo_reqheight())

    # ── 樣式 ──
    def _apply_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=CARD, foreground=FG, font=self.font_body)
        style.configure("TFrame", background=CARD)
        style.configure("Bg.TFrame", background=BG)
        style.configure("TLabel", background=CARD, foreground=FG)
        style.configure("Title.TLabel", background=BG, font=self.font_title)
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED)
        style.configure("Section.TLabel", background=CARD, font=self.font_bold)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=self.font_small)

        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=(8, 5))
        style.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
                  fieldbackground=[("disabled", "#f3f4f6")])

        style.configure("TRadiobutton", background=CARD, padding=(0, 3))
        style.map("TRadiobutton", background=[("active", CARD)], indicatorcolor=[("selected", ACCENT)])

        style.configure("TButton", background="#f6f8fa", foreground=FG, bordercolor=BORDER,
                        lightcolor="#f6f8fa", darkcolor="#f6f8fa", padding=(14, 5), focuscolor=BORDER)
        style.map("TButton",
                  background=[("disabled", "#f6f8fa"), ("pressed", "#e4e9f0"), ("active", "#eef2f7")],
                  foreground=[("disabled", "#a0a7b0")])
        style.configure("Link.TButton", background=CARD, bordercolor=CARD, lightcolor=CARD, darkcolor=CARD,
                        foreground=COLOR_A, padding=(4, 1), font=self.font_small)
        style.map("Link.TButton", background=[("pressed", "#e8f0fb"), ("active", "#f0f5fd")])

        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", bordercolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT, padding=(26, 8), font=self.font_bold,
                        focuscolor=ACCENT)
        style.map("Accent.TButton",
                  background=[("disabled", "#9fc4a1"), ("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
                  lightcolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
                  darkcolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
                  foreground=[("disabled", "#ffffff")])

        style.configure("Horizontal.TProgressbar", troughcolor="#e8ecf1", background=ACCENT,
                        bordercolor="#e8ecf1", lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)

    def _card(self, parent, title: str | None = None) -> ttk.Frame:
        border = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        border.pack(fill="x", pady=(0, 12))
        inner = ttk.Frame(border, padding=(16, 12, 16, 14))
        inner.pack(fill="both", expand=True)
        if title:
            ttk.Label(inner, text=title, style="Section.TLabel").grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        return inner

    # ── 版面 ──
    def build_ui(self):
        outer = ttk.Frame(self.root, style="Bg.TFrame", padding=(20, 16, 20, 18))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="FileDiff 目錄比對", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="比較兩個資料夾的檔案差異，結果以 HTML 報表在瀏覽器開啟。",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(2, 14))

        # 目錄
        paths = self._card(outer, "比較目錄")
        self.inputs: list[tk.Widget] = []
        for row, (label, var, color) in enumerate((("目錄 A", self.a_var, COLOR_A),
                                                    ("目錄 B", self.b_var, COLOR_B)), start=1):
            ttk.Label(paths, text=label, foreground=color, font=self.font_bold).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            entry = ttk.Entry(paths, textvariable=var, width=60)
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            btn = ttk.Button(paths, text="瀏覽…", command=lambda v=var, l=label: self.set_path(v, l))
            btn.grid(row=row, column=2, padx=(8, 0), pady=4)
            self.inputs += [entry, btn]
        swap = ttk.Button(paths, text="⇅ 交換 A / B", style="Link.TButton", command=self.swap_paths)
        swap.grid(row=3, column=1, sticky="w", pady=(2, 0))
        self.inputs.append(swap)
        paths.columnconfigure(1, weight=1)

        # 選項
        opts = self._card(outer, "比對選項")
        ttk.Label(opts, text="比對方式").grid(row=1, column=0, sticky="nw", padx=(0, 12), pady=3)
        modes = ttk.Frame(opts)
        modes.grid(row=1, column=1, sticky="w")
        for text, value in (("檔案大小＋修改時間（快速）", False),
                            ("SHA-256 內容雜湊（準確，檔案多時較慢）", True)):
            rb = ttk.Radiobutton(modes, text=text, variable=self.hash_var, value=value)
            rb.pack(anchor="w")
            self.inputs.append(rb)

        ttk.Label(opts, text="忽略名稱").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(10, 0))
        ignore = ttk.Entry(opts, textvariable=self.ignore_var)
        ignore.grid(row=2, column=1, sticky="ew", pady=(10, 0))
        self.inputs.append(ignore)
        ttk.Label(opts, text="以空白分隔，比對檔名或資料夾名稱；「~」開頭的暫存檔一律略過。",
                  style="Muted.TLabel").grid(row=3, column=1, sticky="w", pady=(4, 0))
        opts.columnconfigure(1, weight=1)

        # 狀態 / 結果
        status = self._card(outer)
        ttk.Label(status, textvariable=self.status_var, wraplength=560).grid(
            row=0, column=0, columnspan=4, sticky="w")
        self.progress = ttk.Progressbar(status, mode="indeterminate")
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 4))

        self.count_labels = []
        for col, (text, color) in enumerate((("只在 A", COLOR_A), ("只在 B", COLOR_B), ("不一致", COLOR_D))):
            box = ttk.Frame(status)
            box.grid(row=2, column=col, sticky="w", padx=(0, 28), pady=(4, 0))
            num = ttk.Label(box, text="–", foreground=color, font=self.font_count)
            num.pack(side="left")
            ttk.Label(box, text=text, style="Muted.TLabel").pack(side="left", padx=(6, 0), pady=(4, 0))
            self.count_labels.append(num)
        self.reopen_btn = ttk.Button(status, text="重新開啟報表", command=self.open_last_report, state="disabled")
        self.reopen_btn.grid(row=2, column=3, sticky="e")
        status.columnconfigure(3, weight=1)

        # 動作列
        actions = ttk.Frame(outer, style="Bg.TFrame")
        actions.pack(fill="x", pady=(4, 0))
        self.clear_btn = ttk.Button(actions, text="清除", command=self.clear_paths)
        self.clear_btn.pack(side="left")
        ttk.Button(actions, text="開啟報表資料夾", command=self.open_report_dir).pack(side="left", padx=(8, 0))
        self.run_btn = ttk.Button(actions, text="開始比對", style="Accent.TButton", command=self.compare_dirs)
        self.run_btn.pack(side="right")

    # ── 動作 ──
    def set_path(self, var: tk.StringVar, label: str):
        current = var.get().strip()
        initial = current if current and Path(current).is_dir() else self.last_dir
        selected = filedialog.askdirectory(parent=self.root, title=f"選擇{label}", initialdir=initial)
        if selected:
            path = str(Path(selected).resolve())
            var.set(path)
            self.last_dir = str(Path(path).parent)

    def swap_paths(self):
        a, b = self.a_var.get(), self.b_var.get()
        self.a_var.set(b)
        self.b_var.set(a)

    def clear_paths(self):
        self.a_var.set("")
        self.b_var.set("")
        self._reset_result("已清除。選擇兩個目錄後按「開始比對」（Enter）。")

    def open_report_dir(self):
        if sys.platform == "win32":
            os.startfile(REPORT_DIR)
        else:
            webbrowser.open(REPORT_DIR.as_uri())

    def open_last_report(self):
        if self.last_report and self.last_report.exists():
            webbrowser.open_new_tab(self.last_report.as_uri())

    def _validate(self) -> tuple[Path, Path] | None:
        raw = {"A": self.a_var.get().strip().strip('"'), "B": self.b_var.get().strip().strip('"')}
        for name, value in raw.items():
            if not value:
                messagebox.showwarning("缺少目錄", f"請先選擇目錄 {name}。", parent=self.root)
                return None
            if not Path(value).is_dir():
                messagebox.showerror("目錄不存在", f"找不到目錄 {name}：\n{value}", parent=self.root)
                return None
        a, b = Path(raw["A"]).resolve(), Path(raw["B"]).resolve()
        if a == b:
            messagebox.showwarning("目錄相同", "目錄 A 與目錄 B 是同一個資料夾。", parent=self.root)
            return None
        return a, b

    def compare_dirs(self):
        if self.worker and self.worker.is_alive():
            return
        paths = self._validate()
        if not paths:
            return
        a, b = paths
        self._reset_result("準備中…")
        self._set_busy(True)
        self.started = time.perf_counter()
        self.worker = threading.Thread(
            target=self._run_compare,
            args=(a, b, self.hash_var.get(), set(self.ignore_var.get().split())),
            daemon=True,
        )
        self.worker.start()
        self.root.after(100, self._poll)

    def _run_compare(self, a: Path, b: Path, use_hash: bool, ignore: set[str]):
        try:
            result = save_html(a, b, use_hash, ignore, progress=lambda msg: self.events.put(("status", msg)))
            self.events.put(("done", result))
        except Exception as exc:  # 交給 UI 執行緒顯示
            self.events.put(("error", exc))

    def _poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "done":
                    self._on_done(*payload)
                    return
                elif kind == "error":
                    self._on_error(payload)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _on_done(self, html_path: Path, counts: tuple[int, int, int]):
        self._set_busy(False)
        self.progress.configure(mode="determinate", value=100)
        elapsed = time.perf_counter() - self.started
        for label, n in zip(self.count_labels, counts):
            label.configure(text=f"{n:,}")
        self.last_report = html_path
        self.reopen_btn.configure(state="normal")
        verdict = "兩個目錄一致 ✓" if not any(counts) else "發現差異"
        self.status_var.set(f"{verdict}　·　耗時 {elapsed:.1f} 秒　·　報表：{html_path.name}")
        webbrowser.open_new_tab(html_path.as_uri())

    def _on_error(self, exc: Exception):
        self._set_busy(False)
        self.progress.configure(mode="determinate", value=0)
        self.status_var.set("比對失敗。")
        messagebox.showerror("比對失敗", f"{type(exc).__name__}: {exc}", parent=self.root)

    def _reset_result(self, message: str):
        self.status_var.set(message)
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        for label in self.count_labels:
            label.configure(text="–")

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        for widget in (*self.inputs, self.run_btn, self.clear_btn):
            widget.configure(state=state)
        self.run_btn.configure(text="比對中…" if busy else "開始比對")
        self.root.configure(cursor="watch" if busy else "")
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()

    def run(self):
        self.root.mainloop()


# 視窗圖示（PNG，base64）：原始 logo 補成正方形，16/32/48/64 px
ICON_PNGS_B64 = (
    # 64x64
    """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
RK5CYII=""",
    # 48x48
    """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
+l+4tVJtmmOzWwAAAABJRU5ErkJggg==""",
    # 32x32
    """iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAHRklEQVR42tVWa3BVVxVea+/zvPdyc29ubkISknLDM0gfgQCtth2n
thTbojjToTpUqIM44pTRX3XUPgZl1FasdmT8gQ590CGtdagItR0HK0ILpUJtSQLEJDwChJDcJPd9Xnvv5Y+bXBPsH2fsD9evffY5
Z6291vr2tz5sSLXCJ2kMPmH7XwZARMSyQ6psagAIiAAERABA+F86BUSGjDFSynE9ALBMSwEDUkgCALXyV0SE13lHhhOPqKQEqVBj
yJEIQBEAMMYQUYjAKbi+53PNmJNKWaHw+XP9XNcnogNoAEQE086OCADKd0gIQEZS6VURngj7467KBKghD3HGWKlYchy/piZ564q2
tra2uz6zYlbbsqd2dPR0bw2bMSVVpUQApCp+kXHluUBoz1po1LVooah0iv5It1XvsvsaNGYWjg8XOq+5nrv8jju/vnH9wnnz5rQ0
2RwAYMux4MyVnMmAAKf2ABAQAIgAGZNOyUimoivWGo0txDgD0E2LB07/yz+N9Y/K9uraTcsj53JXd7/X192ra8a8uU3FUsAN+Nm7
194biXOnoAg4KCBVLhErF4eAgKHyHKt+ceyuR1X8BjebVV4AwDw/8Mxo/M41NdHkY59+9OpPjnm23fDk2oyVe3D1Qx+cvhAP6R2d
mdf6RJVJXn6MEKc2cxKmjJEIWLQ+tGKd5zpUzJiGKfpPjL/9UubQHn+gJ9bceqLrtJ4wfrltx8hv/qb6Lrnp/LbtP17yqdl/7hn9
9YdFy2DkFmQpi4zRdJhOdJkkGQtXeUGggdCAD7/xXGGgCzl62XG9utmqbWZAr+155eWOnQ/84b4Xv7v94U3f/uaWDWeuZJ8+kkaB
IUVkmEFhHBhDIphsA5vAkwxwRj1EZgX5MUJz/Pje4sCpSLLeskN1y+63F9yR7zwsnTGu6SWlFtx486Jbbn9i2w8HR5ytf+rPkjV+
4Ffd2zfx9ACJAPH6iwaIqKTUIrXgOwhMjV7yrnbbiTrh5oyqxtBtG+TIhbGjr3LDMsxw3mX1zc1bf/6sYZnP7O86kzPtM3uvHtuH
CKd+sZlryDRdETGciKL9G/x6TPmS6yDHLyNIJIksHFq6FgMn/ZedJIszYvHDB988ceyRuYvbbI1eervn8BURG+vt/v1zoXiEo+7n
h0E3uG2RkgQT15RN3ABCUqCkACkYSEBUQoYWr2Iz6rJHO4LMRd2OGAZPp6/9bs8Ltmke6Rrs+GA44qXPPr8ttWa2GafoktXzt+zU
qhtV4E86rwQgUkDSySohXFcoHlGBYzbdxmYuLXa+VRo4ac6IA6hSobhkxR1f/tqmrv6h3Ud6LUs//8LT4Zv9GzYszp7PZy6cgeS8
2ns2Kt/D6wMAIUNZuIaB8B3HVbbdskrWtXsD/yj+87AZiQJIhuj7fn1TKlo3+7f7jhVdyLy5K4D+ed9flXX9xpWLir3v5nveN6qS
yHUgVenzRAZMM1RpGLwcKRJCyOpFzM2XTh/gXJLyKHCU9EEEcxYtfX7/3weyQpw9kv5w//wffNFjERWL1XwpZUZrrPo5+fNdolRE
5BUcaWVMITIEzx08aTR9VgQeeHm3/y0McmZyNuohRJReKTKz7p1zzggMmum+oXd2pzbf7dcmaaTI4wZmhChmnMu9eqLFTqaUNwqM
TSE7ACLJTdsdP4tGldF0u3/uDXLHQgu+EFi1eijKTUNDhpo2OOpo3uWhv+5KrGyFJTe5Q3lNZ2BzvFIAxd30UOLuR2KXPxo+tEuP
xMocig2pVgVUJm8pyXME2jMZlayW+13gLQvnOIN9Q2eP66EIM8OmHR7rPBhqa4iuf0C5yjQUacqynIHvddiL1keWrsod2ulfPMlk
iTE+lU0nGJtpmmlT4A2a89d6kq9+aKUpc6/ufUqvXy70mG5Hndx5zQxCrXVB12nmuZ7GjKhVGhwKxkV41o3FzkPZ91+3EgnkvFz4
yjygygBCUqHmz+VcbeM37p3VmHj2W5t54iasaZfASQx7o716VePYvrMkA0BUUjJRZHrMXPB5xSLyyulQPM51g2QAOK0HVCZUCFxe
vXSoVL3uK+333rPs8Q0Pjjt6VcutXmGMMQCdW3NXE2JI0xX5zIxTuse/cNBqXyeTrar/aHDpBNd1UGJiuuA0qgCSAiOpjDb3q2va
H39szZPfeeKjU33JtocDzzVMi0hKQgoYIkhJTAtT+qK4dIRpZqH7AKnXWSltWDoAqxRnGooAAIALnrC8i6lI844fPfPHV16M198i
M/0oXVk5DwICI1KkW8HwSQ19plmaM0gktFCEMQSlCGiqGsKGVCuRLAfwXU9KP5d3GOeJZFL4jghcBAZQ+Q2xLG4YNyybcQ4kAVlZ
mEze3vK4Z2XCmJqBMiyDwAjPiAGCJKmbpm5YAFTJGmGShZEBCSAFUAH5x1t5HkzJCIBIlHUBTkK40qbKgkiWlRxAGe9IRDiVoSdD
alMfpku2/1xOUU54/dspW/h/K34/1v4FpdqUpM5zuAgAAAAASUVORK5CYII=""",
    # 16x16
    """iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAACdUlEQVR42nWSTUtUYRiG7+c575nTzHhs1KIxW5ilMUgGBRVBoWlQ
tCkNql2UW1v0A8JWRas2BVGbFhEEQYvSTajRBxZZm4pBiRA1zclxcpwz5+t9nxYZ0aJrc3Nf64s2b83h/xCImIhYGw0xACmAAAEA
YhAAEQ2CgcUiYoz2vSAKQtetYSsB0ZZbv1EIYJa4KnFo4piTJI4t5ZAVO6nUjtbWU2dOz//0S4vflG0riIBIQj/RmEvv7HLqsv6X
Ubt2psysPnnXLl/pO955ewrLIx+VRICjwCxRNbFlj3voPOlKuFqIGw/ui6b89nWPph/Hy8uPZ+TmqwWuLAlbIlCiY9g13HrEn8mv
PL9FynEOnPtBxd5sX3JbYVPPyYGbw4nqEkxEIEAUTETpJtLs50ehvfqegdKnkSl/buPFS2cvDQ7efzv/8KryvpNtk7IhokAkBnHV
l8hLtp/wZvJ67r1XUze/WByeCKae3ahvWeK6/mhhojL5RjlpBitTXQqKBdPYGYcS5J9EcdSW6xgvuM/vXs8elUzvzsgrWm5WdAgi
BbIoLseFj5Rprs5OpFqOOYhm1fb8vTuZjjLtOhR8/iBhRWVbmZWIWG6mgdiCN7daLG473J+pocWFol5ZNuFrZ1/OFFYqL6eNvdfL
D1FQJmLLrdtA0AHcXPeFrv1NL54O6doOgk/W+mAyqoy9i+09Evw0X8c4kQSgCDAG7LZ1724YenB3VRrS/qwBkcqSlBhaz40jLKmk
K2KImBqbdwggBnHoi5VQDKNjgAAww1IKRoPt370RsSJigsCClUoTICKwbQCAQAgQWNZauAAA9feIyG/3Z9cq/pdfh9I2lG2t1BQA
AAAASUVORK5CYII=""",
)


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    FileDiffUI(root).run()


if __name__ == "__main__":
    main()
