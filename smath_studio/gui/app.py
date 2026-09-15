"""Main application window for SMath Studio GUI."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional

from ..parser import parse_file, Worksheet
from ..writer import write_file
from .canvas import WorksheetCanvas
from .toolbar import StandardToolbar, MathPanelContainer
from .dialogs import AboutDialog, OptionsDialog, InsertFunctionDialog


class SMathApp:
    """Main SMath Studio application window."""

    def __init__(self, file_path: Optional[str] = None):
        self._root = tk.Tk()
        self._root.title("SMath Studio - [Untitled]")
        self._root.geometry("1024x768")
        self._root.minsize(640, 480)

        try:
            icon_path = Path(__file__).parent / "icon.png"
            if icon_path.exists():
                icon = tk.PhotoImage(file=str(icon_path))
                self._root.iconphoto(False, icon)
                self._icon_ref = icon
        except Exception:
            pass

        self._current_file: Optional[Path] = None
        self._worksheet: Optional[Worksheet] = None
        self._modified = False

        # Settings for options dialog
        self._settings = {
            "precision": 4,
            "fractions": "decimal",
            "angle_units": "radians",
            "trailing_zeros": True,
            "significant_digits_mode": False,
        }

        # Apply a consistent ttk style
        self._setup_styles()

        # Build the UI
        self._build_menu_bar()
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

        # Keyboard shortcuts
        self._bind_shortcuts()

        # Protocol for window close
        self._root.protocol("WM_DELETE_WINDOW", self._on_exit)

        # Load file if provided
        if file_path is not None:
            self._root.after(100, lambda: self._open_file(file_path))

        # Start status bar update loop
        self._update_status_bar()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        """Start the tkinter main loop."""
        self._root.mainloop()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_styles(self):
        """Configure ttk styles for a clean appearance."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Toolbutton.TButton",
            padding=(4, 2),
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            font=("Segoe UI", 9),
            padding=(4, 2),
        )
        style.configure(
            "StatusSep.TLabel",
            font=("Segoe UI", 9),
            foreground="#888888",
        )

    def _build_menu_bar(self):
        """Build the menu bar matching SMath Studio's structure."""
        menubar = tk.Menu(self._root)
        self._root.config(menu=menubar)

        # --- File menu ---
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(
            label="New", accelerator="Ctrl+N", command=self._on_new
        )
        file_menu.add_command(
            label="Open...", accelerator="Ctrl+O", command=self._on_open
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Save", accelerator="Ctrl+S", command=self._on_save
        )
        file_menu.add_command(
            label="Save As...", command=self._on_save_as
        )
        file_menu.add_separator()
        file_menu.add_command(label="Print...", accelerator="Ctrl+P", command=self._on_print)
        file_menu.add_separator()
        self._recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self._recent_menu)
        self._recent_files: list[str] = []
        self._load_recent_files()
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_exit)

        # --- Edit menu ---
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(
            label="Undo", accelerator="Ctrl+Z", command=self._on_undo
        )
        edit_menu.add_command(
            label="Redo", accelerator="Ctrl+Y", command=self._on_redo
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Cut", accelerator="Ctrl+X", command=self._on_cut
        )
        edit_menu.add_command(
            label="Copy", accelerator="Ctrl+C", command=self._on_copy
        )
        edit_menu.add_command(
            label="Paste", accelerator="Ctrl+V", command=self._on_paste
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Delete", accelerator="Del", command=self._on_delete
        )

        # --- Insert menu ---
        insert_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Insert", menu=insert_menu)
        insert_menu.add_command(label="Math Region", command=self._on_insert_math)
        insert_menu.add_command(label="Text Region", command=self._on_insert_text)
        insert_menu.add_command(label="Comment", command=self._on_insert_comment)
        insert_menu.add_command(label="Plot Region", command=self._on_insert_plot)
        insert_menu.add_command(label="Matrix", accelerator="Ctrl+M", command=self._on_insert_matrix)
        insert_menu.add_command(label="Line Separator", command=self._on_insert_line)
        insert_menu.add_command(label="Area", command=self._on_insert_area)
        insert_menu.add_separator()
        insert_menu.add_command(
            label="Function...", command=self._on_insert_function
        )

        # --- View menu ---
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(
            label="Zoom In", accelerator="Ctrl++", command=lambda: self._canvas_widget._zoom_in()
        )
        view_menu.add_command(
            label="Zoom Out", accelerator="Ctrl+-", command=lambda: self._canvas_widget._zoom_out()
        )
        view_menu.add_command(
            label="Zoom 100%", accelerator="Ctrl+0", command=self._reset_zoom
        )
        view_menu.add_separator()
        self._show_grid_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="Show Grid", variable=self._show_grid_var,
            command=self._toggle_grid
        )
        self._show_margin_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="Show Margin Line", variable=self._show_margin_var,
            command=self._toggle_margin
        )
        view_menu.add_separator()
        view_menu.add_command(
            label="Regions List", command=self._show_regions_list
        )

        # --- Calculation menu ---
        calc_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Calculation", menu=calc_menu)
        calc_menu.add_command(
            label="Evaluate Selection", accelerator="F5",
            command=lambda: self._canvas_widget.evaluate_selected()
        )
        calc_menu.add_command(
            label="Recalculate All", accelerator="F9", command=self._on_recalculate
        )

        # --- Tools menu ---
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Options...", command=self._on_options)

        # --- Help menu ---
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About SMath Studio", command=self._on_about)

    def _build_toolbar(self):
        """Build the standard toolbar row."""
        toolbar_frame = ttk.Frame(self._root)
        toolbar_frame.pack(side=tk.TOP, fill=tk.X)

        commands = {
            "new": self._on_new,
            "open": self._on_open,
            "save": self._on_save,
            "print": self._on_print,
            "undo": self._on_undo,
            "redo": self._on_redo,
            "cut": self._on_cut,
            "copy": self._on_copy,
            "paste": self._on_paste,
        }
        self._toolbar = StandardToolbar(toolbar_frame, commands)
        self._toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=1)

    def _build_main_area(self):
        """Build the central area: worksheet canvas + right-side math panels."""
        main_frame = ttk.Frame(self._root)
        main_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # PanedWindow allows the user to resize the math panel
        self._paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True)

        # Worksheet canvas (center)
        self._canvas_widget = WorksheetCanvas(self._paned)
        self._canvas_widget.set_on_modified(self._on_canvas_modified)
        self._paned.add(self._canvas_widget, weight=1)

        # Math panels sidebar (right)
        self._math_panels = MathPanelContainer(
            self._paned, on_insert=self._on_symbol_insert
        )
        self._paned.add(self._math_panels, weight=0)

    def _build_status_bar(self):
        """Build the status bar at the bottom."""
        status_frame = ttk.Frame(self._root, relief=tk.SUNKEN)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._status_position = ttk.Label(
            status_frame, text="Position: 0, 0", style="Status.TLabel", width=20
        )
        self._status_position.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(status_frame, text="|", style="StatusSep.TLabel").pack(
            side=tk.LEFT, padx=4
        )

        self._status_calc = ttk.Label(
            status_frame, text="Automatic", style="Status.TLabel", width=14
        )
        self._status_calc.pack(side=tk.LEFT)

        ttk.Label(status_frame, text="|", style="StatusSep.TLabel").pack(
            side=tk.LEFT, padx=4
        )

        self._status_zoom = ttk.Label(
            status_frame, text="100%", style="Status.TLabel", width=8
        )
        self._status_zoom.pack(side=tk.LEFT)

        ttk.Label(status_frame, text="|", style="StatusSep.TLabel").pack(
            side=tk.LEFT, padx=4
        )

        self._status_info = ttk.Label(
            status_frame, text="Ready", style="Status.TLabel"
        )
        self._status_info.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _bind_shortcuts(self):
        """Bind keyboard shortcuts."""
        self._root.bind("<Control-n>", lambda e: self._on_new())
        self._root.bind("<Control-N>", lambda e: self._on_new())
        self._root.bind("<Control-o>", lambda e: self._on_open())
        self._root.bind("<Control-O>", lambda e: self._on_open())
        self._root.bind("<Control-s>", lambda e: self._on_save())
        self._root.bind("<Control-S>", lambda e: self._on_save())
        self._root.bind("<Control-z>", lambda e: self._on_undo())
        self._root.bind("<Control-Z>", lambda e: self._on_undo())
        self._root.bind("<Control-y>", lambda e: self._on_redo())
        self._root.bind("<Control-Y>", lambda e: self._on_redo())
        self._root.bind("<Control-x>", lambda e: self._safe_cut())
        self._root.bind("<Control-X>", lambda e: self._safe_cut())
        self._root.bind("<Control-c>", lambda e: self._safe_copy())
        self._root.bind("<Control-C>", lambda e: self._safe_copy())
        self._root.bind("<Control-v>", lambda e: self._safe_paste())
        self._root.bind("<Control-V>", lambda e: self._safe_paste())
        self._root.bind("<Control-p>", lambda e: self._on_print())
        self._root.bind("<Control-P>", lambda e: self._on_print())
        self._root.bind("<F5>", lambda e: self._canvas_widget.evaluate_selected())
        self._root.bind("<F9>", lambda e: self._on_recalculate())
        self._root.bind("<Control-plus>", lambda e: self._canvas_widget._zoom_in())
        self._root.bind("<Control-equal>", lambda e: self._canvas_widget._zoom_in())
        self._root.bind("<Control-minus>", lambda e: self._canvas_widget._zoom_out())
        self._root.bind("<Control-0>", lambda e: self._reset_zoom())
        self._root.bind("<Control-m>", lambda e: self._on_insert_matrix())
        self._root.bind("<Control-M>", lambda e: self._on_insert_matrix())

    # ------------------------------------------------------------------
    # Status bar update
    # ------------------------------------------------------------------

    def _update_status_bar(self):
        """Periodically update status bar with cursor position."""
        try:
            cx, cy = self._canvas_widget.get_cursor_position()
            self._status_position.config(text=f"Position: {cx}, {cy}")
            zoom = self._canvas_widget.get_zoom_percent()
            self._status_zoom.config(text=f"{zoom}%")
        except Exception:
            pass
        self._root.after(250, self._update_status_bar)

    # ------------------------------------------------------------------
    # Title management
    # ------------------------------------------------------------------

    def _update_title(self):
        """Update the window title to reflect the current file."""
        if self._current_file:
            name = self._current_file.name
        else:
            name = "Untitled"
        mod = " *" if self._modified else ""
        self._root.title(f"SMath Studio - [{name}]{mod}")

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _on_new(self):
        """Create a new empty worksheet."""
        if self._modified:
            answer = messagebox.askyesnocancel(
                "Save Changes",
                "Do you want to save changes to the current worksheet?",
            )
            if answer is None:
                return  # Cancel
            if answer:
                self._on_save()

        self._canvas_widget.clear()
        self._worksheet = Worksheet()
        self._canvas_widget.load_worksheet(self._worksheet)
        self._current_file = None
        self._modified = False
        self._update_title()
        self._status_info.config(text="New worksheet created")

    def _on_open(self):
        """Open a .sm file."""
        path = filedialog.askopenfilename(
            title="Open Worksheet",
            filetypes=[
                ("SMath Worksheets", "*.sm"),
                ("All Files", "*.*"),
            ],
            parent=self._root,
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str):
        """Load and render a worksheet file."""
        try:
            ws = parse_file(path)
            self._worksheet = ws
            self._current_file = Path(path)
            self._modified = False

            # Sync settings
            self._settings["precision"] = ws.settings.calculation.precision
            self._settings["fractions"] = ws.settings.calculation.fractions
            self._settings["trailing_zeros"] = ws.settings.calculation.trailing_zeros
            self._settings["significant_digits_mode"] = (
                ws.settings.calculation.significant_digits_mode
            )

            self._canvas_widget.load_worksheet(ws)
            self._add_recent_file(str(path))
            self._update_title()
            n_regions = len(ws.regions)
            self._status_info.config(
                text=f"Loaded {self._current_file.name} ({n_regions} regions)"
            )
        except Exception as ex:
            messagebox.showerror(
                "Error Opening File",
                f"Could not open {path}:\n\n{ex}",
                parent=self._root,
            )

    def _on_save(self):
        """Save the current worksheet."""
        if self._current_file is None:
            self._on_save_as()
            return
        self._save_to_file(self._current_file)

    def _on_save_as(self):
        """Save the worksheet to a new file."""
        path = filedialog.asksaveasfilename(
            title="Save Worksheet As",
            defaultextension=".sm",
            filetypes=[
                ("SMath Worksheets", "*.sm"),
                ("All Files", "*.*"),
            ],
            parent=self._root,
        )
        if path:
            self._save_to_file(Path(path))

    def _save_to_file(self, path: Path):
        """Write the current worksheet to a file."""
        if self._worksheet is None:
            self._worksheet = Worksheet()
        try:
            write_file(self._worksheet, str(path))
            self._current_file = path
            self._modified = False
            self._add_recent_file(str(path))
            self._update_title()
            self._status_info.config(text=f"Saved {path.name}")
        except Exception as ex:
            messagebox.showerror(
                "Error Saving File",
                f"Could not save to {path}:\n\n{ex}",
                parent=self._root,
            )

    def _on_print(self):
        """Print placeholder -- not yet implemented."""
        messagebox.showinfo(
            "Print",
            "Printing is not yet implemented in this edition.",
            parent=self._root,
        )

    # ------------------------------------------------------------------
    # Edit operations
    # ------------------------------------------------------------------

    def _on_undo(self):
        self._canvas_widget.undo()
        self._status_info.config(text="Undo")

    def _on_redo(self):
        self._canvas_widget.redo()
        self._status_info.config(text="Redo")

    def _safe_cut(self):
        if not self._canvas_widget._editing:
            self._on_cut()

    def _safe_copy(self):
        if not self._canvas_widget._editing:
            self._on_copy()

    def _safe_paste(self):
        if not self._canvas_widget._editing:
            self._on_paste()

    def _on_cut(self):
        self._canvas_widget.cut_selected()
        self._status_info.config(text="Cut")

    def _on_copy(self):
        text = self._canvas_widget.copy_selected()
        if text:
            self._status_info.config(text=f"Copied: {text}")
        else:
            self._status_info.config(text="Nothing to copy")

    def _on_paste(self):
        self._canvas_widget.paste_at_cursor()
        self._status_info.config(text="Pasted")

    def _on_delete(self):
        self._canvas_widget.delete_selected()
        self._status_info.config(text="Deleted")

    # ------------------------------------------------------------------
    # Insert operations
    # ------------------------------------------------------------------

    def _on_insert_math(self):
        self._canvas_widget.insert_math_at()
        self._status_info.config(text="Type expression, press Enter to commit")

    def _on_insert_text(self):
        self._canvas_widget.insert_text_at()
        self._status_info.config(text="Type text, press Ctrl+Enter to commit")

    def _on_insert_comment(self):
        self._canvas_widget.insert_comment_at()
        self._status_info.config(text="Type comment, press Ctrl+Enter to commit")

    def _on_insert_plot(self):
        self._status_info.config(text="Insert Plot Region (not yet implemented)")

    def _on_insert_line(self):
        self._canvas_widget.insert_line_separator()
        self._status_info.config(text="Line separator inserted")

    def _on_insert_area(self):
        self._status_info.config(text="Insert Area (not yet implemented)")

    def _on_insert_matrix(self):
        """Insert a 2x2 matrix at the cursor position."""
        if not self._canvas_widget._editing:
            self._canvas_widget._start_editing(
                self._canvas_widget._cursor_x,
                self._canvas_widget._cursor_y
            )
        if self._canvas_widget._math_editor:
            self._canvas_widget._math_editor._do_matrix()
            self._canvas_widget._math_editor._update_eval()
            self._canvas_widget._math_editor.render()
        self._status_info.config(text="Matrix inserted (Ctrl+M)")

    def _on_insert_function(self):
        """Show the Insert Function dialog."""
        dlg = InsertFunctionDialog(self._root)
        self._root.wait_window(dlg)
        if dlg.result:
            self._canvas_widget.insert_symbol(f"{dlg.result}(")
            self._status_info.config(text=f"Insert: {dlg.result}()")

    # ------------------------------------------------------------------
    # Calculation
    # ------------------------------------------------------------------

    def _on_recalculate(self):
        """Recalculate the entire worksheet."""
        self._canvas_widget.recalculate()
        self._status_info.config(text="Recalculated")

    def _reset_zoom(self):
        self._canvas_widget._zoom = 1.0
        self._canvas_widget._apply_zoom()
        self._status_info.config(text="Zoom: 100%")

    def _toggle_grid(self):
        self._canvas_widget._show_grid = self._show_grid_var.get()
        self._canvas_widget._evaluate_and_render()

    def _toggle_margin(self):
        self._canvas_widget._show_margin = self._show_margin_var.get()
        self._canvas_widget._evaluate_and_render()

    def _show_regions_list(self):
        """Show a simple list of all regions in the worksheet."""
        ws = self._canvas_widget._worksheet
        if ws is None or not ws.regions:
            messagebox.showinfo("Regions", "No regions in worksheet.", parent=self._root)
            return
        lines = []
        for i, r in enumerate(ws.regions):
            kind = "math" if r.math else "text" if r.text_contents else "other"
            desc = ""
            if r.math and r.math.input_expr:
                from ..infix_parser import ast_to_text
                desc = ast_to_text(r.math.input_expr)[:50]
            elif r.text_contents:
                tc = r.text_contents[0] if r.text_contents else None
                if tc and tc.paragraphs:
                    desc = tc.paragraphs[0].text[:50]
            lines.append(f"{i+1}. [{kind}] ({r.left},{r.top}) {desc}")
        messagebox.showinfo(
            "Regions List", "\n".join(lines), parent=self._root
        )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _on_options(self):
        """Show the Options dialog."""
        dlg = OptionsDialog(self._root, self._settings)
        self._root.wait_window(dlg)
        if dlg.result is not None:
            self._settings.update(dlg.result)
            # Apply precision to worksheet if loaded
            if self._worksheet is not None:
                self._worksheet.settings.calculation.precision = dlg.result[
                    "precision"
                ]
                self._worksheet.settings.calculation.fractions = dlg.result[
                    "fractions"
                ]
                self._worksheet.settings.calculation.trailing_zeros = dlg.result[
                    "trailing_zeros"
                ]
                self._worksheet.settings.calculation.significant_digits_mode = (
                    dlg.result["significant_digits_mode"]
                )
            self._status_info.config(text="Options updated")

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _on_about(self):
        """Show the About dialog."""
        AboutDialog(self._root)

    # ------------------------------------------------------------------
    # Symbol insert from toolbar panels
    # ------------------------------------------------------------------

    def _on_symbol_insert(self, symbol: str):
        """Handle a symbol/function insert from the math toolbar panels."""
        self._canvas_widget.insert_symbol(symbol)
        self._status_info.config(text=f"Insert: {symbol}")

    def _on_canvas_modified(self):
        """Called when the canvas content is modified by editing."""
        self._modified = True
        self._update_title()

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Recent files
    # ------------------------------------------------------------------

    def _load_recent_files(self):
        """Load recent files list from config."""
        self._recent_files = []
        cfg = Path.home() / ".smath_studio" / "recent_files.txt"
        if cfg.exists():
            try:
                for line in cfg.read_text().splitlines():
                    line = line.strip()
                    if line and Path(line).exists():
                        self._recent_files.append(line)
            except Exception:
                pass
        self._update_recent_menu()

    def _save_recent_files(self):
        """Persist recent files list to config."""
        cfg_dir = Path.home() / ".smath_studio"
        cfg_dir.mkdir(exist_ok=True)
        cfg = cfg_dir / "recent_files.txt"
        try:
            cfg.write_text("\n".join(self._recent_files[:10]))
        except Exception:
            pass

    def _add_recent_file(self, path: str):
        """Add a file to the recent files list."""
        path = str(Path(path).resolve())
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:10]
        self._save_recent_files()
        self._update_recent_menu()

    def _update_recent_menu(self):
        """Rebuild the Recent Files submenu."""
        self._recent_menu.delete(0, tk.END)
        if not self._recent_files:
            self._recent_menu.add_command(label="(empty)", state=tk.DISABLED)
            return
        for p in self._recent_files:
            name = Path(p).name
            self._recent_menu.add_command(
                label=name, command=lambda fp=p: self._open_file(fp)
            )

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_exit(self):
        """Handle window close with save prompt."""
        if self._modified:
            answer = messagebox.askyesnocancel(
                "Save Changes",
                "Do you want to save changes before exiting?",
            )
            if answer is None:
                return  # Cancel
            if answer:
                self._on_save()
        self._root.destroy()
