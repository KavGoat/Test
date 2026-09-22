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
from .toolbar import StandardToolbar, FormatToolbar, MathPanelContainer
from .dialogs import (
    AboutDialog, OptionsDialog, InsertFunctionDialog, FindReplaceDialog,
    MatrixSizeDialog, InsertPlotDialog, PageSetupDialog, UnitsBrowserDialog,
)


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

    _UI_FONT = ("DejaVu Sans", 9)

    def _setup_styles(self):
        """Configure ttk styles for a clean appearance matching SMath Studio."""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg = "#ece9d8"
        style.configure(".", background=bg, font=self._UI_FONT)
        style.configure(
            "Toolbutton.TButton",
            padding=(4, 2),
            font=self._UI_FONT,
        )
        style.configure(
            "Toolbar.TFrame",
            background="#ece9d8",
        )
        status_bg = "#ece9d8"
        style.configure(
            "Status.TLabel",
            font=self._UI_FONT,
            padding=(4, 2),
            background=status_bg,
        )
        style.configure(
            "StatusSep.TLabel",
            font=self._UI_FONT,
            foreground="#888888",
            background=status_bg,
        )
        style.configure(
            "Status.TFrame",
            background=status_bg,
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
        file_menu.add_command(label="Page Setup...", command=self._on_page_setup)
        file_menu.add_command(label="Print Preview...", command=self._on_print_preview)
        file_menu.add_command(label="Print...", accelerator="Ctrl+P", command=self._on_print)
        file_menu.add_separator()
        export_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Export", menu=export_menu)
        export_menu.add_command(label="Export as PDF...", command=self._on_export_pdf)
        export_menu.add_command(label="Export as PNG...", command=self._on_export_png)
        export_menu.add_command(label="Export as HTML...", command=self._on_export_html)
        export_menu.add_command(label="Export as LaTeX...", command=self._on_export_latex)
        export_menu.add_command(label="Export as PostScript...", command=self._on_export_ps)
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
        edit_menu.add_command(
            label="Duplicate", command=lambda: self._canvas_widget.duplicate_selected()
        )
        edit_menu.add_command(
            label="Select All", accelerator="Ctrl+A", command=self._on_select_all
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Find and Replace...", accelerator="Ctrl+H",
            command=self._on_find_replace,
        )

        # --- Insert menu ---
        insert_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Insert", menu=insert_menu)
        insert_menu.add_command(label="Math Region", command=self._on_insert_math)
        insert_menu.add_command(label="Text Region", command=self._on_insert_text)
        insert_menu.add_command(label="Comment", command=self._on_insert_comment)
        insert_menu.add_command(label="Plot Region", command=self._on_insert_plot)
        insert_menu.add_command(label="Matrix", accelerator="Ctrl+M", command=self._on_insert_matrix)
        insert_menu.add_command(label="Derivative", accelerator="Ctrl+D", command=self._on_insert_derivative)
        insert_menu.add_command(label="Integral", accelerator="Ctrl+I", command=self._on_insert_integral)
        insert_menu.add_command(label="Summation", accelerator="Ctrl+Shift+S", command=self._on_insert_summation)
        insert_menu.add_command(label="Product", accelerator="Ctrl+Shift+P", command=self._on_insert_product)
        insert_menu.add_command(label="Square Root", command=self._on_insert_sqrt)
        insert_menu.add_command(label="Absolute Value", command=self._on_insert_abs)
        insert_menu.add_command(label="System of Equations", command=self._on_insert_system)
        insert_menu.add_separator()
        insert_menu.add_command(label="Line Separator", command=self._on_insert_line)
        insert_menu.add_command(label="Area", command=self._on_insert_area)
        insert_menu.add_separator()
        insert_menu.add_command(label="Picture...", command=self._on_insert_picture)
        insert_menu.add_separator()
        insert_menu.add_command(
            label="Function...", command=self._on_insert_function
        )
        insert_menu.add_command(
            label="Unit...", command=self._on_insert_unit
        )

        # --- Format menu ---
        format_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Format", menu=format_menu)
        format_menu.add_command(
            label="Bold", accelerator="Ctrl+B", command=self._on_format_bold
        )
        format_menu.add_command(
            label="Italic", command=self._on_format_italic
        )
        format_menu.add_command(
            label="Underline", accelerator="Ctrl+U", command=self._on_format_underline
        )
        format_menu.add_separator()
        self._font_size_var = tk.IntVar(value=10)
        size_menu = tk.Menu(format_menu, tearoff=0)
        for sz in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24):
            size_menu.add_radiobutton(
                label=str(sz), variable=self._font_size_var, value=sz,
                command=self._on_font_size_change,
            )
        format_menu.add_cascade(label="Font Size", menu=size_menu)
        format_menu.add_separator()
        format_menu.add_command(label="Text Color...", command=self._on_text_color)
        format_menu.add_separator()
        align_menu = tk.Menu(format_menu, tearoff=0)
        format_menu.add_cascade(label="Align Regions", menu=align_menu)
        align_menu.add_command(label="Align Left", command=lambda: self._canvas_widget.align_left())
        align_menu.add_command(label="Align Right", command=lambda: self._canvas_widget.align_right())
        align_menu.add_command(label="Align Top", command=lambda: self._canvas_widget.align_top())
        align_menu.add_command(label="Align Bottom", command=lambda: self._canvas_widget.align_bottom())
        align_menu.add_separator()
        align_menu.add_command(label="Distribute Horizontally", command=lambda: self._canvas_widget.distribute_horizontal())
        align_menu.add_command(label="Distribute Vertically", command=lambda: self._canvas_widget.distribute_vertical())

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
        self._show_toolbar_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="Toolbar", variable=self._show_toolbar_var,
            command=self._toggle_toolbar
        )
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
        self._show_ruler_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="Rulers", variable=self._show_ruler_var,
            command=self._toggle_rulers
        )
        self._show_sidebar_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label="Sidebar", variable=self._show_sidebar_var,
            command=self._toggle_sidebar
        )
        view_menu.add_separator()
        view_menu.add_command(
            label="Zoom to Fit", command=self._zoom_to_fit
        )
        view_menu.add_command(
            label="Regions List", command=self._show_regions_list
        )
        self._show_borders_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(
            label="Region Borders", variable=self._show_borders_var,
            command=self._toggle_region_borders,
        )
        view_menu.add_separator()
        view_menu.add_command(label="Go to Page...", command=self._go_to_page)
        view_menu.add_separator()
        self._fullscreen_var = tk.BooleanVar(value=False)
        view_menu.add_checkbutton(
            label="Full Screen", accelerator="F11",
            variable=self._fullscreen_var,
            command=self._toggle_fullscreen,
        )

        # --- Calculation menu ---
        calc_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Calculation", menu=calc_menu)
        self._auto_calc_var = tk.BooleanVar(value=True)
        calc_menu.add_checkbutton(
            label="Automatic Calculation",
            variable=self._auto_calc_var,
            command=self._toggle_auto_calc,
        )
        calc_menu.add_separator()
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
        tools_menu.add_command(label="Units Browser...", command=self._on_units_browser)
        tools_menu.add_separator()
        tools_menu.add_command(label="Options...", command=self._on_options)

        # --- Help menu ---
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About SMath Studio", command=self._on_about)

    def _build_toolbar(self):
        """Build the standard toolbar row."""
        self._toolbar_frame = ttk.Frame(self._root)
        self._toolbar_frame.pack(side=tk.TOP, fill=tk.X)
        toolbar_frame = self._toolbar_frame

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
        self._toolbar.pack(side=tk.LEFT, fill=tk.X, padx=2, pady=1)

        fmt_commands = {
            "bold": self._on_format_bold,
            "italic": self._on_format_italic,
            "underline": self._on_format_underline,
            "font_size": self._on_font_size_change,
            "zoom": self._on_zoom_change,
        }
        self._format_toolbar = FormatToolbar(toolbar_frame, fmt_commands)
        self._format_toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2, pady=1)

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
            self._paned, on_insert=self._on_symbol_insert,
            on_navigate=self._on_doc_map_navigate,
        )
        self._paned.add(self._math_panels, weight=0)

    def _build_status_bar(self):
        """Build the status bar at the bottom."""
        status_frame = ttk.Frame(self._root, relief=tk.SUNKEN, style="Status.TFrame")
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
            status_frame, text="100%", style="Status.TLabel", width=6
        )
        self._status_zoom.pack(side=tk.LEFT)

        self._zoom_scale = tk.Scale(
            status_frame, from_=30, to=300, orient=tk.HORIZONTAL,
            length=100, showvalue=False, command=self._on_zoom_slider,
            relief=tk.FLAT, bd=0, highlightthickness=0, sliderrelief=tk.FLAT,
        )
        self._zoom_scale.set(100)
        self._zoom_scale.pack(side=tk.LEFT, padx=2)

        ttk.Label(status_frame, text="|", style="StatusSep.TLabel").pack(
            side=tk.LEFT, padx=4
        )

        self._status_regions = ttk.Label(
            status_frame, text="0 regions", style="Status.TLabel", width=12
        )
        self._status_regions.pack(side=tk.LEFT)

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
        self._root.bind("<Control-b>", lambda e: self._on_format_bold())
        self._root.bind("<Control-B>", lambda e: self._on_format_bold())
        self._root.bind("<Control-u>", lambda e: self._on_format_underline())
        self._root.bind("<Control-U>", lambda e: self._on_format_underline())
        self._root.bind("<Control-a>", lambda e: self._on_select_all())
        self._root.bind("<Control-A>", lambda e: self._on_select_all())
        self._root.bind("<Control-h>", lambda e: self._on_find_replace())
        self._root.bind("<Control-H>", lambda e: self._on_find_replace())
        self._root.bind("<Control-f>", lambda e: self._on_find_replace())
        self._root.bind("<Control-F>", lambda e: self._on_find_replace())
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
        self._root.bind("<Control-d>", lambda e: self._on_insert_derivative())
        self._root.bind("<Control-D>", lambda e: self._on_insert_derivative())
        self._root.bind("<Control-i>", lambda e: self._on_insert_integral())
        self._root.bind("<Control-I>", lambda e: self._on_insert_integral())
        self._root.bind("<Control-Shift-S>", lambda e: self._on_insert_summation())
        self._root.bind("<Control-Shift-P>", lambda e: self._on_insert_product())
        self._root.bind("<Control-Shift-D>", lambda e: self._canvas_widget.duplicate_selected())
        self._root.bind("<Control-w>", lambda e: self._on_new())
        self._root.bind("<Control-W>", lambda e: self._on_new())
        self._root.bind("<Control-r>", lambda e: self._on_recalculate())
        self._root.bind("<Control-R>", lambda e: self._on_recalculate())
        self._root.bind("<F11>", lambda e: self._toggle_fullscreen_key())

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
            self._zoom_scale.set(zoom)
            calc_mode = "Automatic" if self._auto_calc_var.get() else "Manual"
            n_regions = self._canvas_widget.get_region_count()
            self._status_calc.config(text=calc_mode)
            self._status_regions.config(text=f"{n_regions} regions")
            info = self._canvas_widget.get_selected_info()
            if info:
                self._status_info.config(text=info)
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

            self._canvas_widget._filename = Path(path).stem
            self._canvas_widget.load_worksheet(ws)
            self._add_recent_file(str(path))
            self._update_title()
            self._update_doc_map()
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

    def _on_print_preview(self):
        from .dialogs import PrintPreviewDialog
        ws = self._canvas_widget._worksheet
        pw = int(ws.settings.page.width * 96 / 25.4) if ws else 794
        ph = int(ws.settings.page.height * 96 / 25.4) if ws else 1123
        pages = max(1, self._canvas_widget._num_pages if hasattr(self._canvas_widget, '_num_pages') else 1)
        PrintPreviewDialog(self._root, self._canvas_widget._canvas, pw, ph, pages)

    def _on_print(self):
        """Print by exporting to PDF and opening with system viewer."""
        import tempfile
        try:
            canvas = self._canvas_widget._canvas
            bbox = canvas.bbox("all")
            if bbox is None:
                messagebox.showwarning("Print", "Nothing to print.", parent=self._root)
                return
            x1, y1, x2, y2 = bbox
            margin = 20
            ps = canvas.postscript(
                x=x1 - margin, y=y1 - margin,
                width=x2 - x1 + 2 * margin,
                height=y2 - y1 + 2 * margin,
                colormode="color",
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".ps", delete=False)
            tmp.write(ps.encode("utf-8"))
            tmp.close()
            pdf_path = tmp.name.replace(".ps", ".pdf")
            import subprocess
            result = subprocess.run(
                ["gs", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                 f"-sOutputFile={pdf_path}", tmp.name],
                capture_output=True, timeout=30,
            )
            import os
            os.unlink(tmp.name)
            if result.returncode == 0:
                subprocess.Popen(["xdg-open", pdf_path])
                self._status_info.config(text="Sent to print preview")
            else:
                messagebox.showwarning(
                    "Print", "Could not generate PDF for printing.",
                    parent=self._root,
                )
        except Exception as ex:
            messagebox.showerror("Print Error", str(ex), parent=self._root)

    def _on_export_pdf(self):
        """Export the worksheet canvas as a PDF file."""
        path = filedialog.asksaveasfilename(
            title="Export as PDF",
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf"), ("All Files", "*.*")],
            parent=self._root,
        )
        if not path:
            return
        try:
            canvas = self._canvas_widget._canvas
            bbox = canvas.bbox("all")
            if bbox is None:
                messagebox.showwarning("Export", "Nothing to export.", parent=self._root)
                return
            x1, y1, x2, y2 = bbox
            margin = 20
            ps = canvas.postscript(
                x=x1 - margin, y=y1 - margin,
                width=x2 - x1 + 2 * margin,
                height=y2 - y1 + 2 * margin,
                colormode="color",
            )
            import tempfile, subprocess
            tmp = tempfile.NamedTemporaryFile(suffix=".ps", delete=False)
            tmp.write(ps.encode("utf-8"))
            tmp.close()
            result = subprocess.run(
                ["gs", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                 f"-sOutputFile={path}", tmp.name],
                capture_output=True, timeout=30,
            )
            import os
            os.unlink(tmp.name)
            if result.returncode == 0:
                self._status_info.config(text=f"Exported to {Path(path).name}")
            else:
                eps_path = path.replace(".pdf", ".ps")
                with open(eps_path, "w") as f:
                    f.write(ps)
                self._status_info.config(
                    text=f"PDF conversion failed. Saved as PS: {Path(eps_path).name}"
                )
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex), parent=self._root)

    def _on_export_png(self):
        """Export the worksheet canvas as a PNG image."""
        path = filedialog.asksaveasfilename(
            title="Export as PNG",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All Files", "*.*")],
            parent=self._root,
        )
        if not path:
            return
        try:
            canvas = self._canvas_widget._canvas
            # Generate PostScript then convert with PIL
            bbox = canvas.bbox("all")
            if bbox is None:
                messagebox.showwarning("Export", "Nothing to export.", parent=self._root)
                return
            x1, y1, x2, y2 = bbox
            margin = 20
            ps = canvas.postscript(
                x=x1 - margin, y=y1 - margin,
                width=x2 - x1 + 2 * margin,
                height=y2 - y1 + 2 * margin,
                colormode="color",
            )
            from PIL import Image
            import io
            # Try ghostscript conversion via PIL
            try:
                from PIL import EpsImagePlugin
                EpsImagePlugin.gs_windows_binary = "gs"
                img = Image.open(io.BytesIO(ps.encode("utf-8")))
                img.save(path, "PNG")
                self._status_info.config(text=f"Exported to {Path(path).name}")
            except Exception:
                # Fallback: save as EPS
                eps_path = path.replace(".png", ".eps")
                with open(eps_path, "w") as f:
                    f.write(ps)
                self._status_info.config(
                    text=f"Saved as EPS (install Ghostscript for PNG): {Path(eps_path).name}"
                )
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex), parent=self._root)

    def _on_export_ps(self):
        """Export the worksheet canvas as PostScript."""
        path = filedialog.asksaveasfilename(
            title="Export as PostScript",
            defaultextension=".ps",
            filetypes=[("PostScript", "*.ps"), ("EPS", "*.eps"), ("All Files", "*.*")],
            parent=self._root,
        )
        if not path:
            return
        try:
            canvas = self._canvas_widget._canvas
            bbox = canvas.bbox("all")
            if bbox is None:
                messagebox.showwarning("Export", "Nothing to export.", parent=self._root)
                return
            x1, y1, x2, y2 = bbox
            margin = 20
            ps = canvas.postscript(
                x=x1 - margin, y=y1 - margin,
                width=x2 - x1 + 2 * margin,
                height=y2 - y1 + 2 * margin,
                colormode="color",
            )
            with open(path, "w") as f:
                f.write(ps)
            self._status_info.config(text=f"Exported to {Path(path).name}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex), parent=self._root)

    def _on_export_html(self):
        path = filedialog.asksaveasfilename(
            title="Export as HTML",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("All Files", "*.*")],
            parent=self._root,
        )
        if not path:
            return
        try:
            ws = self._canvas_widget._worksheet
            if ws is None:
                messagebox.showwarning("Export", "No worksheet loaded.", parent=self._root)
                return
            from ..infix_parser import ast_to_text
            lines = ['<!DOCTYPE html>', '<html><head>',
                     '<meta charset="utf-8">',
                     '<title>SMath Studio Worksheet</title>',
                     '<style>body{font-family:serif;max-width:800px;margin:40px auto;padding:0 20px}',
                     '.math{margin:12px 0;font-family:serif;font-style:italic}',
                     '.text{margin:8px 0}.comment{background:#ffffcc;padding:8px;border-left:3px solid #cca}',
                     '.result{color:#0000ff}</style>',
                     '</head><body>']
            for region in ws.regions:
                if region.text_contents:
                    tc = region.text_contents[0] if region.text_contents else None
                    if tc:
                        for p in tc.paragraphs:
                            cls = "comment" if region.bg_color and region.bg_color.lower() in ("#ffff80", "#ffffcc") else "text"
                            lines.append(f'<p class="{cls}">{self._html_escape(p.text)}</p>')
                elif region.math and region.math.input_expr:
                    expr_text = ast_to_text(region.math.input_expr)
                    lines.append(f'<div class="math">{self._html_escape(expr_text)}</div>')
            lines.append('</body></html>')
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._status_info.config(text=f"Exported to {Path(path).name}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex), parent=self._root)

    def _on_export_latex(self):
        path = filedialog.asksaveasfilename(
            title="Export as LaTeX",
            defaultextension=".tex",
            filetypes=[("LaTeX", "*.tex"), ("All Files", "*.*")],
            parent=self._root,
        )
        if not path:
            return
        try:
            ws = self._canvas_widget._worksheet
            if ws is None:
                messagebox.showwarning("Export", "No worksheet loaded.", parent=self._root)
                return
            from ..infix_parser import ast_to_text
            lines = [r'\documentclass{article}', r'\usepackage{amsmath}',
                     r'\begin{document}', '']
            for region in ws.regions:
                if region.text_contents:
                    tc = region.text_contents[0] if region.text_contents else None
                    if tc:
                        for p in tc.paragraphs:
                            lines.append(self._latex_escape(p.text))
                            lines.append('')
                elif region.math and region.math.input_expr:
                    expr_text = ast_to_text(region.math.input_expr)
                    lines.append(f'$$ {self._latex_escape(expr_text)} $$')
                    lines.append('')
            lines.append(r'\end{document}')
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._status_info.config(text=f"Exported to {Path(path).name}")
        except Exception as ex:
            messagebox.showerror("Export Error", str(ex), parent=self._root)

    @staticmethod
    def _html_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _latex_escape(text: str) -> str:
        for ch in ('#', '$', '%', '&', '_', '{', '}'):
            text = text.replace(ch, '\\' + ch)
        return text

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

    def _on_select_all(self):
        self._canvas_widget.select_all()
        self._status_info.config(text="Selected all regions")

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
        dlg = InsertPlotDialog(self._root)
        if dlg.result is None:
            return
        self._canvas_widget.insert_plot_region(
            dlg.result["expression"],
            x_min=dlg.result["x_min"],
            x_max=dlg.result["x_max"],
            width=dlg.result["width"],
            height=dlg.result["height"],
        )
        self._status_info.config(text=f"Plot inserted: {dlg.result['expression']}")

    def _on_insert_line(self):
        self._canvas_widget.insert_line_separator()
        self._status_info.config(text="Line separator inserted")

    def _on_insert_area(self):
        self._canvas_widget.insert_area_region()
        self._status_info.config(text="Area region inserted")

    def _on_insert_picture(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self._root,
            title="Insert Picture",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"),
                ("PNG", "*.png"),
                ("JPEG", "*.jpg *.jpeg"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self._canvas_widget.insert_picture_region(path)
        self._status_info.config(text=f"Picture inserted: {os.path.basename(path)}")

    def _on_insert_matrix(self):
        """Insert a matrix at the cursor position, asking for dimensions."""
        dlg = MatrixSizeDialog(self._root)
        if dlg.result is None:
            return
        rows, cols = dlg.result
        if not self._canvas_widget._editing:
            self._canvas_widget._start_editing(
                self._canvas_widget._cursor_x,
                self._canvas_widget._cursor_y
            )
        if self._canvas_widget._math_editor:
            self._canvas_widget._math_editor._do_matrix(rows=rows, cols=cols)
            self._canvas_widget._math_editor._update_eval()
            self._canvas_widget._math_editor.render()
        self._status_info.config(text=f"Matrix {rows}x{cols} inserted")

    def _on_insert_derivative(self):
        self._insert_structure("_do_derivative", "Derivative")

    def _on_insert_integral(self):
        self._insert_structure("_do_integral", "Integral")

    def _on_insert_summation(self):
        self._insert_structure("_do_summation", "Summation")

    def _on_insert_product(self):
        self._insert_structure("_do_product", "Product")

    def _on_insert_sqrt(self):
        self._insert_structure("_do_sqrt", "Square Root")

    def _on_insert_abs(self):
        self._insert_structure("_do_abs", "Absolute Value")

    def _on_insert_system(self):
        self._insert_structure("_do_system", "System of Equations")

    def _insert_structure(self, method_name: str, label: str):
        if not self._canvas_widget._editing:
            self._canvas_widget._start_editing(
                self._canvas_widget._cursor_x,
                self._canvas_widget._cursor_y
            )
        if self._canvas_widget._math_editor:
            getattr(self._canvas_widget._math_editor, method_name)()
            self._canvas_widget._math_editor._update_eval()
            self._canvas_widget._math_editor.render()
        self._status_info.config(text=f"{label} inserted")

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

    def _toggle_auto_calc(self):
        mode = "Automatic" if self._auto_calc_var.get() else "Manual"
        self._status_calc.config(text=mode)
        self._status_info.config(text=f"Calculation mode: {mode}")

    def _on_font_size_change(self, size: int):
        region = self._canvas_widget.get_selected_region()
        if region is not None:
            region.font_size = size
            self._canvas_widget._evaluate_and_render()
            self._status_info.config(text=f"Font size: {size}")

    def _on_zoom_change(self, zoom: float):
        self._canvas_widget._zoom = max(0.3, min(3.0, zoom))
        self._canvas_widget._apply_zoom()
        pct = self._canvas_widget.get_zoom_percent()
        self._status_info.config(text=f"Zoom: {pct}%")
        if hasattr(self, '_format_toolbar'):
            self._format_toolbar.set_zoom(pct)

    def _reset_zoom(self):
        self._canvas_widget._zoom = 1.0
        self._canvas_widget._apply_zoom()
        self._status_info.config(text="Zoom: 100%")
        if hasattr(self, '_format_toolbar'):
            self._format_toolbar.set_zoom(100)

    def _toggle_toolbar(self):
        if self._show_toolbar_var.get():
            self._toolbar_frame.pack(side=tk.TOP, fill=tk.X, after=self._root.winfo_children()[0])
        else:
            self._toolbar_frame.pack_forget()

    def _toggle_grid(self):
        self._canvas_widget._show_grid = self._show_grid_var.get()
        self._canvas_widget._evaluate_and_render()

    def _toggle_margin(self):
        self._canvas_widget._show_margin = self._show_margin_var.get()
        self._canvas_widget._evaluate_and_render()

    def _toggle_rulers(self):
        show = self._show_ruler_var.get()
        if show:
            self._canvas_widget._ruler_corner.grid()
            self._canvas_widget._ruler.grid()
            self._canvas_widget._v_ruler.grid()
        else:
            self._canvas_widget._ruler_corner.grid_remove()
            self._canvas_widget._ruler.grid_remove()
            self._canvas_widget._v_ruler.grid_remove()

    def _toggle_region_borders(self):
        self._canvas_widget._show_borders = self._show_borders_var.get()
        self._canvas_widget._evaluate_and_render()

    def _go_to_page(self):
        from tkinter import simpledialog
        num_pages = getattr(self._canvas_widget, '_num_pages', 1)
        page = simpledialog.askinteger(
            "Go to Page", f"Page number (1-{num_pages}):",
            parent=self._root, minvalue=1, maxvalue=max(num_pages, 1),
        )
        if page is not None:
            ws = self._canvas_widget._worksheet
            if ws:
                ph = ws.settings.page.height
                target_y = (page - 1) * (ph + 20)
                zy = int(target_y * self._canvas_widget._zoom)
                sr = self._canvas_widget._canvas.cget('scrollregion')
                if sr:
                    parts = sr.split()
                    total = max(int(parts[3]), 1)
                    self._canvas_widget._canvas.yview_moveto(zy / total)

    def _toggle_sidebar(self):
        if self._show_sidebar_var.get():
            self._paned.add(self._math_panels, weight=0)
        else:
            self._paned.forget(self._math_panels)

    def _on_zoom_slider(self, val):
        z = int(float(val)) / 100.0
        z = max(0.3, min(3.0, z))
        if abs(z - self._canvas_widget._zoom) > 0.005:
            self._canvas_widget._zoom = z
            self._canvas_widget._apply_zoom()

    def _zoom_to_fit(self):
        bbox = self._canvas_widget._canvas.bbox("all")
        if not bbox:
            return
        x1, y1, x2, y2 = bbox
        cw = max(self._canvas_widget._canvas.winfo_width(), 100)
        ch = max(self._canvas_widget._canvas.winfo_height(), 100)
        content_w = max(x2 - x1, 1)
        content_h = max(y2 - y1, 1)
        scale = min(cw / content_w, ch / content_h) * 0.95
        self._canvas_widget._zoom = max(0.3, min(3.0, scale))
        self._canvas_widget._apply_zoom()

    def _show_regions_list(self):
        """Show a dialog listing all regions with navigation."""
        ws = self._canvas_widget._worksheet
        if ws is None or not ws.regions:
            messagebox.showinfo("Regions", "No regions in worksheet.", parent=self._root)
            return

        dlg = tk.Toplevel(self._root)
        dlg.title("Regions List")
        dlg.geometry("500x400")
        dlg.transient(self._root)

        frame = ttk.Frame(dlg, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)

        columns = ("num", "type", "position", "content")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        tree.heading("num", text="#")
        tree.heading("type", text="Type")
        tree.heading("position", text="Position")
        tree.heading("content", text="Content")
        tree.column("num", width=40, anchor="center")
        tree.column("type", width=60, anchor="center")
        tree.column("position", width=80, anchor="center")
        tree.column("content", width=300)

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        from ..infix_parser import ast_to_text
        for i, r in enumerate(ws.regions):
            if r.math:
                kind = "Math"
            elif r.text_contents:
                kind = "Text"
            elif r.area:
                kind = "Area"
            elif r.plot:
                kind = "Plot"
            elif r.picture:
                kind = "Image"
            else:
                kind = "Other"
            desc = ""
            if r.math and r.math.input_expr:
                desc = ast_to_text(r.math.input_expr)[:60]
            elif r.text_contents:
                tc = r.text_contents[0] if r.text_contents else None
                if tc and tc.paragraphs:
                    desc = tc.paragraphs[0].text[:60]
            tree.insert("", tk.END, values=(i + 1, kind, f"({r.left}, {r.top})", desc))

        def on_select(event):
            sel = tree.selection()
            if sel:
                idx = tree.index(sel[0])
                if idx < len(self._canvas_widget._rendered):
                    self._canvas_widget._select_region(idx)
                    rr = self._canvas_widget._rendered[idx]
                    self._canvas_widget._ensure_visible(rr.bbox[0], rr.bbox[1])

        tree.bind("<<TreeviewSelect>>", on_select)

        ttk.Button(frame, text="Close", command=dlg.destroy).pack(side=tk.BOTTOM, pady=(4, 0))

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
            self._canvas_widget.recalculate()
            self._status_info.config(text="Options updated")

    def _on_page_setup(self):
        """Show the Page Setup dialog."""
        ws = self._worksheet
        pm = ws.settings.page_model if ws else None
        dlg = PageSetupDialog(self._root, pm)
        if dlg.result is not None and ws is not None:
            ws.settings.page_model.paper_width = dlg.result["paper_width"]
            ws.settings.page_model.paper_height = dlg.result["paper_height"]
            ws.settings.page_model.paper_orientation = dlg.result["orientation"]
            ws.settings.page_model.margin_left = dlg.result["margin_left"]
            ws.settings.page_model.margin_right = dlg.result["margin_right"]
            ws.settings.page_model.margin_top = dlg.result["margin_top"]
            ws.settings.page_model.margin_bottom = dlg.result["margin_bottom"]
            ws.settings.page_model.active = True
            from ..parser import HeaderFooter
            hdr = dlg.result.get("header", "")
            ftr = dlg.result.get("footer", "")
            if hdr:
                if ws.settings.page_model.header is None:
                    ws.settings.page_model.header = HeaderFooter()
                ws.settings.page_model.header.text = hdr
            else:
                ws.settings.page_model.header = None
            if ftr:
                if ws.settings.page_model.footer is None:
                    ws.settings.page_model.footer = HeaderFooter()
                ws.settings.page_model.footer.text = ftr
            else:
                ws.settings.page_model.footer = None
            self._canvas_widget.recalculate()
            self._status_info.config(text="Page setup updated")

    def _on_insert_unit(self):
        """Open the Units Browser and insert the selected unit."""
        dlg = UnitsBrowserDialog(self._root)
        if dlg.result:
            self._canvas_widget.insert_symbol(dlg.result)
            self._status_info.config(text=f"Inserted unit: {dlg.result}")

    def _on_units_browser(self):
        """Open the Units Browser dialog."""
        self._on_insert_unit()

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode."""
        is_fs = self._fullscreen_var.get()
        self._root.attributes("-fullscreen", is_fs)

    def _toggle_fullscreen_key(self):
        """Toggle fullscreen via keyboard shortcut."""
        self._fullscreen_var.set(not self._fullscreen_var.get())
        self._toggle_fullscreen()

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    def _on_about(self):
        """Show the About dialog."""
        AboutDialog(self._root)

    def _show_shortcuts(self):
        """Show keyboard shortcuts reference."""
        shortcuts = (
            "Keyboard Shortcuts\n"
            "═══════════════════════════\n\n"
            "File\n"
            "  Ctrl+N        New worksheet\n"
            "  Ctrl+O        Open file\n"
            "  Ctrl+S        Save\n"
            "  Ctrl+P        Print\n\n"
            "Edit\n"
            "  Ctrl+Z        Undo\n"
            "  Ctrl+Y        Redo\n"
            "  Ctrl+X        Cut\n"
            "  Ctrl+C        Copy\n"
            "  Ctrl+V        Paste\n"
            "  Ctrl+A        Select All\n"
            "  Ctrl+H        Find/Replace\n"
            "  Delete        Delete region\n\n"
            "Math Input\n"
            "  :=            Define variable\n"
            "  =             Evaluate expression\n"
            "  Ctrl+M        Insert matrix\n"
            "  Ctrl+D        Insert derivative\n"
            "  Ctrl+I        Insert integral\n"
            "  Ctrl+Shift+S  Insert summation\n"
            "  Ctrl+Shift+P  Insert product\n"
            "  /             Fraction (in editor)\n"
            "  ^             Superscript\n"
            "  (             Parentheses\n"
            "  \\             Square root\n"
            "  |             Absolute value\n"
            "  '             Unit entry mode\n"
            "  _             Subscript dot\n\n"
            "Calculation\n"
            "  F2            Insert text region\n"
            "  F5            Evaluate selection\n"
            "  F9            Recalculate all\n"
            "  Ctrl+R        Recalculate all\n\n"
            "View\n"
            "  Ctrl++        Zoom in\n"
            "  Ctrl+-        Zoom out\n"
            "  Ctrl+0        Zoom 100%\n"
            "  F11           Toggle fullscreen\n\n"
            "Format\n"
            "  Ctrl+B        Bold\n"
            "  Ctrl+U        Underline\n\n"
            "Navigation\n"
            "  Tab           Next region\n"
            "  Shift+Tab     Previous region\n"
            "  Arrow keys    Move cursor\n"
            "  Enter         Edit selected region\n"
            "  Escape        Deselect / Cancel edit\n"
        )
        dlg = tk.Toplevel(self._root)
        dlg.title("Keyboard Shortcuts")
        dlg.geometry("380x520")
        dlg.transient(self._root)
        text = tk.Text(dlg, font=("DejaVu Sans Mono", 9), wrap=tk.WORD, padx=12, pady=12)
        text.insert("1.0", shortcuts)
        text.config(state=tk.DISABLED)
        text.pack(fill=tk.BOTH, expand=True)
        dlg.bind("<Escape>", lambda e: dlg.destroy())

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
        self._update_doc_map()

    def _update_doc_map(self):
        """Refresh the Document Map panel with title regions."""
        if self._worksheet is None:
            self._math_panels.doc_map.update_entries([])
            return
        entries: list[tuple[str, float]] = []
        for r in self._worksheet.regions:
            if not r.text_contents:
                continue
            fg = (r.color or "#000000").lower()
            if fg not in ("#0000ff", "#0000cc"):
                continue
            tc = self._canvas_widget._get_text_content(r.text_contents)
            if tc and tc.paragraphs:
                title = " ".join(p.text for p in tc.paragraphs).strip()
                if title:
                    entries.append((title, r.top))
        self._math_panels.doc_map.update_entries(entries)

    def _on_doc_map_navigate(self, top: float):
        """Scroll the canvas to show the region at the given top position."""
        zoom = self._canvas_widget._zoom
        canvas = self._canvas_widget._canvas
        y = int(top * zoom)
        canvas.yview_moveto(0)
        canvas.update_idletasks()
        sr = canvas.cget("scrollregion")
        if sr:
            parts = sr.split()
            total_h = float(parts[3]) - float(parts[1])
            if total_h > 0:
                target = max(0, y - 40)
                canvas.yview_moveto(target / total_h)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Find and Replace
    # ------------------------------------------------------------------

    def _on_find_replace(self):
        """Open the Find and Replace dialog."""
        self._find_idx = 0
        FindReplaceDialog(
            self._root,
            on_find=self._do_find,
            on_replace=self._do_replace,
            on_replace_all=self._do_replace_all,
        )

    def _do_find(self, text: str, match_case: bool):
        """Find and select the next region containing the search text."""
        if not text or self._canvas_widget._worksheet is None:
            return
        ws = self._canvas_widget._worksheet
        rendered = self._canvas_widget._rendered
        start = getattr(self, "_find_idx", 0)
        for i in range(len(rendered)):
            idx = (start + i) % len(rendered)
            region = rendered[idx].region
            expr_text = self._canvas_widget._region_to_edit_text(region)
            if not expr_text and region.text_contents:
                tc = self._canvas_widget._get_text_content(region.text_contents)
                if tc and tc.paragraphs:
                    expr_text = " ".join(p.text for p in tc.paragraphs)
            if not expr_text:
                continue
            check = expr_text if match_case else expr_text.lower()
            target = text if match_case else text.lower()
            if target in check:
                self._canvas_widget._select_region(idx)
                self._find_idx = idx + 1
                self._status_info.config(text=f"Found at region {idx + 1}")
                return
        self._status_info.config(text="Not found")
        self._find_idx = 0

    def _do_replace(self, find: str, replace: str, match_case: bool):
        """Replace in the currently selected region."""
        if not find:
            return
        idx = self._canvas_widget._selected_index
        if idx is None or idx >= len(self._canvas_widget._rendered):
            self._do_find(find, match_case)
            return
        region = self._canvas_widget._rendered[idx].region
        if region.math and region.math.input_expr:
            from ..infix_parser import ast_to_text, parse_infix, ast_to_elements
            expr_text = ast_to_text(region.math.input_expr)
            if match_case:
                new_text = expr_text.replace(find, replace)
            else:
                import re
                new_text = re.sub(re.escape(find), replace, expr_text, flags=re.IGNORECASE)
            if new_text != expr_text:
                self._canvas_widget._save_undo_state()
                ast = parse_infix(new_text)
                if ast:
                    region.math.input_expr = ast
                    region.math.input_elements = ast_to_elements(ast)
                    self._canvas_widget._mark_modified()
                    self._canvas_widget._evaluate_and_render()
                    self._status_info.config(text="Replaced")
        self._do_find(find, match_case)

    def _do_replace_all(self, find: str, replace: str, match_case: bool):
        """Replace in all regions."""
        if not find:
            return
        ws = self._canvas_widget._worksheet
        if ws is None:
            return
        from ..infix_parser import ast_to_text, parse_infix, ast_to_elements
        count = 0
        self._canvas_widget._save_undo_state()
        for region in ws.regions:
            if region.math and region.math.input_expr:
                expr_text = ast_to_text(region.math.input_expr)
                if match_case:
                    new_text = expr_text.replace(find, replace)
                else:
                    import re
                    new_text = re.sub(re.escape(find), replace, expr_text, flags=re.IGNORECASE)
                if new_text != expr_text:
                    ast = parse_infix(new_text)
                    if ast:
                        region.math.input_expr = ast
                        region.math.input_elements = ast_to_elements(ast)
                        count += 1
        if count > 0:
            self._canvas_widget._mark_modified()
            self._canvas_widget._evaluate_and_render()
        self._status_info.config(text=f"Replaced {count} occurrence(s)")

    # ------------------------------------------------------------------
    # Format operations
    # ------------------------------------------------------------------

    def _on_format_bold(self):
        entry = getattr(self._canvas_widget, "_edit_text_entry", None)
        if entry and isinstance(entry, tk.Text):
            try:
                sel_start = entry.index("sel.first")
                sel_end = entry.index("sel.last")
                if "bold" in entry.tag_names(sel_start):
                    entry.tag_remove("bold", sel_start, sel_end)
                else:
                    entry.tag_add("bold", sel_start, sel_end)
                    entry.tag_configure("bold", font=("DejaVu Sans", 11, "bold"))
            except tk.TclError:
                pass

    def _on_format_italic(self):
        entry = getattr(self._canvas_widget, "_edit_text_entry", None)
        if entry and isinstance(entry, tk.Text):
            try:
                sel_start = entry.index("sel.first")
                sel_end = entry.index("sel.last")
                if "italic" in entry.tag_names(sel_start):
                    entry.tag_remove("italic", sel_start, sel_end)
                else:
                    entry.tag_add("italic", sel_start, sel_end)
                    entry.tag_configure("italic", font=("DejaVu Sans", 11, "italic"))
            except tk.TclError:
                pass

    def _on_format_underline(self):
        entry = getattr(self._canvas_widget, "_edit_text_entry", None)
        if entry and isinstance(entry, tk.Text):
            try:
                sel_start = entry.index("sel.first")
                sel_end = entry.index("sel.last")
                if "underline" in entry.tag_names(sel_start):
                    entry.tag_remove("underline", sel_start, sel_end)
                else:
                    entry.tag_add("underline", sel_start, sel_end)
                    entry.tag_configure("underline", underline=True)
            except tk.TclError:
                pass

    def _on_font_size_change(self):
        size = self._font_size_var.get()
        if self._canvas_widget._selected_index is not None:
            idx = self._canvas_widget._selected_index
            if idx < len(self._canvas_widget._rendered):
                region = self._canvas_widget._rendered[idx].region
                region.font_size = size
                self._canvas_widget._evaluate_and_render()
                self._status_info.config(text=f"Font size: {size}")

    def _on_text_color(self):
        try:
            from tkinter import colorchooser
            color = colorchooser.askcolor(
                title="Text Color", parent=self._root
            )
            if color[1]:
                if self._canvas_widget._selected_index is not None:
                    idx = self._canvas_widget._selected_index
                    if idx < len(self._canvas_widget._rendered):
                        region = self._canvas_widget._rendered[idx].region
                        region.color = color[1]
                        self._canvas_widget._evaluate_and_render()
                        self._status_info.config(text=f"Color: {color[1]}")
        except Exception:
            pass

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
