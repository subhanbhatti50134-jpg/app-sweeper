"""Graphical desktop app for the Linux Uninstaller (Tkinter, stdlib only)."""

import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from uninstaller import __version__
from uninstaller.backends import get_available_backends
from uninstaller.backends.base import InstalledPackage, LeftoverItem
from uninstaller.core.cleaner import Cleaner
from uninstaller.core.scanner import LeftoverScanner
from uninstaller.core.uninstaller import Uninstaller
from uninstaller.utils.helpers import human_size

# ----------------------------------------------------------------------
# Palette
# ----------------------------------------------------------------------
BG = "#16181d"
PANEL = "#1b1e25"
PANEL2 = "#23272f"
SIDEBAR = "#101216"
LINE = "#2b3038"
FG = "#e7eaee"
MUTED = "#98a0aa"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2f6fe0"
DANGER = "#e05252"
DANGER_HOVER = "#c93c3c"
OK = "#2ea55f"
WARN = "#d99a2b"


def _icon_path() -> Optional[str]:
    here = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
    return str(here) if here.exists() else None


# ======================================================================
# Custom modal dialogs
# ======================================================================
class Dialog(tk.Toplevel):
    """Modal dark-styled dialog."""

    def __init__(self, parent: tk.Tk, title: str, message: str,
                 buttons: List[tuple], body_widget: Optional[Callable] = None,
                 width: int = 520):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        self.resizable(False, False)
        self.transient(parent)
        self.result: Any = None

        frame = tk.Frame(self, bg=PANEL, padx=22, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=title, font=("Sans", 14, "bold"),
                 bg=PANEL, fg=FG, anchor="w").pack(fill="x")
        tk.Frame(frame, bg=LINE, height=1).pack(fill="x", pady=(10, 12))

        if message:
            tk.Label(frame, text=message, font=("Sans", 11), bg=PANEL, fg=MUTED,
                     wraplength=width - 60, justify="left", anchor="w"
                     ).pack(fill="x", pady=(0, 8))

        if body_widget:
            body_widget(frame)

        btn_row = tk.Frame(frame, bg=PANEL)
        btn_row.pack(fill="x", pady=(16, 0))
        for text, style, cmd in reversed(buttons):
            b = _button(btn_row, text, style, lambda c=cmd: self._click(c))
            b.pack(side="right", padx=(8, 0))

        self.bind("<Escape>", lambda e: self._click(None))
        self.update_idletasks()
        self._center(parent)
        self.deiconify()
        self.grab_set()
        self.focus_set()

    def _click(self, value: Any) -> None:
        self.result = value
        self.grab_release()
        self.destroy()

    def _center(self, parent: tk.Tk) -> None:
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
            self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass


def _button(parent: tk.Widget, text: str, style: str,
            command: Callable) -> tk.Button:
    """Flat modern button. style: primary | danger | ghost."""
    if style == "primary":
        bg, fg, active = ACCENT, "#ffffff", ACCENT_HOVER
    elif style == "danger":
        bg, fg, active = DANGER, "#ffffff", DANGER_HOVER
    else:
        bg, fg, active = PANEL2, FG, LINE
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                     activebackground=active, activeforeground=fg,
                     relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
                     font=("Sans", 10, "bold"))


# ======================================================================
# Main application
# ======================================================================
class UninstallerApp(tk.Tk):
    def __init__(self, dry_run: bool = False, manager: Optional[str] = None):
        super().__init__()
        self.dry_run = dry_run
        self.forced_manager = manager
        self.title("Linux Uninstaller")
        self.geometry("1180x760")
        self.minsize(960, 620)
        self.configure(bg=BG)

        icon = _icon_path()
        if icon:
            try:
                self.iconphoto(True, tk.PhotoImage(file=icon))
            except tk.TclError:
                pass

        self._pkg_rows: Dict[str, InstalledPackage] = {}   # tree item id -> pkg
        self._leftovers: List[LeftoverItem] = []
        self._orphan_data: Dict[str, List[LeftoverItem]] = {}
        self._clean_sizes: Dict[str, int] = {}
        self._reclaimed = 0
        self._busy = False
        self._scan_job: Optional[str] = None
        self._backends = get_available_backends()
        if manager:
            self._backends = [b for b in self._backends if b.name == manager]

        self._build_fonts()
        self._build_styles()
        self._build_layout()
        self._show_page("apps")
        self.after(200, self._initial_load)

    # ------------------------------------------------------------------
    def _build_fonts(self) -> None:
        f = tkfont.nametofont("TkDefaultFont")
        family = f.actual("family") or "Sans"
        self.f_title = tkfont.Font(family=family, size=17, weight="bold")
        self.f_head = tkfont.Font(family=family, size=12, weight="bold")
        self.f_body = tkfont.Font(family=family, size=10)
        self.f_small = tkfont.Font(family=family, size=9)
        self.f_mono = tkfont.Font(family="Monospace", size=9)

    def _build_styles(self) -> None:
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL2,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                    troughcolor=PANEL, font=self.f_body)
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("Panel.TLabel", background=PANEL, foreground=FG)
        s.configure("Title.TLabel", background=BG, foreground=FG, font=self.f_title)
        s.configure("Head.TLabel", background=PANEL, foreground=FG, font=self.f_head)
        s.configure("TButton", background=PANEL2, foreground=FG,
                    focuscolor=PANEL2, padding=(14, 7))
        s.map("TButton", background=[("active", LINE)])
        s.configure("TEntry", fieldbackground=PANEL2, foreground=FG,
                    insertcolor=FG, padding=6)
        s.map("TEntry", fieldbackground=[("focus", "#2a2f38")])
        s.configure("TCombobox", fieldbackground=PANEL2, foreground=FG,
                    background=PANEL2, padding=5, arrowcolor=FG)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL2)],
              foreground=[("readonly", FG)])
        # Treeview
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                    foreground=FG, rowheight=26, borderwidth=0)
        s.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                    relief="flat", padding=(8, 6), font=self.f_small)
        s.map("Treeview.Heading", background=[("active", LINE)])
        s.map("Treeview", background=[("selected", "#2a3d5c")],
              foreground=[("selected", "#ffffff")])
        # Progressbar
        s.configure("TPanel.Horizontal.TProgressbar", troughcolor=PANEL2,
                    background=ACCENT, thickness=4)

    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        # Sidebar
        self.sidebar = tk.Frame(self, bg=SIDEBAR, width=196)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        logo_row = tk.Frame(self.sidebar, bg=SIDEBAR)
        logo_row.pack(fill="x", pady=(18, 20), padx=14)
        icon = _icon_path()
        if icon:
            try:
                img = tk.PhotoImage(file=icon).subsample(10, 10)  # ~51px
                lbl = tk.Label(logo_row, image=img, bg=SIDEBAR)
                lbl.image = img  # type: ignore[attr-defined]
                lbl.pack(side="left")
            except tk.TclError:
                pass
        tk.Label(logo_row, text="Uninstaller", font=("Sans", 11, "bold"),
                 bg=SIDEBAR, fg=FG).pack(side="left", padx=(9, 0))

        self.nav_buttons: Dict[str, tk.Button] = {}
        nav = [("apps", "  Apps"), ("scan", "  Orphan Scan"),
               ("cleaner", "  Cleaner"), ("about", "  About")]
        for key, label in nav:
            b = tk.Button(self.sidebar, text=label, anchor="w", bd=0,
                          relief="flat", font=self.f_body, cursor="hand2",
                          bg=SIDEBAR, fg=MUTED, activebackground=PANEL2,
                          activeforeground=FG, padx=20, pady=11,
                          command=lambda k=key: self._show_page(k))
            b.pack(fill="x")
            b.bind("<Enter>", lambda e, w=b: w.configure(fg=FG) if
                   w.cget("fg") == MUTED else None)
            b.bind("<Leave>", lambda e, w=b, k=key: w.configure(
                fg=ACCENT if self._page == k else MUTED))
            self.nav_buttons[key] = b

        if self.dry_run:
            tk.Label(self.sidebar, text="DRY-RUN MODE", font=self.f_small,
                     bg=SIDEBAR, fg=WARN).pack(side="bottom", pady=14)

        # Content
        self.content = tk.Frame(self, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        # Status bar
        status = tk.Frame(self, bg=PANEL, height=30)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        self.status_var = tk.StringVar(value="Ready")
        self.reclaim_var = tk.StringVar(value="Freed: 0 B")
        tk.Label(status, textvariable=self.status_var, bg=PANEL, fg=MUTED,
                 font=self.f_small, anchor="w").pack(side="left", padx=14)
        tk.Label(status, textvariable=self.reclaim_var, bg=PANEL, fg=OK,
                 font=self.f_small, anchor="e").pack(side="right", padx=14)

        self.progress = ttk.Progressbar(self, mode="indeterminate",
                                        style="TPanel.Horizontal.TProgressbar")

        self.pages: Dict[str, tk.Frame] = {}

    # ------------------------------------------------------------------
    def _show_page(self, name: str) -> None:
        self._page = name
        for k, b in self.nav_buttons.items():
            b.configure(fg=ACCENT if k == name else MUTED,
                        bg=PANEL2 if k == name else SIDEBAR)
        for w in self.content.winfo_children():
            w.pack_forget()
        builder = {
            "apps": self._build_apps_page,
            "scan": self._build_scan_page,
            "cleaner": self._build_cleaner_page,
            "about": self._build_about_page,
        }[name]
        if name not in self.pages:
            self.pages[name] = builder(self.content)
        self.pages[name].pack(fill="both", expand=True, padx=22, pady=20)

    # ==================================================================
    # Apps page
    # ==================================================================
    def _build_apps_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=BG)

        # Toolbar
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(0, 12))
        tk.Label(bar, text="Installed Applications", font=self.f_title,
                 bg=BG, fg=FG).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._filter_pkg_list())
        e = ttk.Entry(bar, textvariable=self.search_var, width=26)
        e.insert(0, "")
        e.pack(side="right", padx=(10, 0))
        e.configure(takefocus=True)

        self.mgr_var = tk.StringVar(value="All managers")
        mgrs = ["All managers"] + [b.display_name for b in self._backends]
        cb = ttk.Combobox(bar, textvariable=self.mgr_var, values=mgrs,
                          state="readonly", width=22)
        cb.pack(side="right", padx=(0, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._filter_pkg_list())

        _button(bar, "⟳ Refresh", "ghost", self._initial_load).pack(side="right")

        # Split: list (top) + details (bottom)
        paned = tk.PanedWindow(page, orient="vertical", bd=0, sashwidth=5,
                               sashrelief="flat", bg=LINE)
        paned.pack(fill="both", expand=True)

        # --- package tree ---
        list_frame = tk.Frame(paned, bg=PANEL)
        cols = ("name", "version", "size", "manager", "desc")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                 selectmode="browse")
        headings = {"name": ("Application", 260), "version": ("Version", 130),
                    "size": ("Size", 90), "manager": ("Manager", 110),
                    "desc": ("Description", 330)}
        for c, (txt, w) in headings.items():
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, minwidth=60,
                             anchor="w" if c in ("name", "desc", "manager") else "e")
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_pkg_select())
        paned.add(list_frame, minsize=180)

        # --- details ---
        det = tk.Frame(paned, bg=PANEL)
        head = tk.Frame(det, bg=PANEL)
        head.pack(fill="x", padx=14, pady=(12, 4))
        self.sel_var = tk.StringVar(value="Select an application to inspect leftovers")
        tk.Label(head, textvariable=self.sel_var, font=self.f_head,
                 bg=PANEL, fg=FG).pack(side="left")
        self.leftover_info = tk.StringVar(value="")
        tk.Label(head, textvariable=self.leftover_info, font=self.f_small,
                 bg=PANEL, fg=WARN).pack(side="right")

        inner = tk.Frame(det, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        self.lo_tree = ttk.Treeview(inner, columns=("kind", "path", "size"),
                                    show="headings", height=6)
        for c, (t, w, a) in {"kind": ("Type", 80, "w"),
                             "path": ("Leftover path", 620, "w"),
                             "size": ("Size", 90, "e")}.items():
            self.lo_tree.heading(c, text=t)
            self.lo_tree.column(c, width=w, anchor=a, minwidth=50)
        lvsb = ttk.Scrollbar(inner, orient="vertical", command=self.lo_tree.yview)
        self.lo_tree.configure(yscrollcommand=lvsb.set)
        self.lo_tree.pack(side="left", fill="both", expand=True)
        lvsb.pack(side="right", fill="y")

        btn_row = tk.Frame(det, bg=PANEL)
        btn_row.pack(fill="x", padx=14, pady=(4, 14))
        self.uninstall_btn = _button(btn_row, "🗑  Uninstall & Clean", "danger",
                                     self._do_uninstall)
        self.uninstall_btn.pack(side="right")
        self.uninstall_btn.configure(state="disabled")
        tk.Label(btn_row, text="Uninstall removes the package AND its leftover "
                               "cache/config/data files.",
                 font=self.f_small, bg=PANEL, fg=MUTED).pack(side="left")

        paned.add(det, minsize=210)
        paned.sash_place(0, 0, 380)  # Tk 9 removed sashpos()
        return page

    # ------------------------------------------------------------------
    def _initial_load(self) -> None:
        if self._busy:
            return
        if not self._backends:
            self.status_var.set("No supported package manager found on this system")
            return
        self._set_busy(True, "Loading installed packages…")

        def work():
            pkgs: List[InstalledPackage] = []
            for b in self._backends:
                try:
                    pkgs.extend(b.list_packages(include_orphans=False))
                except Exception:
                    continue
            pkgs.sort(key=lambda p: p.name.lower())
            return pkgs

        def done(pkgs):
            self._all_pkgs = pkgs
            self._set_busy(False, f"{len(pkgs)} applications installed")
            self._filter_pkg_list()

        self._run(work, done)

    def _filter_pkg_list(self) -> None:
        if not hasattr(self, "_all_pkgs"):
            return
        q = self.search_var.get().strip().lower()
        mgr_sel = self.mgr_var.get()
        backend_names = {b.display_name: b.name for b in self._backends}
        self.tree.delete(*self.tree.get_children())
        self._pkg_rows.clear()
        count = 0
        for p in self._all_pkgs:
            if q and q not in p.name.lower() and q not in p.description.lower():
                continue
            if mgr_sel != "All managers" and \
                    backend_names.get(mgr_sel) != p.manager:
                continue
            iid = self.tree.insert("", "end", values=(
                p.name, p.version, p.display_size() if p.size else "",
                p.manager, p.description[:70] if p.description else ""))
            self._pkg_rows[iid] = p
            count += 1
        self.status_var.set(f"{count} application(s) shown")

    def _on_pkg_select(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        pkg = self._pkg_rows.get(sel[0])
        if not pkg:
            return
        self.sel_var.set(f"{pkg.name}  •  {pkg.version}  •  via {pkg.manager}")
        self.leftover_info.set("Scanning leftovers…")
        self.uninstall_btn.configure(state="disabled")
        self._leftovers = []
        for i in self.lo_tree.get_children():
            self.lo_tree.delete(i)

        # Debounce rapid selection changes
        job = f"{pkg.manager}:{pkg.name}"
        self._scan_job = job

        def work():
            return LeftoverScanner().scan_for_app(pkg.name)

        def done(items):
            if self._scan_job != job:
                return  # user moved on
            self._leftovers = items
            total = sum(i.size for i in items)
            if items:
                self.leftover_info.set(
                    f"{len(items)} leftover item(s) • {human_size(total)}")
                for it in items:
                    self.lo_tree.insert("", "end", values=(
                        it.kind, it.path, it.display_size()))
            else:
                self.leftover_info.set("No leftovers found ✓")
            self.uninstall_btn.configure(state="normal")

        self._run(work, done)

    def _do_uninstall(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        pkg = self._pkg_rows.get(sel[0])
        if not pkg:
            return
        items = list(self._leftovers)
        total = sum(i.size for i in items)

        if self.dry_run:
            messagebox.showinfo("Dry-run", "DRY-RUN mode: nothing will be changed.",
                                parent=self)
            return

        def body(f):
            if items:
                tk.Label(f, text=f"Will also remove {len(items)} leftover item(s) "
                                 f"({human_size(total)}):",
                         font=self.f_small, bg=PANEL, fg=WARN, anchor="w"
                         ).pack(fill="x", pady=(4, 6))
                box = tk.Frame(f, bg=PANEL2, height=150)
                box.pack(fill="x")
                box.pack_propagate(False)
                t = tk.Text(box, bg=PANEL2, fg=FG, bd=0, font=self.f_mono,
                            relief="flat", padx=8, pady=6)
                t.pack(fill="both", expand=True)
                for it in items[:40]:
                    t.insert("end", f"  {it.path}  ({it.display_size()})\n")
                if len(items) > 40:
                    t.insert("end", f"  … and {len(items) - 40} more\n")
                t.configure(state="disabled")
            else:
                tk.Label(f, text="No leftover files were found for this app.",
                         font=self.f_small, bg=PANEL, fg=MUTED, anchor="w"
                         ).pack(fill="x", pady=(4, 6))

        dlg = Dialog(
            self, "Confirm Uninstall",
            f"Uninstall “{pkg.name}” via {pkg.manager}?",
            buttons=[("Cancel", "ghost", None),
                     ("Uninstall", "danger", "ok")],
            body_widget=body,
        )
        self.wait_window(dlg)
        if dlg.result != "ok":
            return

        self._set_busy(True, f"Uninstalling {pkg.name}…")

        def work():
            un = Uninstaller(backend_name=pkg.manager, force=True, verbose=False)
            return un.uninstall(pkg.name, leftovers=items)

        def done(result):
            self._set_busy(False, "")
            if result.success:
                self._reclaimed += result.leftovers_bytes
                self.reclaim_var.set(f"Freed: {human_size(self._reclaimed)}")
                self._all_pkgs = [p for p in self._all_pkgs
                                  if not (p.name == pkg.name and
                                          p.manager == pkg.manager)]
                self._filter_pkg_list()
                self.sel_var.set("Select an application to inspect leftovers")
                self.leftover_info.set("")
                self.uninstall_btn.configure(state="disabled")
                for i in self.lo_tree.get_children():
                    self.lo_tree.delete(i)
                extra = ""
                if result.leftovers_removed:
                    extra = (f"\nCleaned {len(result.leftovers_removed)} leftover "
                             f"item(s), freed {human_size(result.leftovers_bytes)}.")
                self.status_var.set(f"Uninstalled {pkg.name}")
                messagebox.showinfo("Success", f"{result.message}{extra}",
                                    parent=self)
            else:
                messagebox.showerror("Uninstall failed", result.message,
                                     parent=self)

        self._run(work, done)

    # ==================================================================
    # Orphan scan page
    # ==================================================================
    def _build_scan_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=BG)
        bar = tk.Frame(page, bg=BG)
        bar.pack(fill="x", pady=(0, 12))
        tk.Label(bar, text="Orphaned App Data", font=self.f_title,
                 bg=BG, fg=FG).pack(side="left")
        _button(bar, "🔍  Scan Now", "primary", self._run_orphan_scan
                ).pack(side="right")
        _button(bar, "Clean Selected", "danger", self._clean_orphans
                ).pack(side="right", padx=(0, 10))

        self.scan_info = tk.StringVar(
            value="Find app data left behind by apps that are no longer installed.")
        tk.Label(page, textvariable=self.scan_info, font=self.f_small,
                 bg=BG, fg=MUTED, anchor="w").pack(fill="x", pady=(0, 8))

        split = tk.PanedWindow(page, orient="horizontal", bd=0, sashwidth=5,
                               sashrelief="flat", bg=LINE)
        split.pack(fill="both", expand=True)

        left = tk.Frame(split, bg=PANEL)
        cols = ("name", "size", "items")
        self.orphan_tree = ttk.Treeview(left, columns=cols, show="headings",
                                        selectmode="extended")
        for c, (t, w, a) in {"name": ("App / folder", 240, "w"),
                             "size": ("Size", 100, "e"),
                             "items": ("Files", 70, "e")}.items():
            self.orphan_tree.heading(c, text=t)
            self.orphan_tree.column(c, width=w, anchor=a, minwidth=60)
        sb = ttk.Scrollbar(left, orient="vertical",
                           command=self.orphan_tree.yview)
        self.orphan_tree.configure(yscrollcommand=sb.set)
        self.orphan_tree.pack(side="left", fill="both", expand=True,
                              padx=(8, 0), pady=8)
        sb.pack(side="right", fill="y", pady=8, padx=(0, 8))
        self.orphan_tree.bind("<<TreeviewSelect>>", lambda e: self._on_orphan_sel())
        split.add(left, minsize=320)

        right = tk.Frame(split, bg=PANEL)
        tk.Label(right, text="Paths", font=self.f_head, bg=PANEL, fg=FG
                 ).pack(anchor="w", padx=14, pady=(12, 6))
        box = tk.Frame(right, bg=PANEL)
        box.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.orphan_paths = tk.Text(box, bg=PANEL2, fg=FG, bd=0,
                                    font=self.f_mono, relief="flat",
                                    padx=10, pady=8, wrap="none")
        ps = ttk.Scrollbar(box, orient="vertical",
                           command=self.orphan_paths.yview)
        self.orphan_paths.configure(yscrollcommand=ps.set)
        self.orphan_paths.pack(side="left", fill="both", expand=True)
        ps.pack(side="right", fill="y")
        self.orphan_paths.configure(state="disabled")
        split.add(right, minsize=260)
        return page

    def _run_orphan_scan(self) -> None:
        if self._busy:
            return
        self._set_busy(True, "Scanning for orphaned data…")
        self.scan_info.set("Scanning (this can take a minute)…")

        def work():
            return LeftoverScanner().scan_all_leftovers()

        def done(results):
            self._orphan_data = results
            self._set_busy(False, "")
            self.orphan_tree.delete(*self.orphan_tree.get_children())
            total = sum(sum(i.size for i in v) for v in results.values())
            if not results:
                self.scan_info.set("✓ No orphaned app data found.")
                return
            for name, items in sorted(results.items(),
                                      key=lambda kv: sum(i.size for i in kv[1]),
                                      reverse=True):
                size = sum(i.size for i in items)
                self.orphan_tree.insert("", "end", iid=name,
                                        values=(name, human_size(size),
                                                len(items)))
            self.scan_info.set(
                f"Found {len(results)} orphaned app(s), total {human_size(total)}. "
                f"Select rows and click Clean Selected.")

        self._run(work, done)

    def _on_orphan_sel(self) -> None:
        sel = self.orphan_tree.selection()
        self.orphan_paths.configure(state="normal")
        self.orphan_paths.delete("1.0", "end")
        for name in sel:
            for it in self._orphan_data.get(name, []):
                self.orphan_paths.insert(
                    "end", f"{it.path}\n    ({it.display_size()}, {it.kind})\n")
        self.orphan_paths.configure(state="disabled")

    def _clean_orphans(self) -> None:
        sel = self.orphan_tree.selection()
        if not sel:
            messagebox.showinfo("Nothing selected",
                                "Select one or more orphaned apps first.",
                                parent=self)
            return
        if self.dry_run:
            messagebox.showinfo("Dry-run", "DRY-RUN mode: nothing will be changed.",
                                parent=self)
            return
        total = sum(sum(i.size for i in self._orphan_data.get(n, []))
                    for n in sel)
        names = ", ".join(sel[:4]) + ("…" if len(sel) > 4 else "")
        if not messagebox.askyesno(
                "Confirm cleanup",
                f"Delete ALL leftover data for {len(sel)} app(s)?\n\n"
                f"{names}\n\nTotal: {human_size(total)}\n\n"
                f"This cannot be undone.", parent=self):
            return
        items = [i for n in sel for i in self._orphan_data.get(n, [])]
        self._set_busy(True, f"Cleaning {len(sel)} app(s)…")

        def work():
            c = Cleaner(dry_run=False, force=True)
            return c.remove_items(items, ask=False)

        def done(res):
            removed, freed, errors = res
            self._set_busy(False, "")
            self._reclaimed += freed
            self.reclaim_var.set(f"Freed: {human_size(self._reclaimed)}")
            for n in sel:
                self._orphan_data.pop(n, None)
                if self.orphan_tree.exists(n):
                    self.orphan_tree.delete(n)
            msg = f"Removed {removed} item(s), freed {human_size(freed)}."
            if errors:
                msg += f"\n\n{len(errors)} error(s):\n" + "\n".join(errors[:5])
            self.scan_info.set(msg)
            messagebox.showinfo("Cleanup complete", msg, parent=self)

        self._run(work, done)

    # ==================================================================
    # Cleaner page
    # ==================================================================
    def _build_cleaner_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=BG)
        tk.Label(page, text="System Cleaner", font=self.f_title,
                 bg=BG, fg=FG).pack(anchor="w", pady=(0, 4))
        tk.Label(page, text="Free up space by clearing caches, temp files and trash.",
                 font=self.f_small, bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 16))

        grid = tk.Frame(page, bg=BG)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure((0, 1), weight=1, uniform="c")
        grid.rowconfigure((0, 1), weight=1, uniform="r")

        self.clean_cards: Dict[str, "tk.StringVar"] = {}
        cards = [
            ("cache", "🗂  User Cache", "~/.cache",
             "Browser, app and tool caches stored in your home directory."),
            ("trash", "🗑  Trash", "~/.local/share/Trash",
             "Files you deleted that are still taking up space."),
            ("temp", "⏳  Temp Files", "/tmp & ~/.cache",
             "Stale temporary files older than one hour."),
            ("syscache", "📦  Package Caches", "dnf / apt / flatpak",
             "Downloaded package metadata and unused runtimes."),
        ]
        for i, (key, title, sub, desc) in enumerate(cards):
            card = tk.Frame(grid, bg=PANEL, highlightbackground=LINE,
                            highlightthickness=1, padx=16, pady=14)
            card.grid(row=i // 2, column=i % 2, sticky="nsew", padx=8, pady=8)
            tk.Label(card, text=title, font=self.f_head, bg=PANEL, fg=FG
                     ).pack(anchor="w")
            tk.Label(card, text=sub, font=self.f_mono, bg=PANEL, fg=MUTED
                     ).pack(anchor="w", pady=(2, 6))
            tk.Label(card, text=desc, font=self.f_small, bg=PANEL, fg=MUTED,
                     wraplength=380, justify="left").pack(anchor="w", fill="x")
            row = tk.Frame(card, bg=PANEL)
            row.pack(fill="x", pady=(12, 0))
            size_var = tk.StringVar(value="calculating…")
            tk.Label(row, textvariable=size_var, font=self.f_body, bg=PANEL,
                     fg=WARN).pack(side="left")
            _button(row, "Clean", "ghost",
                    lambda k=key: self._clean_kind(k)).pack(side="right")
            self.clean_cards[key] = size_var  # tk.StringVar

        self.clean_total = tk.StringVar(value="")
        tk.Label(page, textvariable=self.clean_total, font=self.f_small,
                 bg=BG, fg=OK).pack(anchor="w", pady=(10, 0))
        self.after(300, self._compute_clean_sizes)
        return page

    def _compute_clean_sizes(self) -> None:
        if self._busy:
            self.after(800, self._compute_clean_sizes)
            return

        def dir_size(p: Path) -> int:
            if not p.exists():
                return 0
            total = 0
            try:
                if p.is_file():
                    return p.stat().st_size
                for f in p.rglob("*"):
                    try:
                        if f.is_file() and not f.is_symlink():
                            total += f.stat().st_size
                    except OSError:
                        pass
            except OSError:
                pass
            return total

        def work():
            home = Path.home()
            now = time.time()
            sizes = {}
            sizes["cache"] = dir_size(home / ".cache")
            sizes["trash"] = dir_size(home / ".local/share/Trash" / "files")
            temp = 0
            for d in (Path("/tmp"), home / ".cache"):
                try:
                    for e in d.iterdir():
                        try:
                            if now - e.stat().st_mtime > 3600:
                                temp += dir_size(e)
                        except OSError:
                            pass
                except OSError:
                    pass
            sizes["temp"] = temp
            sizes["syscache"] = 0  # shown as "--"
            return sizes

        def done(sizes):
            self._clean_sizes = sizes
            for k, v in sizes.items():
                if k in self.clean_cards:
                    txt = human_size(v) if v else "0 B"
                    self.clean_cards[k].set(txt)

        self._run(work, done)

    def _clean_kind(self, kind: str) -> None:
        if self.dry_run:
            messagebox.showinfo("Dry-run", "DRY-RUN mode: nothing will be changed.",
                                parent=self)
            return
        labels = {"cache": "user cache (~/.cache)",
                  "trash": "the trash",
                  "temp": "stale temp files",
                  "syscache": "package manager caches"}
        if not messagebox.askyesno("Confirm",
                                   f"Clean {labels.get(kind, kind)}?",
                                   parent=self):
            return
        self._set_busy(True, f"Cleaning {labels.get(kind, kind)}…")

        def work():
            c = Cleaner(dry_run=False, force=True)
            if kind == "cache":
                return c.clean_cache(ask=False)
            if kind == "trash":
                return c.empty_trash(ask=False)
            if kind == "temp":
                return c.clean_temp(ask=False)
            # syscache: run package manager cache commands
            from uninstaller.cli import _clean_system_caches
            freed0 = 0
            _clean_system_caches(False)
            return (0, freed0, [])

        def done(res):
            removed, freed, errors = res
            self._set_busy(False, "")
            self._reclaimed += freed
            self.reclaim_var.set(f"Freed: {human_size(self._reclaimed)}")
            msg = (f"Removed {removed} item(s), freed {human_size(freed)}."
                   if kind != "syscache" else "Package caches cleared.")
            if errors:
                msg += f"\n{len(errors)} error(s)"
            self.clean_total.set(msg)
            self._compute_clean_sizes()

        self._run(work, done)

    # ==================================================================
    # About page
    # ==================================================================
    def _build_about_page(self, parent: tk.Frame) -> tk.Frame:
        page = tk.Frame(parent, bg=BG)
        tk.Label(page, text="Linux Uninstaller", font=self.f_title,
                 bg=BG, fg=FG).pack(anchor="w", pady=(0, 2))
        tk.Label(page, text=f"Version {__version__}", font=self.f_small,
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(0, 16))

        text = (
            "Uninstall applications and remove the leftover cache, config, "
            "and data files that package managers leave behind.\n\n"
            "Features\n"
            "  •  Uninstall + leftover cleanup in one step\n"
            "  •  Orphaned data scanner across ~/.config, ~/.cache, ~/.local/share\n"
            "  •  Cache / temp / trash / package-cache cleaner\n"
            "  •  Dry-run preview and confirmation on every destructive action\n"
            "  •  Zero dependencies — Python standard library only\n\n"
            "Detected package managers"
        )
        tk.Label(page, text=text, font=self.f_body, bg=BG, fg=FG,
                 justify="left", anchor="nw").pack(anchor="w", fill="x")

        box = tk.Frame(page, bg=PANEL, highlightbackground=LINE,
                       highlightthickness=1)
        box.pack(fill="x", pady=(10, 0))
        for b in get_available_backends():
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill="x", padx=14, pady=7)
            tk.Label(row, text="●", bg=PANEL, fg=OK).pack(side="left")
            tk.Label(row, text=f"{b.name}", font=self.f_mono, bg=PANEL,
                     fg=FG).pack(side="left", padx=(8, 0))
            tk.Label(row, text=b.display_name, font=self.f_small, bg=PANEL,
                     fg=MUTED).pack(side="left", padx=(14, 0))

        note = ("Run from the terminal for the CLI:  uninstaller --help\n"
                "Uninstall this tool with:  ./uninstall.sh")
        tk.Label(page, text=note, font=self.f_small, bg=BG, fg=MUTED,
                 justify="left", anchor="nw").pack(anchor="w", pady=(18, 0))
        return page

    # ==================================================================
    # Utilities
    # ==================================================================
    def _run(self, work: Callable, done: Callable) -> None:
        """Run *work* in a daemon thread; deliver its result on the UI thread."""

        def runner():
            try:
                result = work()
                self.after(0, lambda r=result: done(r))
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                # Bind now: Python deletes `exc` when the except block exits
                self.after(0, lambda e=exc: self._on_error(e))

        threading.Thread(target=runner, daemon=True).start()

    def _on_error(self, exc: Exception) -> None:
        self._set_busy(False, "")
        messagebox.showerror("Error", f"{type(exc).__name__}: {exc}", parent=self)

    def _set_busy(self, busy: bool, msg: str) -> None:
        self._busy = busy
        if msg:
            self.status_var.set(msg)
        if busy:
            self.progress.pack(fill="x", side="bottom")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()


def run_gui(dry_run: bool = False, manager: Optional[str] = None) -> int:
    """Launch the GUI. Returns an exit code."""
    app = UninstallerApp(dry_run=dry_run, manager=manager)
    app.mainloop()
    return 0
