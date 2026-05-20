#!/usr/bin/env -S python3 -OO
"""
atom2_viewer.py  –  Atom 2 Flight Log Viewer & Exporter
========================================================
Combined replacement for adv.py (visualizer) and atom_data_extractor.py (CSV export).

Layout
------
  Left  : persistent file list (fc2 files, survives restarts)
  Right : animated dashboard (top) + map (middle) + playback controls (bottom)

Menus
-----
  File   : Import FC2…  |  Import Directory…  | ──  | Export CSV…  | Export All CSV…
           ── | Preferences… | ── | View Log… | ── | Quit
  View   : Show Flight Summary  |  Show Log Window  |  Fit Map to Path
  Playback : Play/Pause  |  Step Back  |  Step Forward  |  Rewind  |  Speed ←  |  Speed →
  Help   : About

Keyboard shortcuts (non-Mac)
-----------------------------
  Ctrl+O   Import FC2 file(s)
  Ctrl+E   Export current file to CSV
  Ctrl+Q   Quit

  Ctrl+F   Show Flight Summary
  Ctrl+L   Show Log

  Ctrl+0   Zoom map to fit window.

  Space    Play / Pause
  Left     Step back  (100 records)
  Right    Step forward (100 records)

  Delete   Remove selected file from list
  Backspc  Remove selected file from list

Author: Michael Heinz
"""

# ─────────────────────────────────────────────────────────────────────────────
# Standard library
# ─────────────────────────────────────────────────────────────────────────────
import csv
import json
import os
import platform
import sys
import threading
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Tkinter
# ─────────────────────────────────────────────────────────────────────────────
import tkinter as tk
import tkinter.font as tkf
from tkinter import filedialog, messagebox, ttk
from tkinter.colorchooser import askcolor

# ─────────────────────────────────────────────────────────────────────────────
# Third-party – install with:
#   pip install tkintermapview pillow
# ─────────────────────────────────────────────────────────────────────────────
try:
    import tkintermapview
    HAS_MAP = True
except ImportError:
    HAS_MAP = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─────────────────────────────────────────────────────────────────────────────
# Local modules (same directory as this file)
# ─────────────────────────────────────────────────────────────────────────────
from atom2parser import (
    BASIC_DATA,
    DERIVED_DATA,
    EXTENDED_DATA,
    atom2_parser,
    is_valid_latlon,
    log_stats,
    atom2_parse_filename,
)
import mwhlogging
from mwhlogging import MWHLogger

try:
    from advversion import _version
except ImportError:
    _version = "unknown"

# ─────────────────────────────────────────────────────────────────────────────
# Module-level logger  (window will be attached after Tk root exists)
# ─────────────────────────────────────────────────────────────────────────────
my_logger = MWHLogger("atom2_viewer")
my_logger.setLevel(mwhlogging.DEBUG)

PLATFORM_SYSTEM = platform.system()

# ─────────────────────────────────────────────────────────────────────────────
# Persistent state files
# ─────────────────────────────────────────────────────────────────────────────
PREFS_FILE   = Path.home() / ".atom2_viewer_prefs.json"
FILELIST_FILE = Path.home() / ".atom2_viewer_files.json"

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard metrics shown in the animated header strip.
# Each tuple: (display_label, data_key, unit, format_spec)
# ─────────────────────────────────────────────────────────────────────────────
DASHBOARD_METRICS = [
    ("Speed",    "3d Derived Speed (m/s)", " m/s", ".1f", "max_speed"),
    ("Alt",      "alt (m)",                " m",   ".1f", "max_alt"),
    ("Dist",     "2d Derived Distance (m)","m",    ".0f", "max_dist"),
    ("Heading",  "heading (deg)",          "°",    ".1f", None),
    ("Battery",  "Battery Level (%)",      "%",    ".0f", None),
    ("Sats",     "Satellites",             "",     "d", None),
    ("Wind",     "Wind Speed (m/s)",       " m/s", ".1f", "max_wind"),
    ("Mode",     "Flight Mode (text)",     "",     "s", None),
]

# ─────────────────────────────────────────────────────────────────────────────
# Application defaults
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_PREFS = {
    # ─── Basic Settings ───
    "window_geometry": "1400x860",
    "sash_position": 165,           # Width of the left pane.
    "log_level": "Info",
    "last_import_dir": str(Path.home()),
    "last_export_dir": str(Path.home()),

    # ─── Gauge Limits ───
    "max_speed": 57,
    "max_alt": 200,
    "max_dist": 500,
    "max_wind": 10,

    # ─── Color palette ───
    "color_bg":         "#ffffff",  # Main background (White)
    "color_panel_bg":   "#f8f9fa",  # Lighter background for containers (Off-white)
    "color_button_bg":  "#e9ecef",  # Button background (Very light gray)
    "color_button_fg":  "#222222",  # Button text color (Dark gray)
    "color_accent":     "#0432ff",  # Primary interactive highlight (Blue)
    "color_border":     "#011892",  # Separator lines (Duller blue)
    "color_value":      "#212529",  # Text value color (Near black)
    "color_label":      "#6c757d",  # Label color (Medium gray)
    "color_path":       "#148023",  # Map Path (Forest Green)
    "color_safe":       "#28a745",  # Safe (Standard Green)
    "color_warn":       "#ff9300",  # Warning (Amber/Orange)
    "color_danger":     "#ff2600",  # Danger (Red)
    "color_select":     "#0096ff",  # Selected List Item

    # ─── Font palette ───
    "font_ui": ["TkDefaultFont", 10],
    "font_title": ["TkDefaultFont", 12, "bold"],
    "font_small": ["TkDefaultFont", 8],
    "font_metric": ["TkDefaultFont", 12],
    "font_marker": "",

    # ─── CSV export options ───
    "csv_extended": False,
    "csv_derived": True,

    # ─── System Theme ───
    "theme": "default",
}

DARK_MODE_PREFS = {
    # ─── Basic Settings ───
    "window_geometry": "1400x860",
    "sash_position": 165,
    "log_level": "Info",
    "last_import_dir": str(Path.home()),
    "last_export_dir": str(Path.home()),

    # ─── Gauge Limits ───
    "max_speed": 57,
    "max_alt": 200,
    "max_dist": 500,
    "max_wind": 10,

    # ─── Color palette ───
    "color_bg":         "#121212",  # Main background (Near black)
    "color_panel_bg":   "#1e1e2d",  # Panel background (Deep midnight blue/gray)
    "color_button_bg":  "#252526",  # Button background (Slightly different from panel)
    "color_button_fg":  "#e0e0e0",  # Button text color (Off-white/Light gray)
    "color_accent":     "#64b5ff",  # Primary interactive highlight (Bright Cyan/Sky Blue)
    "color_border":     "#333333",  # Separator lines (Medium dark gray)
    "color_value":      "#e0e0e0",  # Text value color (Off-white/Light gray)
    "color_label":      "#9e9e9e",  # Label color (Medium gray)
    "color_path":       "#4caf50",  # Success/Path (Vibrant Green)
    "color_safe":       "#4caf50",  # Safe (Vibrant Green)
    "color_warn":       "#ff9800",  # Warning (Vibrant Orange/Amber)
    "color_danger":     "#f44336",  # Danger (Vibrant Red)
    "color_select":     "#1f6feb",  # Selected List Item

    # ─── Font palette ───
    "font_ui": ["TkDefaultFont", 10],
    "font_title": ["TkDefaultFont", 12, "bold"],
    "font_small": ["TkDefaultFont", 8],
    "font_metric": ["TkDefaultFont", 14, "bold"],
    "font_marker": "",

    # ─── CSV export options ───
    "csv_extended": False,
    "csv_derived": True,

    # ─── System Theme ───
    "theme": "default",
}

if PLATFORM_SYSTEM == "Linux":
    DEFAULT_PREFS["font_ui"]    = ["Liberation", 10]
    DEFAULT_PREFS["font_title"] = ["Times", 12, "bold"]
    DEFAULT_PREFS["font_small"] = ["Liberation", 8]
    DEFAULT_PREFS["font_metric"]= ["Liberation", 12]
    DARK_MODE_PREFS["font_ui"]    = ["Liberation", 10]
    DARK_MODE_PREFS["font_title"] = ["Times", 12, "bold"]
    DARK_MODE_PREFS["font_small"] = ["Liberation", 8]
    DARK_MODE_PREFS["font_metric"]= ["Liberation", 12]
elif PLATFORM_SYSTEM == "Darwin":
    DEFAULT_PREFS["font_ui"]    = ["Helvetica Neue", 10]
    DEFAULT_PREFS["font_title"] = ["Helvetica Neue", 12, "bold"]
    DEFAULT_PREFS["font_small"] = ["Helvetica Neue", 8]
    DEFAULT_PREFS["font_metric"]= ["Helvetica Neue", 12]
    #DEFAULT_PREFS["font_marker"]="/System/Library/Fonts/HelveticaNeue.ttc"
    DARK_MODE_PREFS["font_ui"]    = ["Helvetica Neue", 10]
    DARK_MODE_PREFS["font_title"] = ["Helvetica Neue", 12, "bold"]
    DARK_MODE_PREFS["font_small"] = ["Helvetica Neue", 8]
    DARK_MODE_PREFS["font_metric"]= ["Helvetica Neue", 12]
    #DARK_MODE_PREFS["font_marker"]="/System/Library/Fonts/HelveticaNeue.ttc"

# ─────────────────────────────────────────────────────────────────────────────
# Preference persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_prefs() -> dict:
    my_logger.debug("Loading preferences.")
    prefs = DEFAULT_PREFS.copy()
    try:
        if PREFS_FILE.exists():
            with open(PREFS_FILE, encoding="utf-8") as f:
                prefs.update(json.load(f))
    except Exception as exc:
        my_logger.warning("Could not load prefs: %s", exc)
    return prefs


def save_prefs(prefs: dict) -> None:
    my_logger.debug("Saving preferences.")
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception as exc:
        my_logger.error("Could not save prefs: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# File-list persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_file_list() -> list[str]:
    my_logger.debug("Loading file list.")
    try:
        if FILELIST_FILE.exists():
            with open(FILELIST_FILE, encoding="utf-8") as f:
                paths = json.load(f)
                paths.sort()
            return [p for p in paths if Path(p[0]).exists()]
    except Exception as exc:
        my_logger.warning("Could not load file list: %s", exc)
    return []


def save_file_list(paths: list[str]) -> None:
    my_logger.debug("Saving file list.")
    try:
        with open(FILELIST_FILE, "w", encoding="utf-8") as f:
            json.dump(paths, f, indent=2)
    except Exception as exc:
        my_logger.error("Could not save file list: %s", exc)


class PrefsDialog(tk.Toplevel):
    """
    Displays the current preferences and allows updating them.
    Supports two sets of defaults - normal and dark mode.
    """

    COLOR_FIELDS=[
        ("color_bg",       "Background"),
        ("color_panel_bg", "Panel Background"),
        ("color_button_bg","Button Backg."),
        ("color_button_fg","Button Text"),
        ("color_accent",   "Accent"),
        ("color_border",   "Border"),
        ("color_value",    "Values"),
        ("color_label",    "Label"),
        ("color_path",     "Flight Path"),
        ("color_safe",     "Safe"),
        ("color_warn",     "Warning"),
        ("color_danger",   "Danger"),
        ("color_select",   "Selected"),
    ]

    FONT_FIELDS=[
        ("font_ui",  "Label Font"),
        ("font_title",  "Title Font"),
        ("font_small",  "Small Font"),
        ("font_metric",  "Gauge Font"),
    ]

    # Use this to restrict input on the numeric fields.
    @staticmethod
    def _validate_digit(p) -> bool:
        return (p.isdigit() or p =="")

    def __init__(self, parent, prefs: dict, on_save, menubar):
        my_logger.debug("Creating Prefs Dialog.")
        super().__init__(parent)

        self.title("Preferences")
        self.resizable(False, False)
        self.transient(parent)      # keep on top of parent
        self.menubar=menubar
        self.validate=parent.register(self._validate_digit)

        self.configure(menu=menubar)
        self._prefs  =prefs.copy()
        self._on_save=on_save
        self._swatches: dict[str, tk.Label]={}
        self._font_vars: dict[str, tuple]  ={}

        self._csv_extended_var = tk.BooleanVar(value=self._prefs.get("csv_extended", False))
        self._csv_derived_var = tk.BooleanVar(value=self._prefs.get("csv_derived", True))

        self._build()

        self.protocol("WM_DELETE_WINDOW", lambda: self.withdraw())
        if PLATFORM_SYSTEM == "Darwin":
            self.bind("<Command-w>", lambda e: self.withdraw())
        else:
            self.bind("<Control-w>", lambda e: self.withdraw())

        self._center_on(parent)

    # ── Layout ─────────────────────────────────────────────────────────

    def _build(self):
        pad={"padx" : 10, "pady" : 4}

        tk.Label(self, text="Most changes will not take effect until restart.",
                 font=self._prefs["font_ui"]).pack(padx=12, pady=(8, 0),
                                                  anchor="w")

        # ── Limits ──────────────────────────────────────────────────────────

        limits_frame=tk.LabelFrame(self, text="Gauge Limits", padx=6, pady=6)
        limits_frame.pack(fill=tk.X, padx=4, pady=4)

        # (Limit widgets setup remains identical)
        tk.Label(limits_frame, text="Max Dist:", anchor="w",
                 width=12).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self._max_dist=tk.IntVar(value=self._prefs.get("max_dist", 0))
        tk.Entry(limits_frame, textvariable=self._max_dist,
                validatecommand=(self.validate,"%P"), validate="key",
                width=4).grid(row=0, column=1, padx=4, pady=4, sticky="w")
        tk.Label(limits_frame, text="meters", anchor="w",
                width=12).grid(row=0, column=2, sticky="w", padx=4, pady=4)

        tk.Label(limits_frame, text="Max Speed:", anchor="w",
                 width=12).grid(row=0, column=3, sticky="w", padx=4, pady=4)
        self._max_speed=tk.IntVar(value=self._prefs.get("max_speed", 0))
        tk.Entry(limits_frame, textvariable=self._max_speed,
                validatecommand=(self.validate,"%P"), validate="key",
                 width=4).grid(row=0, column=4, padx=4, pady=4, sticky="w")
        tk.Label(limits_frame, text="kph", anchor="w",
                width=12).grid(row=0, column=5, sticky="w", padx=4, pady=4)

        tk.Label(limits_frame, text="Max Alt:", anchor="w",
                 width=12).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self._max_alt=tk.IntVar(value=self._prefs.get("max_alt", 0))
        tk.Entry(limits_frame, textvariable=self._max_alt,
                validatecommand=(self.validate,"%P"), validate="key",
                width=4).grid(row=1, column=1, padx=4, pady=4, sticky="w")
        tk.Label(limits_frame, text="meters", anchor="w",
                width=12).grid(row=1, column=2, sticky="w", padx=4, pady=4)

        tk.Label(limits_frame, text="Max Wind:", anchor="w",
                 width=12).grid(row=1, column=3, sticky="w", padx=4, pady=4)
        self._max_wind=tk.IntVar(value=self._prefs.get("max_wind", 0))
        tk.Entry(limits_frame, textvariable=self._max_wind,
                validatecommand=(self.validate,"%P"), validate="key",
                width=4).grid(row=1, column=4, padx=4, pady=4, sticky="w")
        tk.Label(limits_frame, text="m/s", anchor="w",
                width=12).grid(row=1, column=5, sticky="w", padx=4, pady=4)

        # ── Colors ────────────────────────────────────────────────────────
        color_frame=tk.LabelFrame(self, text=" Colors ", padx=6, pady=6)
        color_frame.pack(fill=tk.X, padx=4, pady=4)

        for i, (key, label) in enumerate(self.COLOR_FIELDS):
            row=i // 2
            col=(i % 2) * 3

            tk.Label(color_frame, text=label + ":", anchor="w",
                     width=12).grid(row=row, column=col, sticky="w", **pad)

            swatch=tk.Label(color_frame, width=3,
                              bg=self._prefs.get(key, "#000000"),
                              relief=tk.SOLID, bd=1)
            swatch.grid(row=row, column=col + 1, padx=(0, 4), pady=4)
            self._swatches[key]=swatch

            tk.Button(color_frame, text="Choose…",
                      command=lambda k=key: self._pick_color(k),
                      padx=4).grid(row=row, column=col + 2, **pad)

        # ── Fonts ─────────────────────────────────────────────────────

        font_frame=tk.LabelFrame(self, text=" Fonts ", padx=6, pady=6)
        font_frame.pack(fill=tk.X, padx=4, pady=4)

        families=self._get_font_families()

        for i, (key, label) in enumerate(self.FONT_FIELDS):
            current=self._prefs.get(key, ("Helvetica", 10))
            current_family=current[0]
            current_size  =current[1]
            current_bold  =len(current) > 2 and current[2] == "bold"

            tk.Label(font_frame, text=label + ":", anchor="w",
                    width=12).grid(row=i, column=0, sticky="w", padx=(10, 4), pady=4)

            # Family dropdown
            family_var=tk.StringVar(value=current_family)
            family_cb =ttk.Combobox(font_frame, textvariable=family_var,
                                    values=families, width=22, state="readonly")
            family_cb.grid(row=i, column=1, padx=4, pady=4)

            # Size spinbox
            size_var=tk.IntVar(value=current_size)
            tk.Spinbox(font_frame, textvariable=size_var,
                    from_=6, to=32, width=4).grid(row=i, column=2, padx=4, pady=4)

            # Bold checkbox
            bold_var=tk.BooleanVar(value=current_bold)
            tk.Checkbutton(font_frame, text="Bold",
                        variable=bold_var).grid(row=i, column=3, padx=4, pady=4)

            self._font_vars[key]=(family_var, size_var, bold_var)

        # ── CSV Export Options ───────────────────────────────────────────
        csv_frame=tk.LabelFrame(self, text=" CSV Export Options ", padx=6, pady=6)
        csv_frame.pack(fill=tk.X, padx=4, pady=4)

        tk.Label(csv_frame, text="Include Extended Data:",
                 anchor="w").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        chk_ext = tk.Checkbutton(csv_frame, variable=self._csv_extended_var)
        chk_ext.grid(row=0, column=1)

        tk.Label(csv_frame, text="Include Derived Data:",
                 anchor="w").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        chk_der = tk.Checkbutton(csv_frame, variable=self._csv_derived_var)
        chk_der.grid(row=0, column=3)

        # ── Logging ──────────────────────────────────────────────
        log_frame=tk.LabelFrame(self, text=" Logging ", padx=6, pady=6)
        log_frame.pack(fill=tk.X, padx=12, pady=4)

        tk.Label(log_frame, text="Log Level:").pack(side=tk.LEFT, padx=(4, 8))
        self._log_var=tk.StringVar(value=self._prefs.get("log_level", "Info"))
        for level in ("Error", "Warning", "Info", "Debug"):
            tk.Radiobutton(log_frame, text=level,
                           variable=self._log_var, value=level).pack(
                side=tk.LEFT, padx=4)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row=tk.Frame(self)
        btn_row.pack(fill=tk.X, padx=12, pady=(4, 12))

        tk.Button(btn_row, text="Light Mode",
                  command=self._light_mode).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Dark Mode",
                  command=self._dark_mode).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Save",
                  command=self._save,
                  default=tk.ACTIVE).pack(side=tk.RIGHT)
        tk.Button(btn_row, text="Cancel",
                  command=self.withdraw).pack(side=tk.RIGHT, padx=(4, 0))

        # Allow Enter to save and Escape to cancel
        self.bind("<Return>",  lambda e: self._save())
        self.bind("<Escape>",  lambda e: self.withdraw())
        if PLATFORM_SYSTEM == "Darwin":
            self.bind("<Command-w>", lambda e: self.withdraw())
        else:
            self.bind("<Control-w>", lambda e: self.withdraw())


    # ──────────────────────────────────────────────────────────────────────────
    # Helper Functions
    # ──────────────────────────────────────────────────────────────────────────

    def _get_font_families(self) -> list[str]:
        families=sorted(set(tkf.families()))
        return [f for f in families if not f.startswith("@")]  # skip vertical CJK fonts

    def _center_on(self, parent):
        self.update_idletasks()
        x=parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y=parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _pick_color(self, key: str):
        current=self._prefs.get(key, "#000000")
        _, hex_color=askcolor(color=current,
                                title=f"Choose: {key}",
                                parent=self)
        if hex_color:
            self._prefs[key]=hex_color
            self._swatches[key].configure(bg=hex_color)

    def _light_mode(self):
        """Resets all widgets based on the default theme."""
        default_prefs = DEFAULT_PREFS

        # 1. Restore Limits
        self._max_speed.set(default_prefs.get("max_speed"))
        self._max_dist.set(default_prefs.get("max_dist"))
        self._max_alt.set(default_prefs.get("max_alt"))
        self._max_wind.set(default_prefs.get("max_wind"))

        # 2. Restore Colors
        for key, _ in self.COLOR_FIELDS:
            default=default_prefs.get(key, "#000000")
            self._prefs[key]=default
            self._swatches[key].configure(bg=default)

        # 3. Restore Fonts
        for key, _ in self.FONT_FIELDS:
            default=default_prefs.get(key, ("Helvetica", 10))
            family_var, size_var, bold_var=self._font_vars[key]
            family_var.set(default[0])
            size_var.set(default[1])
            bold_var.set(len(default) > 2 and default[2] == "bold")
        self._log_var.set(default_prefs.get("log_level", "Info"))

        # 4. Update CSV Checkbox States
        self._csv_extended_var.set(default_prefs.get("csv_extended", False))
        self._csv_derived_var.set(default_prefs.get("csv_derived", True))

        # 5. Update internal state to match the theme
        self._prefs.update(default_prefs)
        self.update_idletasks()

    def _dark_mode(self):
        """Resets all widgets based on the dark theme."""
        default_prefs = DARK_MODE_PREFS

        # 1. Restore Limits
        self._max_speed.set(default_prefs.get("max_speed"))
        self._max_dist.set(default_prefs.get("max_dist"))
        self._max_alt.set(default_prefs.get("max_alt"))
        self._max_wind.set(default_prefs.get("max_wind"))

        # 2. Restore Colors
        for key, _ in self.COLOR_FIELDS:
            default=default_prefs.get(key, "#000000")
            self._prefs[key]=default
            self._swatches[key].configure(bg=default)

        # 3. Restore Fonts
        for key, _ in self.FONT_FIELDS:
            default=default_prefs.get(key, ("Helvetica", 10))
            family_var, size_var, bold_var=self._font_vars[key]
            family_var.set(default[0])
            size_var.set(default[1])
            bold_var.set(len(default) > 2 and default[2] == "bold")
        self._log_var.set(default_prefs.get("log_level", "Info"))

        # 4. Update CSV Checkbox States
        self._csv_extended_var.set(default_prefs.get("csv_extended", False))
        self._csv_derived_var.set(default_prefs.get("csv_derived", True))

        # 5. Update internal state to match the theme
        self._prefs.update(default_prefs)
        self.update_idletasks()

    def _save(self):
        """Saves all current widget values and the selected theme."""
        for key, _ in self.FONT_FIELDS:
            family_var, size_var, bold_var=self._font_vars[key]
            if bold_var.get():
                self._prefs[key]=(family_var.get(), size_var.get(), "bold")
            else:
                self._prefs[key]=(family_var.get(), size_var.get())

        self._prefs["log_level"]=self._log_var.get()
        self._prefs["max_speed"]=int(self._max_speed.get())
        self._prefs["max_dist"]=int(self._max_dist.get())
        self._prefs["max_alt"]=int(self._max_alt.get())
        self._prefs["max_wind"]=int(self._max_wind.get())

        self._prefs["csv_extended"]=self._csv_extended_var.get()
        self._prefs["csv_derived"]=self._csv_derived_var.get()

        self._on_save(self._prefs)
        self.withdraw()

    def show(self):
        self.deiconify()
        self.lift()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: format a single metric value for the dashboard
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(value, fmt_spec: str, unit: str) -> str:
    """Format a telemetry value; returns '—' if value is None."""
    if value is None:
        return "—"
    try:
        if fmt_spec == "s":
            return str(value)
        if fmt_spec == "d":
            return f"{int(value)}{unit}"
        return f"{float(value):{fmt_spec}}{unit}"
    except (TypeError, ValueError):
        return str(value)


# ─────────────────────────────────────────────────────────────────────────────
#  DashboardStrip  –  animated metric tiles above the map
#
#  A horizontal row of labeled metric tiles.
#  Each tile shows a label and a value that updates during playback.
#
# ─────────────────────────────────────────────────────────────────────────────

class DashboardStrip(tk.Frame):
    def __init__(self, parent, prefs: dict, **kw):
        my_logger.debug("Creating Dashboard Strip.")
        bg = prefs["color_panel_bg"]
        super().__init__(parent, bg=bg, **kw)
        self.prefs = prefs
        self._vars: dict[str, tk.StringVar] = {}
        self._labels: dict[str, tk.Label] = {}
        self._build()

    def _build(self):
        prefs = self.prefs
        bg    = prefs["color_panel_bg"]

        for i, (label, key, _, _, _) in enumerate(DASHBOARD_METRICS):
            tile = tk.Frame(self, bg=bg, padx=8, pady=4,
                            relief=tk.FLAT, bd=0)
            tile.grid(row=0, column=i, sticky="nsew", padx=1)
            self.columnconfigure(i, weight=1)

            tk.Label(tile, text=label,
                     bg=bg, fg=prefs["color_label"],
                     font=prefs["font_ui"]).pack()

            var = tk.StringVar(value="—")
            self._vars[key] = var
            label = tk.Label(tile, textvariable=var,
                     bg=bg, fg=prefs["color_value"],
                     font=prefs["font_metric"])
            label.pack()
            self._labels[key] = label

        # Thin accent border at the bottom
        tk.Frame(self, bg=prefs["color_border"], height=1).grid(
            row=1, column=0, columnspan=len(DASHBOARD_METRICS), sticky="ew")

    def update_record(self, record: dict):
        """Push a new telemetry record into the dashboard tiles."""
        for label, key, unit, fmt, limit in DASHBOARD_METRICS:
            value = record.get(key)
            self._vars[key].set(_fmt(value, fmt, unit))
            if limit is not None and isinstance(value, (int, float)):
                max_val = int(self.prefs[limit])
                if value > max_val * 0.9:
                    self._labels[key].config(fg=self.prefs["color_danger"])
                elif value > max_val *0.5:
                    self._labels[key].config(fg=self.prefs["color_warn"])
                else:
                    self._labels[key].config(fg=self.prefs["color_safe"])
            elif label == "Battery" and isinstance(value, (int, float)):
                if value < 25:
                    self._labels[key].config(fg=self.prefs["color_danger"])
                elif value < 50:
                    self._labels[key].config(fg=self.prefs["color_warn"])
                else:
                    self._labels[key].config(fg=self.prefs["color_safe"])

    def clear(self):
        for var in self._vars.values():
            var.set("—")


class FileListPane(tk.Frame):
    """
    FileListPane  –  left panel with persistent fc2 file list

    Scrollable list of fc2 files.  Fires on_select(path) when the user
    double-clicks a row.  The list is persisted across sessions.
    """

    def __init__(self, parent, prefs: dict, on_select, **kw):
        my_logger.debug("Creating File List Pane.")
        bg = prefs["color_bg"]
        super().__init__(parent, bg=bg, **kw)
        self.prefs     = prefs
        self.on_select = on_select
        self._paths: list[list] = []   # parallel to Listbox entries
        self._build()
        self._load_persisted()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build(self):
        prefs = self.prefs
        bg    = prefs["color_bg"]

        # Title bar
        hdr = tk.Frame(self, bg=prefs["color_panel_bg"], pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="FC2 Files",
                 bg=prefs["color_panel_bg"],
                 fg=prefs["color_accent"],
                 font=prefs["font_title"]).pack(side=tk.LEFT, padx=8)

        # Listbox + scrollbar
        list_frame = tk.Frame(self, bg=bg)
        list_frame.pack(fill=tk.BOTH, expand=True)

        sb = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._listbox = tk.Listbox(
            list_frame,
            bg=prefs["color_panel_bg"],
            fg=prefs["color_value"],
            selectbackground=prefs["color_select"],
            selectforeground=prefs["color_value"],
            font=prefs["font_ui"],
            relief=tk.FLAT,
            bd=0,
            activestyle="none",
            yscrollcommand=sb.set,
        )
        sb.config(command=self._listbox.yview)
        self._listbox.pack(fill=tk.BOTH, expand=True)

        # Disabled to avoid conflict with play/pause and to limit accidental
        # re-loads. Use double-click to load a file.
        #self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<Delete>",          self._remove_selected)
        self._listbox.bind("<BackSpace>",       self._remove_selected)
        self._listbox.bind("<Double-Button-1>", self._on_select)

        # Thin status bar showing count
        self._count_var = tk.StringVar(value="0 files")
        tk.Label(self, textvariable=self._count_var,
                 bg=prefs["color_panel_bg"],
                 fg=prefs["color_label"],
                 font=prefs["font_small"]).pack(fill=tk.X, pady=2, padx=4, side=tk.BOTTOM)

    def _refresh_list(self):
        self._listbox.delete(0, tk.END)
        for p in self._paths:
            self._listbox.insert(tk.END, p[1])
            color = self.prefs["color_value"] if p[2] else self.prefs["color_warn"]
            self._listbox.itemconfig(tk.END, fg=color)

    # ── Public API ────────────────────────────────────────────────────────────

    def add_files(self, paths: list[str]):
        """Add one or more paths; duplicates and non-existent files are ignored."""
        added = 0
        for p in paths:
            p = str(Path(p).resolve())
            existing = [entry[0] for entry in self._paths]
            if p in existing:
                my_logger.info("%s is already in the file list. Skipping.", p)
            elif Path(p).exists():
                # Skip files that don't really contain fc2 data.
                try:
                    records = atom2_parser(file_name=p, logger=my_logger)
                except Exception:
                    my_logger.error("%s is not a valid atom2 fc2 file.", p)
                    continue

                my_logger.debug("Adding %s to the file list.", p)
                ts = self._ms_to_datetime_str(atom2_parse_filename(p))
                mappable = any(r.get("GPS Lock") == "Yes" for r in records)

                self._paths.append([p, ts, mappable])
                added += 1
            else:
                my_logger.error("%s does not exist.", p)
        if added:
            self._paths.sort()
            self._save()
            self._update_count()
            self._refresh_list()

    def remove_selected(self):
        self._remove_selected()

    def get_paths(self) -> list[str]:
        return [entry[0] for entry in self._paths]

    def select_path(self, path: str):
        """Programmatically select a row by path."""
        path = str(Path(path).resolve())
        if path in self._paths:
            idx = self._paths.index(path)
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)
            self._listbox.see(idx)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _ms_to_datetime_str(self, ms: int) -> str:
        dt = datetime.fromtimestamp(ms / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _on_select(self, _event=None):
        sel = self._listbox.curselection()
        if sel:
            path = self._paths[sel[0]][0]
            self.on_select(path)

    def _remove_selected(self, _event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        my_logger.info("Deleting item %s: %s", sel[0], self._paths[idx][0])
        self._listbox.delete(idx)
        del self._paths[idx]
        self._save()
        self._update_count()

    def _load_persisted(self):
        # Note that because this is only called at start up we don't
        # need to erase the old list or worry about sorting the new one.
        paths = load_file_list()
        for p in paths:
            my_logger.debug("Adding %s.", p[0])
            self._paths.append(p)
            self._listbox.insert(tk.END, p[1])
            mappable = p[2]
            color = self.prefs["color_value"] if mappable else self.prefs["color_warn"]
            self._listbox.itemconfig(tk.END, fg=color)
        self._update_count()

    def _save(self):
        save_file_list(self._paths)

    def _update_count(self):
        n = len(self._paths)
        self._count_var.set(f"{n} file{'s' if n != 1 else ''}")


class PlaybackControls(tk.Frame):
    """
    PlaybackControls  –  transport bar at the bottom of the map pane

    Slider + transport buttons + speed selector.
    Callbacks injected by the parent so this widget stays decoupled.
    """

    PLAYBACK_SPEEDS = [1, 2, 4, 8, 16]

    def __init__(self, parent, prefs: dict,
                 on_play_pause, on_step_back, on_step_fwd,
                 on_slider, on_speed_change, **kw):
        my_logger.debug("Creating Playback Controls.")
        bg = prefs["color_bg"]
        super().__init__(parent, bg=bg, **kw)
        self.prefs           = prefs
        self._on_play_pause  = on_play_pause
        self._on_step_back   = on_step_back
        self._on_step_fwd    = on_step_fwd
        self._on_slider      = on_slider
        self._on_speed_change= on_speed_change
        self.speed_idx       = 0
        self._playing        = False
        self._build()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build(self):
        prefs = self.prefs
        bg    = prefs["color_button_bg"]

        # Progress label row
        lbl_row = tk.Frame(self, bg=bg)
        lbl_row.pack(fill=tk.X, padx=8, pady=(4, 0))

        self._progress_var = tk.StringVar(value="0 / 0")
        tk.Label(lbl_row, textvariable=self._progress_var,
                 bg=bg, fg=prefs["color_label"],
                 font=prefs["font_small"]).pack(side=tk.RIGHT)

        self._time_var = tk.StringVar(value="00:00")
        tk.Label(lbl_row, textvariable=self._time_var,
                 bg=bg, fg=prefs["color_value"],
                 font=prefs["font_small"]).pack(side=tk.LEFT)

        # Slider
        self._slider_var = tk.IntVar(value=0)
        style = ttk.Style()
        try:
            style.configure("Playback.Horizontal.TScale",
                            background=bg,
                            troughcolor=prefs["color_border"],
                            slidercolor=prefs["color_accent"])
        except Exception as e:
            my_logger.error(str(e))

        self._slider = ttk.Scale(
            self, from_=0, to=1,
            variable=self._slider_var,
            orient=tk.HORIZONTAL,
            command=self._slider_moved,
            style="Playback.Horizontal.TScale",
        )
        self._slider.pack(fill=tk.X, padx=10, pady=4)
        self._slider.state(["disabled"])

        # Button row
        btn_row = tk.Frame(self, bg=bg)
        btn_row.pack(pady=(0, 4))

        use_emoji = (PLATFORM_SYSTEM == "Darwin")

        def mkbtn(text, cmd):

            if use_emoji:
                # The color prefs don't work with TKinter on Darwin right now.
                return tk.Button(
                    btn_row, text=text, command=cmd,
                )

            return tk.Button(
                btn_row, text=text, command=cmd,
                bg=prefs["color_button_bg"], fg=prefs["color_button_fg"],
                relief=tk.FLAT, font=tuple(prefs["font_ui"]),
                cursor="hand2", padx=2,
                activebackground=prefs["color_button_bg"],
                activeforeground=prefs["color_button_fg"]
            )

        self._btn_slower = mkbtn("⏮️" if use_emoji else "Slower", self._slower)
        self._btn_back   = mkbtn("⏪" if use_emoji else "<<",  self._step_back)
        self._btn_play   = mkbtn("▶️" if use_emoji else ">",   self._play_pause)
        self._btn_fwd    = mkbtn("⏩" if use_emoji else ">>",  self._step_fwd)
        self._btn_faster = mkbtn("⏭️" if use_emoji else "Faster", self._faster)

        for b in (self._btn_slower, self._btn_back, self._btn_play,
                  self._btn_fwd,  self._btn_faster):
            b.pack(side=tk.LEFT, padx=2)

        # Speed selector
        speed_row = tk.Frame(self, bg=bg)
        speed_row.pack(pady=(0, 6))

        self._speed_var = tk.StringVar(value="1×")
        for i, spd in enumerate(self.PLAYBACK_SPEEDS):
            rb = tk.Radiobutton(
                speed_row, text=f"{spd}×",
                variable=self._speed_var, value=f"{spd}×",
                command=lambda i=i: self._set_speed(i),
                bg=bg, fg=prefs["color_label"],
                selectcolor=bg,
                activebackground=bg,
                activeforeground=prefs["color_accent"],
                font=prefs["font_ui"],
                relief=tk.FLAT, padx=4,
            )
            rb.pack(side=tk.LEFT)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_range(self, total: int):
        """Call after loading a file to configure the slider range."""
        self._slider.configure(to=max(1, total - 1))
        self._slider.state(["!disabled"])
        self._progress_var.set(f"1 / {total}")
        self._slider_var.set(0)

    def set_position(self, idx: int, total: int, elapsed_us: float):
        self._slider_var.set(idx)
        self._progress_var.set(f"{idx + 1} / {total}")
        elapsed_s  = elapsed_us / 1_000_000
        m, s       = divmod(int(elapsed_s), 60)
        self._time_var.set(f"{m:02d}:{s:02d}")

    def set_playing(self, playing: bool):
        self._playing = playing
        if playing:
            self._btn_play.configure(
                text="⏸️" if PLATFORM_SYSTEM == "Darwin" else "||",
            )
        else:
            self._btn_play.configure(
                text="▶️" if PLATFORM_SYSTEM == "Darwin" else ">",
            )

    def current_speed(self) -> int:
        return self.PLAYBACK_SPEEDS[self.speed_idx]

    # ── Internal ─────────────────────────────────────────────────────────────

    def _play_pause(self):
        self._on_play_pause()

    def _step_back(self):
        self._on_step_back()

    def _step_fwd(self):
        self._on_step_fwd()

    def _slower(self):
        self._set_speed(self.speed_idx - 1)

    def _faster(self):
        self._set_speed(self.speed_idx + 1)

    def _set_speed(self, idx: int):
        self.speed_idx = max(0, min(len(self.PLAYBACK_SPEEDS) - 1, idx))
        self._speed_var.set(f"{self.PLAYBACK_SPEEDS[self.speed_idx]}×")
        self._on_speed_change(self.speed_idx)

    def _slider_moved(self, val):
        idx = int(float(val))
        self._on_slider(idx)


class MapPane(tk.Frame):
    """
    MapPane  –  the right pane containing dashboard + map + controls

    Right-side pane.  Top: DashboardStrip.  Middle: map (tkintermapview).
    Bottom: PlaybackControls.

    If tkintermapview is unavailable, a placeholder canvas is shown instead.
    """

    def __init__(self, parent, prefs: dict, playback_callbacks: dict, **kw):
        my_logger.debug("Creating Map Pane.")
        bg = prefs["color_bg"]
        super().__init__(parent, bg=bg, **kw)
        self.prefs = prefs

        # ── Dashboard ────────────────────────────────────────────────────────
        self.dashboard = DashboardStrip(self, prefs)
        self.dashboard.pack(fill=tk.X)

        # ── Map ──────────────────────────────────────────────────────────────
        map_container = tk.Frame(self, bg=bg)
        map_container.pack(fill=tk.BOTH, expand=True)

        if HAS_MAP:
            self.map_widget = tkintermapview.TkinterMapView(
                map_container, corner_radius=0)
            self.map_widget.pack(fill=tk.BOTH, expand=True)
        else:
            # Fallback placeholder
            self.map_widget = None
            tk.Label(map_container,
                     text="Map unavailable.\nInstall tkintermapview to enable.",
                     bg=bg, fg=prefs["color_label"],
                     font=prefs["font_ui"]).pack(expand=True)

        # ── Playback controls ─────────────────────────────────────────────
        self.controls = PlaybackControls(
            self, prefs,
            on_play_pause  = playback_callbacks["play_pause"],
            on_step_back   = playback_callbacks["step_back"],
            on_step_fwd    = playback_callbacks["step_fwd"],
            on_slider      = playback_callbacks["slider"],
            on_speed_change= playback_callbacks["speed_change"],
        )
        self.controls.pack(fill=tk.X, side=tk.BOTTOM)

        # ── Internal map state ────────────────────────────────────────────
        self._path_line    = None
        self._drone_marker = None
        self._home_marker  = None
        self._drone_cache  = {}      # heading → ImageTk.PhotoImage
        self._drone_heading= -1

    # ── Map drawing helpers ───────────────────────────────────────────────────

    def draw_path(self, coords: list[tuple]):
        """Draw (or redraw) the full flight path on the map."""
        if not self.map_widget:
            return
        if self._path_line:
            self._path_line.delete()
            self._path_line = None
        if self._drone_marker:
            self._drone_marker.delete()
            self._drone_marker = None
        if self._home_marker:
            self._home_marker.delete()
            self._home_marker = None
        self._drone_cache.clear()
        self._drone_heading = -1

        if len(coords) >= 2:
            self.map_widget.delete_all_path()
            self._path_line = self.map_widget.set_path(
                coords, color=self.prefs["color_path"], width=4)

    def fit_to_path(self, coords: list[tuple]):
        """Zoom/pan the map to show the entire flight path."""
        if not self.map_widget or not coords:
            return
        lats = [c[0] for c in coords]
        lons = [c[1] for c in coords]
        self.map_widget.fit_bounding_box(
            (max(lats), min(lons)), (min(lats), max(lons)))

    def update_markers(self, lat, lon, home_lat, home_lon, heading: float):
        """Move drone and home markers to the current position."""
        if not self.map_widget:
            return
        if not is_valid_latlon(lat, lon):
            return

        # Home marker
        if is_valid_latlon(home_lat, home_lon):
            if self._home_marker is None:
                self._home_marker = self.map_widget.set_marker(
                    home_lat, home_lon,
                    icon=self._make_home_icon() if HAS_PIL else None,
                )
            else:
                self._home_marker.set_position(home_lat, home_lon)

        # Drone marker (cached per 5° step)
        h5 = round(heading / 5) * 5
        if HAS_PIL and h5 not in self._drone_cache:
            self._drone_cache[h5] = self._make_drone_icon(h5)
        icon = self._drone_cache.get(h5)

        if self._drone_marker is None:
            self._drone_marker = self.map_widget.set_marker(
                lat, lon, icon=icon)
            self._drone_heading = h5
        else:
            self._drone_marker.set_position(lat, lon)
            if h5 != self._drone_heading:
                self._drone_heading = h5
                if icon:
                    self._drone_marker.change_icon(icon)

    # ── Icon factories (require Pillow) ───────────────────────────────────────

    def _make_drone_icon(self, heading) -> "ImageTk.PhotoImage | None":
        if not HAS_PIL:
            return None
        size, pad = 21, 4
        tsize = size + pad * 2
        img   = Image.new("RGBA", (tsize, tsize), (0, 0, 0, 0))
        draw  = ImageDraw.Draw(img)
        cx = cy = tsize // 2
        draw.polygon(
            [(cx, pad),
             (cx + size // 2, pad + size),
             (cx,             cy + pad),
             (cx - size // 2, pad + size)],
            fill=self.prefs["color_danger"],
            outline=self.prefs["color_border"],
        )
        img = img.rotate(-heading, resample=Image.BICUBIC, expand=False)
        return ImageTk.PhotoImage(img)

    def _make_home_icon(self) -> "ImageTk.PhotoImage | None":
        if not HAS_PIL:
            return None
        size = 22
        img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cc   = size // 2

        if self.prefs["font_marker"] == "":
            # Draw a simple house icon.
            draw.rectangle([(4, 0), (7, cc)],
                           fill=self.prefs["color_border"],
                           outline=self.prefs["color_border"])
            draw.polygon([(cc, 0), (size, cc), (0, cc)],
                         fill=self.prefs["color_warn"],
                         outline=self.prefs["color_border"])
            draw.rectangle([(0, cc), (size, size)],
                           fill=self.prefs["color_warn"],
                           outline=self.prefs["color_border"],
                           width=2)
            draw.rectangle([(cc - 3, cc), (cc + 3, size)],
                           fill=self.prefs["color_border"])
            draw.rectangle([(cc - 2, cc - size // 3), (cc + 2, cc - size // 3 + 4)],
                           fill=self.prefs["color_border"],
                           outline=self.prefs["color_border"])
        else:
            # Use a letter "H" in a circle.
            font=ImageFont.truetype(self.prefs["font_marker"], size)
            draw.ellipse([(0,0),(size,size)], fill=self.prefs["color_bg"],
                         outline=self.prefs["color_path"])
            draw.text((cc, cc), "H", font=font,
                      fill=self.prefs["color_path"],
                      anchor="mm")

        return ImageTk.PhotoImage(img)


# ─────────────────────────────────────────────────────────────────────────────
#  FlightSummaryWindow  –  pop-up showing stats for the loaded file
#
#  Displays min/max statistics for all basic fields of the currently
#  loaded fc2 file.  Populated by calling refresh(records).
# ─────────────────────────────────────────────────────────────────────────────

class FlightSummaryWindow(tk.Toplevel):
    """
    Flight summary pop-up built around a ttk.Treeview table.

    Columns
    -------
    Field   – human-readable field name
    Min     – minimum value across all records
    Max     – maximum value across all records
    Unit    – unit string

    The table covers every numeric field found in BASIC_DATA plus the
    derived speed and distance fields.  A header strip above the table
    shows file name, total record count, and flight duration.

    Clicking a column header sorts the table by that column (toggle
    ascending / descending).  The window is resizable; columns resize
    with it.
    """

    # Fields to summarise.  Tuple: (data_key, display_name, unit)
    # Add or remove rows here without touching anything else.
    SUMMARY_FIELDS = [
        ("alt (m)",                    "Altitude",        "m"),
        ("heading (deg)",              "Heading",         "°"),
        ("pitch angle (deg)",          "Pitch",           "°"),
        ("bank (deg)",                 "Roll",            "°"),
        ("3d Derived Speed (m/s)",     "3-D Speed",       "m/s"),
        ("3d Travelled Distance (m)",  "Distance Travelled",  "m"),
        ("3d Distance Distance (m)",   "Distance to Home",   "m"),
        ("Wind Speed (m/s)",           "Wind Speed",      "m/s"),
        ("Wind Direction (deg)",       "Wind Direction",  "°"),
        ("Battery Level (%)",          "Battery Level",   "%"),
        ("Battery (mv)",               "Battery Voltage", "mV"),
        ("Battery Current (ma)",       "Battery Current", "mA"),
        ("Battery Temp (c)",           "Battery Temp", "C"),
        ("Satellites",                 "Satellites",      ""),
        ("Signal Strength (%)",        "Signal Strength", "%"),
    ]

    # Column definitions: (treeview id, header label, anchor, min width, stretch)
    _COLUMNS = [
        ("field", "Field",  tk.W,  80, True),
        ("unit",  "Unit",   tk.E,  40, True),
        ("min",   "Min",    tk.E,   80, True),
        ("max",   "Max",    tk.E,   80, True),
    ]

    def __init__(self, parent, prefs: dict):
        my_logger.debug("Creating Flight Summary Window.")

        super().__init__(parent)
        self.prefs = prefs
        self.title("Flight Summary")
        self.resizable(True, True)
        self.transient(parent)

        x=parent.winfo_x() + (parent.winfo_width()  - 760)  // 2
        y=parent.winfo_y() + (parent.winfo_height() - 420) // 2
        self.geometry(f"760x420+{x}+{y}")

        self.configure(bg=prefs["color_bg"])

        self._sort_col = "field"
        self._sort_asc = True
        self._rows = None

        self._build()

        self.protocol("WM_DELETE_WINDOW", lambda: self.withdraw())
        if PLATFORM_SYSTEM == "Darwin":
            self.bind("<Command-w>", lambda e: self.withdraw())
        else:
            self.bind("<Control-w>", lambda e: self.withdraw())

    # ── Construction ──────────────────────────────────────────────────────────

    def _build(self):
        p = self.prefs
        bg       = p["color_bg"]
        panel_bg = p["color_panel_bg"]
        fg       = p["color_value"]
        label_fg = p["color_label"]
        accent   = p["color_accent"]
        border   = p["color_border"]
        font_ui  = p["font_ui"]
        font_sm  = p["font_small"]
        font_ttl = p["font_title"]

        # ── Header strip ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=panel_bg, pady=6)
        hdr.pack(fill=tk.X)

        self._title_var = tk.StringVar(value="No file loaded.")
        tk.Label(hdr, textvariable=self._title_var,
                 bg=panel_bg, fg=accent,
                 font=font_ttl, anchor="w").pack(side=tk.LEFT, padx=10)

        self._meta_var = tk.StringVar(value="")
        tk.Label(hdr, textvariable=self._meta_var,
                 bg=panel_bg, fg=accent,
                 font=font_sm, anchor="e").pack(side=tk.RIGHT, padx=10)

        tk.Frame(self, bg=border, height=1).pack(fill=tk.X)

        # ── Treeview + scrollbars ─────────────────────────────────────────
        tree_frame = tk.Frame(self, bg=bg)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        vsb = tk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = tk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        # Style the Treeview to match the app colour palette.
        style = ttk.Style(self)
        style_name = "Summary.Treeview"
        style.configure(style_name,
                        background=panel_bg,
                        foreground=fg,
                        fieldbackground=panel_bg,
                        rowheight=22,
                        font=font_ui)
        style.configure(f"{style_name}.Heading",
                        background=panel_bg,
                        foreground=label_fg,
                        relief=tk.FLAT,
                        font=font_ui)
        style.map(style_name,
                  background=[("selected", p["color_select"])],
                  foreground=[("selected", fg)])
        style.map(f"{style_name}.Heading",
                  background=[("active", border)])

        col_ids = [c[0] for c in self._COLUMNS]
        self._tree = ttk.Treeview(
            tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="browse",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            style=style_name,
        )
        vsb.config(command=self._tree.yview)
        hsb.config(command=self._tree.xview)
        self._tree.pack(fill=tk.BOTH, expand=True)

        # Configure each column and bind header click for sorting.
        for col_id, label, anchor, minwidth, stretch in self._COLUMNS:
            self._tree.heading(col_id, text=label,
                               command=lambda c=col_id: self._sort_by(c))
            self._tree.column(col_id, anchor=anchor,
                              minwidth=minwidth, width=minwidth, stretch=stretch)

        # Alternating row colours
        self._tree.tag_configure("odd",  background=panel_bg)
        self._tree.tag_configure("even", background=bg)

        # ── Bottom bar ────────────────────────────────────────────────────
        tk.Frame(self, bg=border, height=1).pack(fill=tk.X)
        bot = tk.Frame(self, bg=panel_bg, pady=4)
        bot.pack(fill=tk.X)

        self._footer_var = tk.StringVar(value="")
        tk.Label(bot, textvariable=self._footer_var,
                 bg=panel_bg, fg=accent,
                 font=font_sm, anchor="w").pack(side=tk.LEFT, padx=10)

        if PLATFORM_SYSTEM == "Darwin":
            tk.Button(bot, text="Close",
                      command=self.withdraw,
                      ).pack(side=tk.RIGHT, padx=8)
        else:
            tk.Button(bot, text="Close",
                      command=self.withdraw,
                      font=font_ui,
                      bg=p.get("color_button_bg", panel_bg),
                      fg=p.get("color_button_fg", fg),
                      relief=tk.FLAT, padx=8
                      ).pack(side=tk.RIGHT, padx=8)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, records: list[dict], file_name: str = ""):
        """Recompute statistics from records and repopulate the table."""

        # Clear existing rows.
        self._tree.delete(*self._tree.get_children())

        if not records:
            self._title_var.set("No file loaded.")
            self._meta_var.set("")
            self._footer_var.set("")
            return

        fname = Path(file_name).name if file_name else "unknown"
        self.title(f"Flight Summary — {fname}")
        self._title_var.set(fname)

        # ── Flight duration ───────────────────────────────────────────────
        elapsed_vals = [r.get("elapsed (us)", 0) for r in records
                        if isinstance(r.get("elapsed (us)"), (int, float))]
        if elapsed_vals:
            duration_s = (max(elapsed_vals) - min(elapsed_vals)) / 1_000_000
            m, s = divmod(int(duration_s), 60)
            h, m = divmod(m, 60)
            dur_str = (f"{h}h {m:02d}m {s:02d}s" if h
                       else f"{m}m {s:02d}s")
        else:
            dur_str = "unknown"

        self._meta_var.set(f"Duration: {dur_str}   Records: {len(records):,}")

        # ── Build rows ────────────────────────────────────────────────────
        rows = []  # list of (field_label, unit, min, max, mean, range, sort_key)
        for data_key, display_name, unit in self.SUMMARY_FIELDS:
            vals = [r[data_key] for r in records
                    if isinstance(r.get(data_key), (int, float))]

            if not vals:
                continue
            vmin  = min(vals)
            vmax  = max(vals)
            vmean = sum(vals) / len(vals)
            vrange = vmax - vmin
            rows.append({
                "field": display_name,
                "unit":  unit,
                "min":   vmin,
                "max":   vmax,
                "mean":  vmean,
                "range": vrange,
            })

        # Store for re-sort without re-computing.
        self._rows = rows
        self._populate_tree(rows)

        # ── Footer ───────────────────────────────────────────────────────
        gps_count = sum(1 for r in records if r.get("GPS Lock") == "Yes")
        gps_pct   = 100 * gps_count / len(records) if records else 0
        self._footer_var.set(
            f"GPS lock: {gps_count:,} of {len(records):,} records  ({gps_pct:.0f}%)"
        )

    def show(self):
        self.deiconify()
        self.lift()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _populate_tree(self, rows: list[dict]):
        """Insert rows into the Treeview, applying sort and alternating colours."""
        self._tree.delete(*self._tree.get_children())

        # Determine sort key and direction.
        col  = self._sort_col
        asc  = self._sort_asc
        numeric_cols = {"min", "max", "mean", "range"}

        def sort_key(r):
            v = r.get(col, "")
            if col in numeric_cols:
                return v if isinstance(v, (int, float)) else float("-inf")
            return str(v).lower()

        sorted_rows = sorted(rows, key=sort_key, reverse=not asc)

        # Update heading arrows.
        for col_id, label, *_ in self._COLUMNS:
            arrow = (" ▲" if asc else " ▼") if col_id == col else ""
            self._tree.heading(col_id, text=label + arrow)

        for i, row in enumerate(sorted_rows):
            tag = "even" if i % 2 == 0 else "odd"
            self._tree.insert("", tk.END, tags=(tag,), values=(
                row["field"],
                row["unit"],
                self._fmtn(row["min"]),
                self._fmtn(row["max"]),
            ))

    def _sort_by(self, col_id: str):
        """Toggle sort direction when the same column is clicked again."""
        if self._sort_col == col_id:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col_id
            self._sort_asc = True
        if hasattr(self, "_rows"):
            self._populate_tree(self._rows)

    @staticmethod
    def _fmtn(v) -> str:
        """Format a numeric value for display: integers without decimals."""
        if not isinstance(v, (int, float)):
            return "—"
        if v == int(v) and abs(v) < 10_000:
            return f"{int(v)}"
        return f"{v:.2f}"


# ─────────────────────────────────────────────────────────────────────────────
#  CSV export helper
#
#   Write records to a CSV file alongside the source file (or in destination).
#   Returns the path of the written CSV.
# ─────────────────────────────────────────────────────────────────────────────

def export_csv(file_name: str, records: list[dict],
               extended: bool = False, derived: bool = True,
               destination: str | None = None) -> str:
    my_logger.debug("Exporting %s to %s.", file_name, destination)
    base_name  = Path(file_name).stem
    directory  = destination if destination else str(Path(file_name).parent)
    csv_path   = os.path.join(directory, f"{base_name}.csv")

    header = (
        BASIC_DATA
        + (EXTENDED_DATA if extended else [])
        + (DERIVED_DATA  if derived  else [])
    )

    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for rec in records:
            writer.writerow([rec.get(field, "") for field in header])

    my_logger.info("CSV written: %s", csv_path)
    return csv_path


# ─────────────────────────────────────────────────────────────────────────────
#  HelpWindow  –  tabbed help dialog
#
#  Four tabs: Overview, Keyboard Shortcuts, Windows, Preferences
#  Opens via Help > Help… (F1 on non-Mac, Command+? on Mac).
# ─────────────────────────────────────────────────────────────────────────────

class HelpWindow(tk.Toplevel):
    """
    Tabbed help window with sections for:
      • Overview / Quick Start
      • Keyboard Shortcuts
      • Window descriptions (Main, Flight Summary, Log, Preferences)
    """

    # ── Content ───────────────────────────────────────────────────────────────

    _SHORTCUTS = [
        # (key, description)
        # File
        ("Ctrl+O  /  ⌘O",     "Import FC2 file(s)"),
        ("Ctrl+E  /  ⌘E",     "Export current file to CSV"),
        ("Ctrl+,  /  ⌘,",     "Open Preferences"),
        ("Ctrl+Q  /  ⌘Q",     "Quit"),
        # View
        ("Ctrl+F  /  ⌘F",     "Show / hide Flight Summary"),
        ("Ctrl+L  /  ⌘L",     "Show / hide Log window"),
        ("Ctrl+0  /  ⌘0",     "Fit map to flight path"),
        # Playback
        ("Space",              "Play / Pause"),
        ("→  (Right arrow)",   "Step forward 100 records"),
        ("←  (Left arrow)",    "Step back 100 records"),
        # File list
        ("Delete / Backspace", "Remove selected file from list"),
        ("Double-click",       "Load selected file"),
    ]

    _WINDOWS = [
        (
            "Main Window",
            """\
The main window is divided into two panes separated by a draggable sash.

Left pane – FC2 File List
  • Lists all FC2 flight-log files that have been imported.
  • Files that can be displayed on the map are shown in the "values" color.
    Files that have no valid GPS record are displayed with the "warning"
    color.
  • The list is saved on disk and restored when the app restarts.
  • Double-click a file to load it.
  • Press Delete or Backspace to remove a file from the list
    (the file itself is not deleted).
  • Use File > Import FC2 File(s) or File > Import Directory to add files.

Right pane – Dashboard, Map, and Playback Controls
  • Dashboard Strip (top): shows live telemetry for the current record —
    speed, altitude, distance, heading, battery level, satellite count,
    wind speed, and flight mode. Some values change color (safe / warning /
    danger) as they approach their configured limits.
  • Map (middle): displays the complete flight path as a colored line.
    A drone icon (arrow) shows the current position and heading.
    A house icon marks the home point. Requires the tkintermapview package.
  • Playback Controls (bottom): slider, transport buttons (step back, play/pause,
    step forward), speed selector (1× – 16×), and an elapsed-time readout.

Status bar (very bottom): shows the last operation or any error messages.""",
        ),
        (
            "Flight Summary",
            """\
Opened via View > Flight Summary… or Ctrl+F / ⌘F.

Displays a sortable table of statistics for the currently loaded file.

Columns
  • Field    – telemetry field name (e.g. Altitude, Speed, Battery Level)
  • Unit     – measurement unit (m, m/s, %, etc.)
  • Min      – minimum value recorded during the flight
  • Max      – maximum value recorded during the flight

Header strip
  • Shows the file name, total record count, and flight duration.

Footer bar
  • Reports how many records had a valid GPS lock, and what percentage
    of the flight that represents.

Clicking any column header sorts the table by that column.
Clicking the same header again reverses the sort order (▲ / ▼ arrow shown).

The window updates automatically whenever a new file is loaded
while the Flight Summary is visible.""",
        ),
        (
            "Log Window",
            """\
Opened via View > Log… or Ctrl+L / ⌘L.

Shows a running log of application events: file loads, parse results,
CSV exports, errors, and internal debug messages.

Log levels (set in Preferences > Logging):
  • Error   – only serious failures
  • Warning – failures and significant warnings
  • Info    – normal operational messages (default)
  • Debug   – verbose developer-level messages

The log is useful for diagnosing parse errors or unexpected behavior.
Log entries are displayed in the window and also sent to the standard output
when the application is launched from a terminal window.

Log entries are not saved to disk.""",
        ),
        (
            "Preferences",
            """\
Opened via File > Preferences… or Ctrl+, / ⌘,.

Gauge Limits
  • Max Dist   – the distance (meters) from the home point considered dangerous.
  • Max Speed  – the speed (m/s) of the drone that is considered hazardous.
  • Max Alt    – the altitude (meters) that is considered hazardous.
  • Max Wind   – the wind speed (m/s) that is considered hazardous.

  Gauges transition through green → amber → red as values approach their limit.

Colors
  • Customize every color used in the application — background, text,
    accent, borders, safe/warning/danger indicators, and the flight-path
    color on the map.
  • Click "Choose…" next to any swatch to pick a new color.

Fonts
  • Set the font family, size, and bold style for four text roles:
    Label Font, Title Font, Small Font, and Gauge Font.

CSV Export Options
  • Include Extended Data – adds extra raw fields from the FC2 file to CSV output.
  • Include Derived Data  – adds computed fields (speed, distance, etc.) to CSV output.

Logging
  • Sets the verbosity of the Log window (Error / Warning / Info / Debug).

Quick-theme buttons
  • Light Mode – resets all colors and fonts to the built-in light theme.
  • Dark Mode  – resets all colors and fonts to the built-in dark theme.

Note: most changes take effect after restarting the application.""",
        ),
    ]

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(self, parent, prefs: dict):
        my_logger.debug("Creating Help Window.")
        super().__init__(parent)
        self.title("Help – Atom 2 Flight Log Viewer")
        self.resizable(True, True)
        self.transient(parent)
        self.prefs = prefs

        x = parent.winfo_x() + (parent.winfo_width()  - 680) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 560) // 2
        self.geometry(f"680x600+{x}+{y}")
        self.minsize(500, 400)

        self.configure(bg=prefs["color_bg"])
        self._build()
        self.protocol("WM_DELETE_WINDOW", lambda: self.withdraw())
        if PLATFORM_SYSTEM == "Darwin":
            self.bind("<Command-w>", lambda e: self.withdraw())
        else:
            self.bind("<Control-w>", lambda e: self.withdraw())

    def _build(self):
        bg       = self.prefs["color_bg"]
        panel_bg = self.prefs["color_panel_bg"]
        fg       = self.prefs["color_value"]
        label_fg = self.prefs["color_label"]
        accent   = self.prefs["color_accent"]
        border   = self.prefs["color_border"]
        font_ui  = self.prefs["font_ui"]
        font_ttl = self.prefs["font_title"]

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=panel_bg, pady=8)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Atom 2 Flight Log Viewer — Help",
                 bg=panel_bg, fg=accent,
                 font=font_ttl).pack(side=tk.LEFT, padx=12)
        tk.Frame(self, bg=border, height=1).pack(fill=tk.X)

        # ── Close button ──────────────────────────────────────────────────
        tk.Frame(self, bg=border, height=1).pack(fill=tk.X, side=tk.BOTTOM)
        bot = tk.Frame(self, bg=panel_bg, pady=6)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Button(bot, text="Close",
                  command=self.withdraw,
                  font=font_ui,
                  bg=self.prefs.get("color_button_bg", panel_bg),
                  fg=self.prefs.get("color_button_fg", fg),
                  relief=tk.FLAT, padx=12
                  ).pack(side=tk.RIGHT, padx=10)

        # ── Notebook ──────────────────────────────────────────────────────
        style = ttk.Style(self)
        style.configure("Help.TNotebook",        background=bg)
        style.configure("Help.TNotebook.Tab",    background=panel_bg,
                        foreground=label_fg, padding=[8, 4])
        style.map("Help.TNotebook.Tab",
                  background=[("selected", bg)],
                  foreground=[("selected", fg)])

        nb = ttk.Notebook(self, style="Help.TNotebook")
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Tab 1: Overview
        nb.add(self._make_text_tab(nb, self._overview_text()),
               text="Quick Start")

        # Tab 2: Keyboard Shortcuts
        nb.add(self._make_shortcuts_tab(nb), text="Keyboard Shortcuts")

        # Tab 3: Windows (sub-tabs per window)
        nb.add(self._make_windows_tab(nb), text="Windows")

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _make_text_tab(self, parent, text: str) -> tk.Frame:
        """Return a frame containing a read-only scrolled Text widget."""
        p      = self.prefs
        bg     = p["color_panel_bg"]
        fg     = p["color_value"]

        frame = tk.Frame(parent, bg=bg)
        sb    = tk.Scrollbar(frame, orient=tk.VERTICAL)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        txt = tk.Text(frame,
                      bg=bg, fg=fg,
                      font=p["font_ui"],
                      relief=tk.FLAT, bd=0,
                      wrap=tk.WORD,
                      padx=14, pady=10,
                      yscrollcommand=sb.set,
                      state=tk.NORMAL,
                      cursor="arrow")
        sb.config(command=txt.yview)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, text)
        txt.configure(state=tk.DISABLED)
        return frame

    def _make_shortcuts_tab(self, parent) -> tk.Frame:
        """Return a frame with a two-column shortcut table."""
        p        = self.prefs
        bg       = p["color_panel_bg"]
        fg       = p["color_value"]
        accent   = p["color_accent"]
        border   = p["color_border"]
        font_ui  = p["font_ui"]

        outer = tk.Frame(parent, bg=bg)

        # Scrollable canvas for the table
        canvas = tk.Canvas(outer, bg=bg, bd=0, highlightthickness=0)
        sb     = tk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(canvas, bg=bg)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(win_id, width=event.width)

        canvas.bind("<Configure>", _on_configure)

        # Header row
        tk.Label(inner, text="Shortcut", font=p["font_title"],
                 bg=bg, fg=accent, anchor="w",
                 width=22).grid(row=0, column=0, sticky="w", padx=(14, 4), pady=(10, 4))
        tk.Label(inner, text="Action", font=p["font_title"],
                 bg=bg, fg=accent, anchor="w").grid(
                 row=0, column=1, sticky="w", padx=4, pady=(10, 4))

        tk.Frame(inner, bg=border, height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=2)

        for i, (key, desc) in enumerate(self._SHORTCUTS):
            row_bg = bg if i % 2 == 0 else p["color_bg"]
            tk.Label(inner, text=key, font=font_ui,
                     bg=row_bg, fg=fg, anchor="w",
                     width=22).grid(row=i + 2, column=0,
                                    sticky="w", padx=(14, 4), pady=2)
            tk.Label(inner, text=desc, font=font_ui,
                     bg=row_bg, fg=fg, anchor="w").grid(
                     row=i + 2, column=1, sticky="w", padx=4, pady=2)

        return outer

    def _make_windows_tab(self, parent) -> tk.Frame:
        """Return a frame with a sub-notebook, one tab per window."""
        p  = self.prefs
        bg = p["color_bg"]

        outer = tk.Frame(parent, bg=bg)

        style = ttk.Style(outer)
        style.configure("Sub.TNotebook",      background=bg)
        style.configure("Sub.TNotebook.Tab",  background=p["color_panel_bg"],
                        foreground=p["color_label"], padding=[6, 3])
        style.map("Sub.TNotebook.Tab",
                  background=[("selected", p["color_panel_bg"])],
                  foreground=[("selected", p["color_value"])])

        sub_nb = ttk.Notebook(outer, style="Sub.TNotebook")
        sub_nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for title, content in self._WINDOWS:
            tab = self._make_text_tab(sub_nb, content)
            sub_nb.add(tab, text=title)

        return outer

    # ── Content helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _overview_text() -> str:
        acc = "⌘" if PLATFORM_SYSTEM == "Darwin" else "Ctrl+"
        return f"""\
Welcome to the Atom 2 Flight Log Viewer & Exporter.

QUICK START

1. Import files
   • Use File > Import FC2 File(s) ({acc}O) to add one or more .fc2 log files,
     or File > Import Directory to add every .fc2 file in a folder.
   • Files are remembered and restored the next time you open the app.

2. Load a file
   • Double-click any file in the left-hand list to parse and display it.
   • The map will draw the full flight path and zoom to fit it.

3. Explore the flight
   • Use the playback controls at the bottom to step through the flight
     record by record, or press Space to play / pause.
   • Use the speed selector (1× – 16×) to accelerate playback.
   • The dashboard tiles at the top update in real time.

4. View statistics
   • Open View > Flight Summary ({acc}F) for a sortable table of min/max
     values for every telemetry channel.

5. Export to CSV
   • Use File > Export Current File to CSV ({acc}E) to save the loaded
     flight as a spreadsheet.
   • File > Export All Files to CSV processes your entire file list at once.

6. Customize
   • File > Preferences ({acc},) lets you change colors, fonts, gauge
     limits, and CSV export options.

For more detail on each window or keyboard shortcut, see the other tabs.
"""

    def show(self):
        self.deiconify()
        self.lift()


# ─────────────────────────────────────────────────────────────────────────────
#  Main application window
# ─────────────────────────────────────────────────────────────────────────────

class Atom2Viewer(tk.Tk):
    """
    Top-level window.  Owns the menu bar, the horizontal PanedWindow that
    splits the file-list pane from the map pane, and all playback state.
    """

    PLAYBACK_INCREMENT = [1, 1, 2, 4, 8]   # record steps per tick at each speed index

    def __init__(self):
        my_logger.debug("Creating top level window.")
        super().__init__()

        self.prefs = load_prefs()

        my_logger.setLevel(mwhlogging.LOG_LEVEL_MAP[self.prefs["log_level"]])

        self.title("Atom 2 Flight Log Viewer")
        self.configure(bg=self.prefs["color_bg"])
        self.minsize(900, 600)
        self.geometry(self.prefs.get("window_geometry", "1400x860"))

        # ── Pop-up Windows ────────────────────────────────────────────────
        self._summary_window = None
        self._preferences_window = None
        self._help_window = None

        # ── Playback state ────────────────────────────────────────────────
        self.records:     list[dict] = []
        self.records_len: int        = 0
        self.coords:      list[tuple]= []
        self.current_file: str       = ""
        self.current_idx:  int       = 0
        self.playing:      bool      = False
        self.pending_update: bool    = False
        self.speed_idx:    int       = 0
        self._stop_event             = threading.Event()
        self._playback_thread        = None

        # ── All-records cache (for CSV export) ────────────────────────────
        # atom2_parser is called once; we keep all records (not just GPS-locked)
        self._all_records: list[dict] = []

        self._apply_styles()
        self._build_ui()

        my_logger.debug("After _build_ui")

        # Attach logger window now that Tk root exists
        my_logger.configure_logging(
            tk_parent=self,
            tk_menubar=self._menubar,
            tk_title="Atom 2 Viewer Log",
            tk_settings=(self.prefs["color_bg"], self.prefs["color_value"],
                         "Courier New", 12)
        )

        my_logger.debug("After configure logging.")

        my_logger.info("Platform: %s", PLATFORM_SYSTEM)

        # macOS: double-click on .fc2 in Finder
        if PLATFORM_SYSTEM == "Darwin":
            self.createcommand("::tk::mac::OpenDocument", self._mac_open)
            self.createcommand("tkAboutDialog",           self._show_about)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.createcommand("tk::mac::Quit", self._on_close)
        except Exception as e:
            my_logger.error(str(e))

    def _mac_open(self, *filenames):
        my_logger.debug("_mac_open")
        self.after(100, lambda: self._load_file(filenames[0]))

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_styles(self):
        style = ttk.Style(self)
        preferred = self.prefs.get("theme", "default")
        if preferred in style.theme_names():
            style.theme_use(preferred)

    def _save_prefs(self,prefs):
        self.prefs=prefs
        save_prefs(prefs)

    def _build_ui(self):
        self.option_add("*tearOff", False)

        # ── Menu bar ─────────────────────────────────────────────────────
        self._menubar = tk.Menu(self)
        self.configure(menu=self._menubar)

        self._build_file_menu()
        self._build_view_menu()
        self._build_playback_menu()
        self._build_help_menu()

        # ── Horizontal paned window ───────────────────────────────────────
        paned = tk.PanedWindow(
            self, orient=tk.HORIZONTAL,
            bg=self.prefs["color_border"],
            sashwidth=5, sashrelief=tk.FLAT,
        )
        paned.pack(fill=tk.BOTH, expand=True)
        self._paned = paned

        # Left: file list
        self._file_list_pane = FileListPane(
            paned, self.prefs, on_select=self._load_file)
        paned.add(self._file_list_pane,
                  stretch="never",
                  minsize=160,
                  width=self.prefs.get("sash_position", 280))

        # Right: dashboard + map + controls
        self._map_pane = MapPane(
            paned, self.prefs,
            playback_callbacks={
                "play_pause"  : self._toggle_play,
                "step_back"   : self._step_back,
                "step_fwd"    : self._step_fwd,
                "slider"      : self._on_slider,
                "speed_change": self._on_speed_change,
            },
        )
        paned.add(self._map_pane, stretch="always", minsize=500)

        # ── Status bar ────────────────────────────────────────────────────
        status_bar = tk.Frame(self, bg=self.prefs["color_panel_bg"], pady=3)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(status_bar, textvariable=self._status_var,
                 bg=self.prefs["color_panel_bg"],
                 fg=self.prefs["color_accent"],
                 font=self.prefs["font_small"]).pack(side=tk.LEFT, padx=10)

        # ── Keyboard shortcuts ────────────────────────────────────────────
        self._bind_keys()

    # ── Menu builders ─────────────────────────────────────────────────────────

    def _build_file_menu(self):
        m = tk.Menu(self._menubar)
        self._menubar.add_cascade(label="File", menu=m, underline=0)

        acc = "Command" if PLATFORM_SYSTEM == "Darwin" else "Ctrl"

        m.add_command(label="Import FC2 File(s)…",
                      command=self._import_files,
                      accelerator=f"{acc}+O",
                      underline=0)
        m.add_command(label="Import Directory…",
                      command=self._import_directory,
                      underline=7)
        m.add_separator()
        m.add_command(label="Export Current File to CSV…",
                      command=self._export_csv_current,
                      accelerator=f"{acc}+E",
                      underline=0)
        m.add_command(label="Export All Files to CSV…",
                      command=self._export_csv_all,
                      underline=7)
        m.add_separator()
        m.add_command(label="Preferences…",
                      command=self._show_prefs,
                      accelerator=f"{acc}+,",
                      underline=0)
        m.add_separator()
        if PLATFORM_SYSTEM != "Darwin":
            m.add_command(label="About",
                          command=self._show_about,
                          underline=0)
        m.add_separator()
        m.add_command(label="Quit",
                      command=self._on_close,
                      accelerator=f"{acc}+Q",
                      underline=0)

    def _build_view_menu(self):
        m = tk.Menu(self._menubar)
        self._menubar.add_cascade(label="View", menu=m, underline=0)

        acc = "Command" if PLATFORM_SYSTEM == "Darwin" else "Ctrl"

        m.add_command(label="Flight Summary…",
                      command=self._show_summary,
                      accelerator=f"{acc}+F",
                      underline=0)
        m.add_command(label="Log…",
                      command=self._show_log,
                      accelerator=f"{acc}+L",
                      underline=0)
        m.add_separator()
        m.add_command(label="Fit Map to Path",
                      command=self._fit_map,
                      underline=0)

    def _build_playback_menu(self):
        m = tk.Menu(self._menubar)
        self._menubar.add_cascade(label="Playback", menu=m, underline=0)

        m.add_command(label="Play / Pause",
                      command=self._toggle_play,
                      accelerator="Space",
                      underline=0)
        m.add_command(label="Step Back",
                      command=self._step_back,
                      accelerator="←",
                      underline=5)
        m.add_command(label="Step Forward",
                      command=self._step_fwd,
                      accelerator="→",
                      underline=5)
        m.add_separator()
        m.add_command(label="Decrease Speed",
                      command=self._slower,
                      underline=0)
        m.add_command(label="Increase Speed",
                      command=self._faster,
                      underline=0)
        m.add_separator()
        m.add_command(label="Go to Start",
                      command=lambda: self._update_display(0),
                      underline=6)
        m.add_command(label="Go to End",
                      command=lambda: self._update_display(len(self.records) - 1),
                      underline=6)

    def _build_help_menu(self):
        m = tk.Menu(self._menubar)
        self._menubar.add_cascade(label="Help", menu=m, underline=0)

        acc = "Command+?" if PLATFORM_SYSTEM == "Darwin" else "F1"
        m.add_command(label="Help…",
                      command=self._show_help,
                      accelerator=acc,
                      underline=0)
        m.add_separator()
        m.add_command(label="About…",
                      command=self._show_about,
                      underline=0)

    def _bind_keys(self):
        if PLATFORM_SYSTEM == "Darwin":
            # File Menu
            self.bind("<Command-o>", lambda e: self._import_files())
            self.bind("<Command-e>", lambda e: self._export_csv_current())
            self.bind("<Command-q>", lambda e: self._on_close())
            self.bind("<Command-,>", lambda e: self._show_prefs())
            # View Menu
            self.bind("<Command-f>", lambda e: self._show_summary())
            self.bind("<Command-l>", lambda e: self._show_log())
            self.bind("<Command-0>", lambda e: self._fit_map())
        else:
            # File Menu
            self.bind("<Control-o>", lambda e: self._import_files())
            self.bind("<Control-e>", lambda e: self._export_csv_current())
            self.bind("<Control-q>", lambda e: self._on_close())
            # View Menu
            self.bind("<Control-f>", lambda e: self._show_summary())
            self.bind("<Control-l>", lambda e: self._show_log())
            self.bind("<Control-0>", lambda e: self._fit_map())

        if PLATFORM_SYSTEM == "Darwin":
            self.bind("<Command-?>",   lambda e: self._show_help())
        else:
            self.bind("<F1>",          lambda e: self._show_help())

        self.bind("<space>", lambda e: self._toggle_play())
        self.bind("<Left>",  lambda e: self._step_back())
        self.bind("<Right>", lambda e: self._step_fwd())
        self.bind("<Delete>",    lambda e: self._file_list_pane.remove_selected())
        self.bind("<BackSpace>", lambda e: self._file_list_pane.remove_selected())

    # ─────────────────────────────────────────────────────────────────────────
    # File import
    # ─────────────────────────────────────────────────────────────────────────

    def _import_files(self):
        files = filedialog.askopenfilenames(
            title="Import FC2 Flight Log(s)",
            initialdir=self.prefs.get("last_import_dir", str(Path.home())),
            filetypes=[("FC2 flight logs", "*.fc2"), ("All files", "*.*")],
        )
        if not files:
            return
        self.prefs["last_import_dir"] = str(Path(files[0]).parent)
        self._file_list_pane.add_files(list(files))
        self._set_status(f"Added {len(files)} file(s) to the list.")

    def _import_directory(self):
        directory = filedialog.askdirectory(
            title="Import all FC2 files from directory",
            initialdir=self.prefs.get("last_import_dir", str(Path.home())),
        )
        if not directory:
            return
        self.prefs["last_import_dir"] = directory
        fc2_files = list(Path(directory).rglob("*.fc2"))
        if not fc2_files:
            messagebox.showinfo("No FC2 Files",
                                f"No .fc2 files found in:\n{directory}")
            return
        self._file_list_pane.add_files([str(p) for p in fc2_files])
        self._set_status(f"Added {len(fc2_files)} file(s) from directory.")

    # ─────────────────────────────────────────────────────────────────────────
    # File loading  (parses the binary and updates the map / dashboard)
    # ─────────────────────────────────────────────────────────────────────────

    def _load_file(self, path: str):
        """Parse an fc2 file and populate the UI.  Called from double click."""
        if self.playing:
            self._pause()

        self._set_status(f"Loading {Path(path).name}…")
        self.update_idletasks()

        try:
            all_records = atom2_parser(file_name=path, logger=my_logger)
        except Exception as exc:
            messagebox.showerror("Parse Error", str(exc))
            my_logger.error(str(exc))
            self._set_status("Error loading file.")
            return

        if not all_records:
            messagebox.showwarning("Empty File", "No records found in this file.")
            return

        self._all_records = all_records
        self.current_file = path

        log_stats(my_logger, self._all_records)

        # For map/playback, only use GPS-locked records
        gps_records = [r for r in all_records if r.get("GPS Lock") == "Yes"]
        if not gps_records:
            messagebox.showwarning("No GPS Data",
                                   "No GPS-locked records found in this file.")
            return

        self.records     = gps_records
        self.records_len = len(gps_records)
        self.coords      = [(r["lat (deg)"], r["lon (deg)"]) for r in gps_records]
        self.current_idx = 0

        # Draw path and fit map
        self._map_pane.draw_path(self.coords)
        self._map_pane.fit_to_path(self.coords)

        # Set slider range
        self._map_pane.controls.set_range(self.records_len)

        # Update window title
        self.title(f"Atom 2 Viewer — {Path(path).name}")

        self._set_status(
            f"Loaded {self.records_len} GPS records from {Path(path).name}.")

        # Go to first frame
        self._update_display(0)

        # Update summary window if it's open
        if self._summary_window is not None and self._summary_window.winfo_viewable():
            self._summary_window.refresh(self._all_records, self.current_file)

    # ─────────────────────────────────────────────────────────────────────────
    # Display update  (called every frame during playback)
    # ─────────────────────────────────────────────────────────────────────────

    def _update_display(self, idx: int):
        if not self.records:
            return
        idx = max(0, min(idx, self.records_len - 1))
        self.current_idx = idx
        r = self.records[idx]

        # Dashboard
        self._map_pane.dashboard.update_record(r)

        # Map markers
        lat      = r.get("lat (deg)")
        lon      = r.get("lon (deg)")
        home_lat = r.get("Home Lat (deg)")
        home_lon = r.get("Home Lon (deg)")
        heading  = r.get("heading (deg)", 0)
        self._map_pane.update_markers(lat, lon, home_lat, home_lon, heading)

        # Controls
        elapsed_us = r.get("elapsed (us)", 0)
        self._map_pane.controls.set_position(idx, self.records_len, elapsed_us)

        self.pending_update = False

    # ─────────────────────────────────────────────────────────────────────────
    # Playback engine
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        if not self.records:
            return
        if self.current_idx >= self.records_len - 1:
            self.current_idx = 0
        self.playing = True
        self._map_pane.controls.set_playing(True)
        self._stop_event.clear()
        self._playback_thread = threading.Thread(
            target=self._playback_loop, daemon=True)
        self._playback_thread.start()

    def _pause(self):
        self.playing = False
        self._stop_event.set()
        self._map_pane.controls.set_playing(False)

    def _playback_loop(self):
        """Background thread: advances frames at the correct wall-clock rate."""
        incr = self.PLAYBACK_INCREMENT
        speeds = PlaybackControls.PLAYBACK_SPEEDS

        while not self._stop_event.is_set():
            step   = incr[self.speed_idx]
            i_next = self.current_idx + step

            if i_next >= self.records_len:
                self.after(0, self._pause)
                break

            r_cur  = self.records[self.current_idx]
            r_next = self.records[i_next]
            dt_us  = (r_next.get("elapsed (us)", 0)
                      - r_cur.get("elapsed (us)", 0))
            dt_us  = dt_us / speeds[self.speed_idx]
            sleep  = max(0.01, dt_us / 1_000_000)

            if not self.pending_update:
                self.pending_update = True
                self.current_idx    = i_next
                self.after(0, self._update_display, i_next)

            self._stop_event.wait(timeout=sleep)

    def _step_back(self):
        self._update_display(self.current_idx - 100)

    def _step_fwd(self):
        self._update_display(self.current_idx + 100)

    def _slower(self):
        ctrl = self._map_pane.controls
        ctrl._slower()

    def _faster(self):
        ctrl = self._map_pane.controls
        ctrl._faster()

    def _on_slider(self, idx: int):
        if idx != self.current_idx:
            self._update_display(idx)

    def _on_speed_change(self, idx: int):
        self.speed_idx = idx

    # ─────────────────────────────────────────────────────────────────────────
    # CSV export
    # ─────────────────────────────────────────────────────────────────────────

    def _export_csv_current(self):
        """Export the currently loaded file to CSV."""
        if not self._all_records:
            messagebox.showinfo("No Data", "No file is currently loaded.")
            return

        dest_dir = filedialog.askdirectory(
            title="Choose export directory",
            initialdir=self.prefs.get("last_export_dir", str(Path.home())),
        )
        if not dest_dir:
            return
        self.prefs["last_export_dir"] = dest_dir

        try:
            csv_path = export_csv(
                self.current_file,
                self._all_records,
                extended=self.prefs.get("csv_extended", False),
                derived=self.prefs.get("csv_derived", True),
                destination=dest_dir,
            )
            self._set_status(f"Exported: {Path(csv_path).name}")
            messagebox.showinfo("Export Complete", f"CSV written to:\n{csv_path}")
        except Exception as exc:
            my_logger.error(str(exc))
            messagebox.showerror("Export Error", str(exc))

    def _export_csv_all(self):
        """Export every file in the file list to CSV."""
        paths = self._file_list_pane.get_paths()
        if not paths:
            messagebox.showinfo("No Files", "The file list is empty.")
            return

        dest_dir = filedialog.askdirectory(
            title="Choose export directory for all files",
            initialdir=self.prefs.get("last_export_dir", str(Path.home())),
        )
        if not dest_dir:
            return
        self.prefs["last_export_dir"] = dest_dir

        errors  = []
        written = 0
        for path in paths:
            try:
                records = atom2_parser(file_name=path, logger=my_logger)
                if records:
                    export_csv(
                        path, records,
                        extended=self.prefs.get("csv_extended", False),
                        derived=self.prefs.get("csv_derived", True),
                        destination=dest_dir,
                    )
                    written += 1
                else:
                    my_logger.info("%s has 0 records.", Path(path).name)
                    errors.append(f"{Path(path).name}: 0 records.")
            except Exception as exc:
                my_logger.warning("%s: %s", Path(path).name, str(exc))
                errors.append(f"{Path(path).name}: {exc}")

        msg = f"Exported {written} of {len(paths)} files."
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors)
        messagebox.showinfo("Batch Export Complete", msg)
        self._set_status(f"Batch export: {written}/{len(paths)} files written.")

    # ─────────────────────────────────────────────────────────────────────────
    # Pop-ups and dialogs
    # ─────────────────────────────────────────────────────────────────────────

    def _show_summary(self):
        if self._summary_window is None:
            self._summary_window = FlightSummaryWindow(self, self.prefs)

        self._summary_window.refresh(self._all_records, self.current_file)
        self._summary_window.show()

    def _show_log(self):
        try:
            my_logger.show_tk_window()
        except Exception as e:
            my_logger.error(str(e))
            messagebox.showinfo("Log", "Log window is not available.")

    def _fit_map(self):
        if self.coords:
            self._map_pane.fit_to_path(self.coords)
        else:
            messagebox.showinfo("No Data", "No flight path is loaded.")

    def _show_prefs(self):
        if self._preferences_window is None:
            self._preferences_window = PrefsDialog(self, self.prefs,
                                                   self._save_prefs,
                                                   self._menubar)
        self._preferences_window.show()

    def _show_help(self):
        if self._help_window is None:
            self._help_window = HelpWindow(self, self.prefs)
        self._help_window.show()

    def _show_about(self):
        messagebox.showinfo(
            "About Atom 2 Data Viewer",
            f"Atom 2 Log Visualizer\n\n"
            f"Version:\n{_version}\n\n"
            "Written by Michael Heinz.\n"
            "Based on work by Michael Heinz, Koen Aerts, and Rob Pritt.",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Status bar helper
    # ─────────────────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # Shutdown
    # ─────────────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self.playing:
            self._pause()
        self.prefs["window_geometry"] = self.geometry()
        try:
            self.prefs["sash_position"] = self._paned.sash_coord(0)[0]
        except Exception as e:
            my_logger.error(str(e))

        save_prefs(self.prefs)
        self.quit()

    def cli_load_file(self, path: str):
        """ Used to load a file when running from the command line. """
        if Path(path).exists():
            self._file_list_pane.add_files([path])
            self.after(200, lambda: self._load_file(path))
        else:
            my_logger.error("File not found: %s", path)


def main():
    """ Main entry point... because pylint insists on a docstring here."""
    app = Atom2Viewer()

    # Allow a single fc2 path as a command-line argument (convenience)
    if len(sys.argv) > 1:
        path = sys.argv[1]
        app.cli_load_file(path)
    app.mainloop()


if __name__ == "__main__":
    main()
