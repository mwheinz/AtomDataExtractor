#!/usr/bin/env python3
"""
Atom 2 Flight Log Visualizer
Displays drone flight path, telemetry gauges, and RC stick positions
with playback controls. Uses tkinter + tkintermapview.
"""

import os
import sys
import math
import struct
import re
import datetime
import threading
import time
import json
import platform
from pathlib import Path
import tkinter as tk
import tkinter.font as tkf
from tkinter import ttk, filedialog, messagebox
import tkintermapview
from PIL import Image, ImageDraw, ImageTk, ImageFont
from adeversion import _version
from atom2parser import BadData, atom2_parser, is_valid_latlon
import mwhlogging
from mwhlogging import MWHLogger

my_logger = MWHLogger("atom_data_viewer")
my_logger.setLevel(mwhlogging.DEBUG)

PREFS_FILE = Path.home() / ".atom_data_viewer.json"

DEFAULT_PREFS = {
    # ─────────────────────────────────────────────────────────────────────────
    # Basic settings.
    # ─────────────────────────────────────────────────────────────────────────
    "window_geometry": "1200x800",
    "log_level"      : "Debug",

    # ─────────────────────────────────────────────────────────────────────────
    # Color palette
    # ─────────────────────────────────────────────────────────────────────────
    "color_bg"       : "#0d1117",
    "color_gauge_bg" : "#161b22",
    "color_accent"   : "#58a6ff",
    "color_border"   : "#30363d",
    "color_value"    : "#e6edf3",
    "color_label"    : "#8b949e",
    "color_path"     : "#3fb950",

    "color_safe"     : "#3fb950",
    "color_warn"     : "#d29922",
    "color_danger"   : "#f85149",

    # ─────────────────────────────────────────────────────────────────────────
    # Font palette. May be overridden by the platform type.
    # ─────────────────────────────────────────────────────────────────────────
    "font_label"     : ("Helvetica", 10),
    "font_title"     : ("Times", 13, "bold"),
    "font_marker"    : "",
    "font_small"     : ("Helvetica", 8),
}

# ─────────────────────────────────────────────────────────────────────────────
# Use fonts that should be available on the current platform.
# ─────────────────────────────────────────────────────────────────────────────
PLATFORM_SYSTEM = platform.system()
if PLATFORM_SYSTEM == "Linux":
    DEFAULT_PREFS["font_label"]  = ("Liberation", 10)
    DEFAULT_PREFS["font_title"]  = ("Times", 13, "bold")
    DEFAULT_PREFS["font_marker"] = ""
    DEFAULT_PREFS["font_small"]  = ("Liberation", 8)
elif PLATFORM_SYSTEM == "Darwin":
    DEFAULT_PREFS["font_label"]  = ("Helvetica Neue", 10)
    DEFAULT_PREFS["font_title"]  = ("Helvetica Neue", 13, "bold")
    DEFAULT_PREFS["font_marker"] = "/System/Library/Fonts/HelveticaNeue.ttc"
    DEFAULT_PREFS["font_small"]  = ("Helvetica Neue", 8)
else:
    DEFAULT_PREFS["font_label"] = ("Helvetica", 10)
    DEFAULT_PREFS["font_title"] = ("Times", 13, "bold")
    DEFAULT_PREFS["font_marker"] = ""
    DEFAULT_PREFS["font_small"] = ("Helvetica", 8)

LOG_LEVEL_MAP = {
    "Error": mwhlogging.ERROR,
    "Warning": mwhlogging.WARNING,
    "Info": mwhlogging.INFO,
    "Debug": mwhlogging.DEBUG,
}

def load_prefs() -> dict:
    my_logger.debug(f"Loading preferences from {PREFS_FILE}")
    try:
        if PREFS_FILE.exists():
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            prefs = DEFAULT_PREFS.copy()
            prefs.update(saved)
            return prefs
    except Exception as e:
        messagebox.showerror("Failed to load the saved preferences.", str(e))
        my_logger.error(f"Failed to load the saved preferences.\n{e}")
        pass
    return DEFAULT_PREFS.copy()

def save_prefs(prefs: dict) -> None:
    my_logger.debug(f"Saving preferences to {PREFS_FILE}")
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        messagebox.showerror("Failed to save the preferences.", str(e))
        my_logger.error(f"Failed to save the preferences.\n{e}")
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Preferences Dialog
# ─────────────────────────────────────────────────────────────────────────────

class PrefsDialog(tk.Toplevel):
    """
    Modal dialog for editing the application preferences.
    Edits a copy of prefs and calls on_save(new_prefs) if the user clicks Save.
    """

    COLOR_FIELDS = [
        ("color_bg",       "Background"),
        ("color_gauge_bg", "Gauge Background"),
        ("color_accent",   "Accent"),
        ("color_border",   "Border"),
        ("color_value",    "Values"),
        ("color_label",    "Label"),
        ("color_path",     "Flight Path"),
        ("color_safe",     "Safe"),
        ("color_warn",     "Warning"),
        ("color_danger",   "Danger"),
    ]

    FONT_FIELDS = [
        ("font_label",  "Label Font"),
        ("font_title",  "Title Font"),
        ("font_small",  "Small Font"),
    ]

    def __init__(self, parent, prefs: dict, on_save):
        super().__init__(parent)
        self.title("Preferences")
        self.resizable(False, False)
        self.grab_set()             # make modal
        self.transient(parent)      # keep on top of parent

        self._prefs   = prefs.copy()
        self._on_save = on_save
        self._swatches: dict[str, tk.Label] = {}
        self._font_vars: dict[str, tuple]   = {}

        self._build()
        self._center_on(parent)

    # ── Layout ────────────────────────────────────────────────────────────

    def _build(self):
        PAD = dict(padx=10, pady=4)

        tk.Label(self, text="Some changes will not take effect until restart.",
             font=self._prefs["font_label"],
             fg="white").pack(padx=12, pady=(8, 0), anchor="w")

        # ── Colors ────────────────────────────────────────────────────────
        color_frame = tk.LabelFrame(self, text=" Colors ", padx=6, pady=6)
        color_frame.pack(fill=tk.X, padx=12, pady=(12, 4))

        for i, (key, label) in enumerate(self.COLOR_FIELDS):
            row = i // 2
            col = (i % 2) * 3       # 3 columns per side: label | swatch | button

            tk.Label(color_frame, text=label + ":", anchor="w",
                     width=12).grid(row=row, column=col, sticky="w", **PAD)

            swatch = tk.Label(color_frame, width=3,
                              bg=self._prefs.get(key, "#000000"),
                              relief=tk.SOLID, bd=1)
            swatch.grid(row=row, column=col + 1, padx=(0, 4), pady=4)
            self._swatches[key] = swatch

            tk.Button(color_frame, text="Choose…",
                      command=lambda k=key: self._pick_color(k),
                      padx=4).grid(row=row, column=col + 2, **PAD)

        # ── Fonts ─────────────────────────────────────────────────────────
        font_frame = tk.LabelFrame(self, text=" Fonts ", padx=6, pady=6)
        font_frame.pack(fill=tk.X, padx=12, pady=4)

        families = self._get_font_families()

        for i, (key, label) in enumerate(self.FONT_FIELDS):
            current = self._prefs.get(key, ("Helvetica", 10))
            # current may be a list if loaded from JSON (JSON turns tuples into lists)
            current_family = current[0]
            current_size   = current[1]
            current_bold   = len(current) > 2 and current[2] == "bold"

            tk.Label(font_frame, text=label + ":", anchor="w",
                    width=12).grid(row=i, column=0, sticky="w", padx=(10, 4), pady=4)

            # Family dropdown
            family_var = tk.StringVar(value=current_family)
            family_cb  = ttk.Combobox(font_frame, textvariable=family_var,
                                    values=families, width=22, state="readonly")
            family_cb.grid(row=i, column=1, padx=4, pady=4)

            # Size spinbox
            size_var = tk.IntVar(value=current_size)
            tk.Spinbox(font_frame, textvariable=size_var,
                    from_=6, to=32, width=4).grid(row=i, column=2, padx=4, pady=4)

            # Bold checkbox
            bold_var = tk.BooleanVar(value=current_bold)
            tk.Checkbutton(font_frame, text="Bold",
                        variable=bold_var).grid(row=i, column=3, padx=4, pady=4)

            self._font_vars[key] = (family_var, size_var, bold_var)

        # Font marker path (separate — it's a file path, not a tkinter font)
        tk.Label(font_frame, text="Marker Font:", anchor="w",
                width=12).grid(row=len(self.FONT_FIELDS), column=0,
                                sticky="w", padx=(10, 4), pady=4)
        self._marker_var = tk.StringVar(value=self._prefs.get("font_marker", ""))
        tk.Entry(font_frame, textvariable=self._marker_var,
                width=28).grid(row=len(self.FONT_FIELDS), column=1,
                                columnspan=2, padx=4, pady=4, sticky="w")
        tk.Button(font_frame, text="Browse…",
                command=self._pick_marker_font).grid(
            row=len(self.FONT_FIELDS), column=3, padx=4, pady=4)

        # ── Logging ───────────────────────────────────────────────────────
        log_frame = tk.LabelFrame(self, text=" Logging ", padx=6, pady=6)
        log_frame.pack(fill=tk.X, padx=12, pady=4)

        tk.Label(log_frame, text="Log Level:").pack(side=tk.LEFT, padx=(4, 8))
        self._log_var = tk.StringVar(value=self._prefs.get("log_level", "Info"))
        for level in ("Error", "Warning", "Info", "Debug"):
            tk.Radiobutton(log_frame, text=level,
                           variable=self._log_var, value=level).pack(
                side=tk.LEFT, padx=4)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row = tk.Frame(self)
        btn_row.pack(fill=tk.X, padx=12, pady=(4, 12))

        tk.Button(btn_row, text="Restore Defaults",
                  command=self._restore_defaults).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Cancel",
                  command=self.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_row, text="Save",
                  command=self._save,
                  default=tk.ACTIVE).pack(side=tk.RIGHT)

        # Allow Enter to save and Escape to cancel
        self.bind("<Return>",  lambda e: self._save())
        self.bind("<Escape>",  lambda e: self.destroy())

    # ── Helpers ───────────────────────────────────────────────────────────

    def _pick_marker_font(self):
        path = filedialog.askopenfilename(
            title="Select marker font file",
            filetypes=[("Font files", "*.ttf *.ttc *.otf"), ("All files", "*.*")],
            parent=self
        )
        if path:
            self._marker_var.set(path)

    def _get_font_families(self) -> list[str]:
        families = sorted(set(tkf.families()))
        return [f for f in families if not f.startswith("@")]  # skip vertical CJK fonts

    def _center_on(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _pick_color(self, key: str):
        from tkinter.colorchooser import askcolor
        current = self._prefs.get(key, "#000000")
        _, hex_color = askcolor(color=current,
                                title=f"Choose: {key}",
                                parent=self)
        if hex_color:
            self._prefs[key] = hex_color
            self._swatches[key].configure(bg=hex_color)

    def _restore_defaults(self):
        for key, _ in self.COLOR_FIELDS:
            default = DEFAULT_PREFS.get(key, "#000000")
            self._prefs[key] = default
            self._swatches[key].configure(bg=default)
        for key, _ in self.FONT_FIELDS:
            default = DEFAULT_PREFS.get(key, ("Helvetica", 10))
            family_var, size_var, bold_var = self._font_vars[key]
            family_var.set(default[0])
            size_var.set(default[1])
            bold_var.set(len(default) > 2 and default[2] == "bold")
        self._marker_var.set(DEFAULT_PREFS.get("font_marker", ""))
        self._log_var.set(DEFAULT_PREFS.get("log_level", "Info"))
        self.update_idletasks()


    def _save(self):
        for key, _ in self.FONT_FIELDS:
            family_var, size_var, bold_var = self._font_vars[key]
            if bold_var.get():
                self._prefs[key] = (family_var.get(), size_var.get(), "bold")
            else:
                self._prefs[key] = (family_var.get(), size_var.get())

        self._prefs["font_marker"] = self._marker_var.get()
        self._prefs["log_level"] = self._log_var.get()
        self._on_save(self._prefs)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Canvas-based gauge widgets
# ─────────────────────────────────────────────────────────────────────────────

class CompassGauge(tk.Canvas):
    """Circular compass that shows heading."""

    def __init__(self, parent, prefs:dict, label="", size=120, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        self.prefs = prefs
        self.label = label
        self.size = size
        self.heading = 0.0
        self._draw()

    def _draw(self):
        s = self.size
        cx = cy = s / 2
        r = s / 2 - 4

        self.delete("all")

        # Outer ring
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                         outline=self.prefs["color_border"], width=2,
                         fill=self.prefs["color_gauge_bg"])

        # Cardinal labels
        for label, angle in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            rad = math.radians(angle - 90)
            lx = cx + (r - 14) * math.cos(rad)
            ly = cy + (r - 14) * math.sin(rad)
            color = self.prefs["color_danger"] if label == "N" else self.prefs["color_label"]
            self.create_text(lx, ly, text=label, fill=color,
                             font=self.prefs["font_small"])

        # Label
        self.create_text(cx, cy - r * 0.25,
                         text=self.label, fill=self.prefs["color_label"],
                         font=self.prefs["font_small"])

        # Tick marks
        for i in range(36):
            ang = math.radians(i * 10 - 90)
            inner = r - 6 if i % 9 == 0 else r - 4
            x1 = cx + inner * math.cos(ang)
            y1 = cy + inner * math.sin(ang)
            x2 = cx + r * math.cos(ang)
            y2 = cy + r * math.sin(ang)
            self.create_line(x1, y1, x2, y2, fill=self.prefs["color_border"])

        # Needle
        needle_rad = math.radians(self.heading - 90)
        nx = cx + (r - 18) * math.cos(needle_rad)
        ny = cy + (r - 18) * math.sin(needle_rad)
        # tail
        tx = cx - 8 * math.cos(needle_rad)
        ty = cy - 8 * math.sin(needle_rad)
        self.create_line(tx, ty, nx, ny, fill=self.prefs["color_accent"], width=2,
                         arrow=tk.LAST, arrowshape=(8, 10, 3))

        # Center dot
        self.create_oval(cx-3, cy-3, cx+3, cy+3, fill=self.prefs["color_accent"], outline="")

        # Value text
        self.create_text(cx, s - 8, text=f"{self.heading:.1f}°",
                         fill=self.prefs["color_value"], font=self.prefs["font_small"])

    def set_value(self, heading: float):
        self.heading = heading % 360
        self._draw()


class ArcGauge(tk.Canvas):
    """
    Semi-circular arc gauge for a single numeric value.
    Shows a coloured arc fill + needle + numeric readout.
    """

    def __init__(self, parent, prefs:dict, label, min_val, max_val,
                 unit="", warn_pct=0.5, danger_pct=0.95,
                 size=110, **kw):
        super().__init__(parent, width=size, height=int(size * 0.75),
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        self.prefs     = prefs
        self.label     = label
        self.min_val   = min_val
        self.max_val   = max_val
        self.unit      = unit
        self.warn_pct  = warn_pct
        self.danger_pct= danger_pct
        self.size      = size
        self.value     = min_val
        self._draw()

    def _draw(self):
        s = self.size
        h = int(s * 0.75)
        cx = s / 2
        cy = h * 0.88
        r  = s * 0.42

        self.delete("all")

        # Background arc (180°)
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=0, extent=180,
                        style=tk.ARC, outline=self.prefs["color_border"], width=8)

        # Colored fill arc
        pct = (self.value - self.min_val) / max(self.max_val - self.min_val, 1e-9)
        pct = max(0.0, min(1.0, pct))
        extent = pct * 180

        color = self.prefs["color_safe"]
        if pct >= self.danger_pct:
            color = self.prefs["color_danger"]
        elif pct >= self.warn_pct:
            color = self.prefs["color_warn"]

        if extent > 0:
            self.create_arc(cx-r, cy-r, cx+r, cy+r,
                            start=180 - extent, extent=extent,
                            style=tk.ARC, outline=color, width=8)

        # Needle
        needle_angle = math.radians(180 - pct * 180)
        nx = cx + (r - 2) * math.cos(needle_angle)
        ny = cy - (r - 2) * math.sin(needle_angle)
        self.create_line(cx, cy, nx, ny, fill=self.prefs["color_value"], width=2)
        self.create_oval(cx-3, cy-3, cx+3, cy+3, fill=self.prefs["color_value"], outline="")

        # Label
        self.create_text(cx, cy - r * 0.5,
                         text=self.label, fill=self.prefs["color_label"],
                         font=self.prefs["font_small"])

        # Value
        val_text = f"{self.value:.1f}{self.unit}"
        self.create_text(cx, cy - 10,
                         text=val_text, fill=self.prefs["color_value"],
                         font=self.prefs["font_label"])

    def set_value(self, value: float):
        self.value = value
        self._draw()


class StickDisplay(tk.Canvas):
    """
    Renders a single joystick as a 2D crosshair inside a square.
    x_val, y_val should be in range 0..2048 (centre = 1024).
    """

    def __init__(self, parent, prefs, label, size=100, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        self.prefs  = prefs
        self.label  = label
        self.size   = size
        self.x_val  = 1024.0   # 0..2048
        self.y_val  = 1024.0
        self._draw()

    def _draw(self):
        s = self.size
        pad = 2
        inner = s - 2 * pad

        self.delete("all")

        # Box
        #self.create_rectangle(pad, pad, s - pad, s - pad,
        #                       outline=self.prefs["color_border"], fill=self.prefs["color_gauge_bg"])
        self.create_oval(pad, pad, s - pad, s - pad,
                               outline=self.prefs["color_border"], fill=self.prefs["color_gauge_bg"])

        # Centre cross
        mid = s / 2
        self.create_line(pad, mid, s - pad, mid, fill=self.prefs["color_border"], dash=(2, 3))
        self.create_line(mid, pad, mid, s - pad, fill=self.prefs["color_border"], dash=(2, 3))

        # Dot position
        nx = pad + (self.x_val / 2048.0) * inner
        ny = pad + (1.0 - self.y_val / 2048.0) * inner  # invert Y

        # Glow circle
        gr = 12
        self.create_oval(nx - gr, ny - gr, nx + gr, ny + gr,
                         fill=self.prefs["color_gauge_bg"], outline="")
        self.create_oval(nx - 5, ny - 5, nx + 5, ny + 5,
                         fill=self.prefs["color_accent"], outline="")

        # Label
        self.create_text(mid, s - 5, text=self.label,
                         fill=self.prefs["color_label"], font=self.prefs["font_small"])

    def set_values(self, x_val: float, y_val: float):
        self.x_val = x_val
        self.y_val = y_val
        self._draw()


class BarGauge(tk.Canvas):
    """Vertical bar gauge (e.g. battery, satellites)."""

    def __init__(self, parent, prefs, label="", min_val=0, max_val=10,
                 unit="", size_w=50, size_h=90, warn_low=False,
                 warn_high=False, **kw):
        super().__init__(parent, width=size_w, height=size_h,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        self.prefs   = prefs
        self.label   = label
        self.min_val = min_val
        self.max_val = max_val
        self.unit    = unit
        self.size_w  = size_w
        self.size_h  = size_h
        self.value   = min_val
        self.warn_low = warn_low
        self.warn_high = warn_high
        self._draw()

    def _draw(self):
        w = self.size_w
        h = self.size_h
        pad_x = 8
        bar_w = w - 2 * pad_x
        bar_top = 18
        bar_bot = h - 24
        bar_h   = bar_bot - bar_top

        self.delete("all")

        # Background
        self.create_rectangle(pad_x, bar_top, w - pad_x, bar_bot,
                               outline=self.prefs["color_border"], fill=self.prefs["color_gauge_bg"])

        pct = (self.value - self.min_val) / max(self.max_val - self.min_val, 1e-9)
        pct = max(0.0, min(1.0, pct))

        color = self.prefs["color_safe"]
        if self.warn_low is not False and pct <= self.warn_low:
            color = self.prefs["color_danger"]
        if self.warn_high is not False and pct >= self.warn_high:
            color = self.prefs["color_danger"]

        fill_top = bar_bot - pct * bar_h
        if pct > 0:
            self.create_rectangle(pad_x + 1, fill_top,
                                  w - pad_x - 1, bar_bot - 1,
                                  fill=color, outline="")

        # Label
        self.create_text(w / 2, 9, text=self.label,
                         fill=self.prefs["color_label"], font=self.prefs["font_small"])

        # Value
        self.create_text(w / 2, h - 10,
                         text=f"{self.value:.0f}{self.unit}",
                         fill=self.prefs["color_value"], font=self.prefs["font_small"])

    def set_value(self, value: float):
        self.value = value
        self._draw()


# ─────────────────────────────────────────────────────────────────────────────
# Text info panel
# ─────────────────────────────────────────────────────────────────────────────

class InfoPanel(tk.LabelFrame):
    """Key/value text readout for status fields."""

    def __init__(self, parent, prefs, fields: list[str], **kw):
        super().__init__(parent, bg=prefs["color_bg"], **kw)
        self._vars = {}
        self.prefs = prefs
        for i, name in enumerate(fields):
            row = i // 2
            col = (i % 2) * 2
            tk.Label(self, text=name + ":", bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                     font=self.prefs["font_label"], anchor="w").grid(
                row=row, column=col, sticky="w", padx=(6, 2), pady=1)
            var = tk.StringVar(value="—")
            tk.Label(self, textvariable=var, bg=self.prefs["color_bg"], fg=self.prefs["color_value"],
                     font=self.prefs["font_label"], anchor="w").grid(
                row=row, column=col+1, sticky="w", padx=(2, 6), pady=1)
            self._vars[name] = var

    def update_field(self, name: str, value):
        if name in self._vars:
            self._vars[name].set(str(value))


# ─────────────────────────────────────────────────────────────────────────────
# Main application window
# ─────────────────────────────────────────────────────────────────────────────

class DroneViewer(tk.Tk):

    # Playback speed multipliers
    SPEEDS = [1.0, 2.0, 4.0, 8.0, 16.0]

    def __init__(self):
        super().__init__()

        self.prefs = load_prefs()

        self.configure(menu=tk.Menu(self))
        self.title("Atom 2 Flight Log Viewer")
        self.configure(bg=self.prefs["color_bg"])
        self.minsize(1100, 720)

        my_logger.setLevel(LOG_LEVEL_MAP[self.prefs["log_level"]])
        geometry = self.prefs.get("window_geometry", "1280x800")

        self.geometry(geometry)

        # ── State ─────────────────────────────────────────────────────────
        self.records: list[dict] = []
        self.current_idx: int    = 0
        self.playing: bool       = False
        self.speed_idx: int      = 1          # default 1×
        self.playback_thread     = None
        self._stop_event         = threading.Event()

        # Map markers / path
        self._path_line          = None
        self._drone_marker       = None
        self._home_marker        = None
        self._played_path        = []         # coords shown so far
        self._heading            = None

        self._build_ui()
        self._apply_styles()

    # ── UI construction ───────────────────────────────────────────────────
    def _show_prefs(self):
        PrefsDialog(self, self.prefs, self._on_prefs_saved)

    def _on_prefs_saved(self, new_prefs: dict):
        self.prefs.update(new_prefs)
        save_prefs(self.prefs)
        my_logger.setLevel(LOG_LEVEL_MAP[self.prefs["log_level"]])
        # Redraw all canvas gauges so they pick up the new colors immediately
        for widget in (self._gauge_speed, self._gauge_alt, self._gauge_dist,
                       self._gauge_compass, self._bar_battery, self._bar_sats,
                       self._bar_wind, self._bar_thrust, self._stick_left,
                       self._stick_right):
            widget._draw()
 
    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Atom 2 Data Viewer\n"
            f"Version {_version}\n\n"
            "View the contents of an Atom2 flight log (.fc2 file).\n\n"
            "Written by Michael Heinz.\n"
            "Based on work by Michael Heinz, Koen Aerts, and Rob Pritt."
        )

    def _on_close(self):
        my_logger.debug("Quitting.")
        self.prefs["window_geometry"] = self.geometry()
        save_prefs(self.prefs)
        self.quit()

    def _build_ui(self):

        my_logger.debug("Building the UI")

        self.option_add('*tearOff', False)
        self.configure(menu=tk.Menu(self))
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open FC2", command=self._open_file)
        file_menu.add_separator()
        file_menu.add_command(label="Preferences…", command=self._show_prefs)  # ← add this
        file_menu.add_separator()
        file_menu.add_command(label="About", command=self._show_about)
        file_menu.add_command(label="Quit", command=self._on_close)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.createcommand("tk::mac::Quit", self._on_close)

        # ── Top bar ───────────────────────────────────────────────────────
        top = tk.Frame(self, bg=self.prefs["color_bg"], pady=6)
        top.pack(fill=tk.X, side=tk.TOP)

        tk.Label(top, text="ATOM 2 FLIGHT VIEWER",
                 bg=self.prefs["color_bg"], fg=self.prefs["color_accent"],
                 font=self.prefs["font_title"]).pack(side=tk.LEFT, padx=16)

        self._file_label = tk.Label(top, text="No file loaded",
                                    bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                                    font=self.prefs["font_title"])
        self._file_label.pack(side=tk.LEFT, padx=8)

        open_btn = tk.Button(top, text="Open FC2…",
                             command=self._open_file,
                             fg=self.prefs["color_bg"], relief=tk.FLAT,
                             font=self.prefs["font_label"],
                             padx=10, pady=2, cursor="hand2")
        open_btn.pack(side=tk.RIGHT, padx=16)

        # ── Main paned area ───────────────────────────────────────────────
        main = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              bg=self.prefs["color_bg"], sashwidth=4, sashrelief=tk.FLAT)
        main.pack(fill=tk.BOTH, expand=True)

        # Left: map
        map_frame = tk.Frame(main, bg=self.prefs["color_bg"])
        main.add(map_frame, stretch="always", minsize=500)

        self.map_widget = tkintermapview.TkinterMapView(
            map_frame, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True)

        # Disable the scroll wheel, it doesn't seem to work correctly.
        self.map_widget.canvas.unbind("<MouseWheel>")

        # Right: gauges + controls
        right = tk.Frame(main, bg=self.prefs["color_bg"], width=360)
        right.pack_propagate(False)
        main.add(right, stretch="never", minsize=360)

        self._build_gauges(right)
        self._build_controls(right)

        # ── Bottom status bar ─────────────────────────────────────────────
        bot = tk.Frame(self, bg=self.prefs["color_bg"], pady=3)
        bot.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_var = tk.StringVar(value="Ready. Open an FC2 file to begin.")
        tk.Label(bot, textvariable=self._status_var,
                 bg=self.prefs["color_bg"], fg=self.prefs["color_label"], font=self.prefs["font_small"]).pack(side=tk.LEFT, padx=10)

        self._progress_var = tk.StringVar(value="0 / 0")
        tk.Label(bot, textvariable=self._progress_var,
                 bg=self.prefs["color_bg"], fg=self.prefs["color_label"], font=self.prefs["font_small"]).pack(side=tk.RIGHT, padx=10)

    def _build_gauges(self, parent):
        """Build the entire right-side gauge panel."""

        my_logger.debug("Building the Gauges")

        # ── Section: Arc gauges row ───────────────────────────────────────
        arc_row = tk.LabelFrame(parent, bg=self.prefs["color_bg"])
        arc_row.pack(fill=tk.X, padx=6, pady=(6, 0))

        # TODO: Need the maximum values for these to adjust gauges.
        self._gauge_speed  = ArcGauge(arc_row, self.prefs, "SPEED",   0, 1, " kph", size=110)
        self._gauge_alt    = ArcGauge(arc_row, self.prefs, "ALT",     0, 1, " m",  size=110)
        self._gauge_dist   = ArcGauge(arc_row, self.prefs, "DIST",    0, 1, " m",  size=110)

        for g in (self._gauge_speed, self._gauge_alt, self._gauge_dist):
            g.pack(side=tk.LEFT, expand=True)

        # ── Section: Compass + bars ───────────────────────────────────────
        mid_row = tk.Frame(parent, bg=self.prefs["color_bg"])
        mid_row.pack(fill=tk.X, padx=6, pady=4)

        self._gauge_compass = CompassGauge(mid_row, self.prefs, label="HEADING", size=110)
        self._gauge_compass.pack(side=tk.LEFT, padx=(0, 8))

        bars = tk.Frame(mid_row, bg=self.prefs["color_bg"])
        bars.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._bar_battery = BarGauge(bars, self.prefs, label="BATT", max_val=100, unit="%", size_w=36, size_h=110, warn_low=0.3)
        self._bar_sats    = BarGauge(bars, self.prefs, label="SATS", max_val=30,  size_w=36, size_h=110)
        self._bar_wind    = BarGauge(bars, self.prefs, label="WIND", max_val=15, unit=" m/s", size_w=36, size_h=110, warn_high=0.8)
        self._bar_thrust  = BarGauge(bars, self.prefs, label="THRST",max_val=10, size_w=36, size_h=110, warn_high=0.8)

        for b in (self._bar_battery, self._bar_sats, self._bar_wind, self._bar_thrust):
            b.pack(side=tk.LEFT, padx=2)

        # ── Section: Text info ────────────────────────────────────────────
        info_frame = tk.Frame(parent, bg=self.prefs["color_bg"], bd=0)
        info_frame.pack(fill=tk.X, padx=6, pady=4)

        self.info = InfoPanel(info_frame, self.prefs, [
            "Drone Mode",
            "GPS Lock",
            "Flight Mode",
            "Pos Mode",
            "Batt. V",
            "Batt. A",
            "Batt. Temp",
            "Batt. %",
            "Wind Dir",
            "Wind Speed",
            "Record #",
            "Elapsed",
            "Flight Ctr",
        ])
        self.info.pack(fill=tk.X)

        # ── Section: RC Sticks ────────────────────────────────────────────
        sticks_frame = tk.Frame(parent, bg=self.prefs["color_bg"])
        sticks_frame.pack(padx=6, pady=6)

        tk.Label(sticks_frame, text="CONTROLLER", bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                 font=self.prefs["font_small"]).pack(padx=8)

        self._stick_left  = StickDisplay(sticks_frame, self.prefs, "Throttle & Yaw",  size=110)
        self._stick_right = StickDisplay(sticks_frame, self.prefs, "Pitch & Bank", size=110)
        self._stick_left.pack(side=tk.LEFT, padx=(0, 4))
        self._stick_right.pack(side=tk.LEFT)

    def _build_controls(self, parent):
        """Transport controls at the bottom of the right panel."""

        my_logger.debug("Building the Controls")

        ctrl = tk.LabelFrame(parent, bg=self.prefs["color_bg"], pady=8)
        ctrl.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

        # Slider
        self._slider_var = tk.IntVar(value=0)
        self._slider = ttk.Scale(ctrl, from_=0, to=1,
                                 variable=self._slider_var,
                                 orient=tk.HORIZONTAL,
                                 command=self._on_slider)
        self._slider.pack(fill=tk.X, padx=10, pady=(4, 6))

        btn_row = tk.Frame(ctrl, bg=self.prefs["color_bg"])
        btn_row.pack()

        def btn(text, cmd, color=self.prefs["color_gauge_bg"], fg=self.prefs["color_value"]):
            return tk.Button(btn_row, text=text, command=cmd,
                             bg=color, fg=fg, relief=tk.FLAT,
                             font=self.prefs["font_label"],
                             cursor="hand2", activebackground=self.prefs["color_border"],
                             activeforeground=color, bd=1)

        if PLATFORM_SYSTEM == "Darwin":
            self._btn_rw    = btn("⏮️", self._go_start)
            self._btn_back  = btn("⏪", self._step_back)
            self._btn_play  = btn("▶️", self._toggle_play)
            self._btn_fwd   = btn("⏩", self._step_fwd)
            self._btn_ff    = btn("⏭️", self._go_end)
        else:
            self._btn_rw    = btn("<<<", self._go_start)
            self._btn_back  = btn("<<", self._step_back)
            self._btn_play  = btn(">", self._toggle_play)
            self._btn_fwd   = btn(">>", self._step_fwd)
            self._btn_ff    = btn(">>>", self._go_end)


        for b in (self._btn_rw, self._btn_back, self._btn_play,
                  self._btn_fwd, self._btn_ff):
            b.pack(side=tk.LEFT, padx=2)

        # Speed selector
        speed_row = tk.Frame(ctrl, bg=self.prefs["color_bg"])
        speed_row.pack(pady=(4, 2))

        self._speed_var = tk.StringVar(value="1×")
        speeds = ["1×", "2×", "4×", "8×", "16×"]
        for i, label in enumerate(speeds):
            idx = i
            rb = tk.Radiobutton(speed_row, text=label,
                                variable=self._speed_var, value=label,
                                command=lambda i=idx: self._set_speed(i),
                                bg=self.prefs["color_bg"],
                                fg=self.prefs["color_label"],
                                selectcolor=self.prefs["color_bg"],
                                activebackground=self.prefs["color_bg"],
                                activeforeground=self.prefs["color_accent"],
                                indicatoron=True,
                                relief=tk.FLAT,
                                font=self.prefs["font_label"],
                                padx=4, pady=2)
            rb.pack(side=tk.LEFT)

    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TScale", background=self.prefs["color_gauge_bg"],
                        troughcolor=self.prefs["color_border"], slidercolor=self.prefs["color_accent"])

    # ── File loading ──────────────────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            title="Open Atom 2 FC2 Log",
            filetypes=[("FC2 flight logs", "*.fc2"), ("All files", "*.*")]
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        my_logger.debug(f"Loading {path}")
        self._set_status("Loading…")
        self.update_idletasks()

        try:
            records = atom2_parser(path, my_logger)
        except Exception as e:
            messagebox.showerror("Parse error", str(e))
            self._set_status("Error loading file.")
            return

        self.records     = [r for r in records if r.get("GPS Lock") == "Yes"]
        if not records:
            messagebox.showwarning("No data",
                "No valid records found in this file.")
            return

        self.coords = [(r["lat (deg)"], r["lon (deg)"]) for r in self.records]

        self.current_idx = 0

        # Slider range
        self._slider.configure(to=len(records) - 1)
        self._slider_var.set(0)

        # Draw full path on map
        self._draw_map_path()

        # Get the max for some attributes so I can scale the gauges.
        range = [r["alt (m)"] for r in records if r.get("alt (m)") != ""]
        self.max_alt = max(range)

        range = [r["Thrust"] for r in records if r.get("Thrust") != ""]
        self.max_thrust = max(range)

        range = [r["3d Derived Speed (m/s)"] for r in records if r.get("3d Derived Speed (m/s)") != ""]
        #range = [r["speed (m/s)"] for r in records if r.get("speed (m/s)") != ""]
        self.max_speed = max(range)*3.6 # convert to KPH

        range = [r["distance (m)"] for r in records if r.get("distance (m)") != ""]
        self.max_dist = max(range)

        range = [r["Wind Speed (m/s)"] for r in records if r.get("Wind Speed (m/s)") != ""]
        self.max_wind = max(range)

        self._bar_thrust.max_val = self.max_thrust
        self._bar_wind.max_val = self.max_wind
        self._gauge_alt.max_val = self.max_alt
        self._gauge_speed.max_val = self.max_speed
        self._gauge_dist.max_val = self.max_dist
        my_logger.debug(f"Max speed = {self.max_speed} kph, Max dist = {self.max_dist} m, Max alt = {self.max_alt} m")
        my_logger.debug(f"Max thrust = {self.max_thrust}, Max wind = {self.max_wind} m/s")

        # Get the initial bounding box for the map.
        range = [r["lat (deg)"] for r in records if r.get("lat (deg)") != ""]
        self.min_lat = min(range)
        self.max_lat = max(range)
        range = [r["lon (deg)"] for r in records if r.get("lon (deg)") != ""]
        self.min_lon = min(range)
        self.max_lon = max(range)

        # Centre map on first point, scale the map to fit the entire path.
        my_logger.debug(f"Map bounding box: ({self.max_lat},{self.min_lon}), ({self.min_lat},{self.max_lon})")
        self.map_widget.fit_bounding_box((self.max_lat, self.min_lon), (self.min_lat, self.max_lon))

        self._file_label.configure(text=os.path.basename(path))
        self._set_status(f"Loaded {len(records)} GPS records.")
        self._update_display(0)

    # ── Map drawing ───────────────────────────────────────────────────────

    def _draw_map_path(self):
        if self._path_line:
            self._path_line.delete()
            self._path_line = None

        if len(self.coords) >= 2:
            self._path_line = self.map_widget.set_path(
                self.coords, color=self.prefs["color_path"], width=4)

    #
    # Icons for the map
    #
    def _make_drone_icon(self, heading) -> ImageTk.PhotoImage:
        """Draw a simple arrow head rotated to the current heading."""
        size = 21 # Make this an odd number so we actually have a center pixel.
        # Note we add 4 pixels of padding on all sides to make sure there's
        # room for the rotation.
        img = Image.new("RGBA", (size+8, size+8), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = size // 2 + 1, size // 2 + 1

        # Draw a simple arrow/chevron pointing "up" (north = 0°)
        # Note the 4-pixel pad on the top and left.
        draw.polygon([(cx, 0), (size, size), (cx, cy+cy//2), (0, size)],
                    fill=self.prefs["color_danger"], outline=self.prefs["color_border"])

        img = img.rotate(-heading, resample=Image.BICUBIC, expand=False)

        return ImageTk.PhotoImage(img)

    def _make_home_icon(self) -> ImageTk.PhotoImage:
        size = 20
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cc = size // 2

        if self.prefs["font_marker"] == "":
            """Draw a simple house icon."""
            # Roof triangle
            draw.polygon([(cc, 0), (size, cc), (0, cc)],
                         fill=self.prefs["color_accent"],
                         outline=self.prefs["color_border"])
            # House body
            draw.rectangle([(0, cc), (size, size)],
                           fill=self.prefs["color_accent"],
                           outline=self.prefs["color_border"])
            # Door
            draw.rectangle([(cc-4, cc), (cc+4, size)],
                           fill=self.prefs["color_border"])
        else:
            font = ImageFont.truetype(self.prefs["font_marker"], size)
            draw.ellipse([(0,0),(size,size)], fill=self.prefs["color_bg"],
                         outline=self.prefs["color_path"])
            draw.text((cc, cc), "H", font=font,
                      fill=self.prefs["color_path"],
                      anchor="mm")

        return ImageTk.PhotoImage(img)

    def _update_markers(self, record: dict):
        '''
        Updates the position (and orientation) of the home and drone markers.
        '''
        # Home marker
        home_lat = record.get("Home Lat (deg)", "")
        home_lon = record.get("Home Lon (deg)", "")
        if is_valid_latlon(home_lat, home_lon):
            if self._home_marker is None:
                self._home_marker = self.map_widget.set_marker(
                    home_lat, home_lon, 
                    icon=self._make_home_icon(),
                )
                # Make sure the drone is drone on top of the home marker.
                if self._drone_marker is not None:
                    self._drone_marker.delete()
                    self._drone_marker = None
            else:
                self._home_marker.set_position(home_lat,home_lon)

        lat = record["lat (deg)"]
        lon = record["lon (deg)"]
        heading = record["heading (deg)"]

        if self._drone_marker is None:
            self._drone_marker = self.map_widget.set_marker(
                lat, lon,
                icon=self._make_drone_icon(heading),
            )
        else:
            self._drone_marker.set_position(lat,lon)
            # Only recreate the drone icon if the heading has changed enough
            # to be noticable.
            if self._heading != round(heading,0):
                self._heading = round(heading,0)
                self._drone_marker.change_icon(self._make_drone_icon(self._heading))

    # ── Display update ────────────────────────────────────────────────────

    def _update_display(self, idx: int):
        if not self.records:
            return
        idx = max(0, min(idx, len(self.records) - 1))
        self.current_idx = idx
        r = self.records[idx]

        # Gauges
        self._gauge_speed.set_value(r.get("3d Derived Speed (m/s)", 0)*3.6)
        #self._gauge_speed.set_value(r.get("speed (m/s)", 0)*3.6)
        self._gauge_alt.set_value(r.get("alt (m)", 0))
        self._gauge_dist.set_value(r.get("distance (m)", 0))
        self._gauge_compass.set_value(r.get("heading (deg)", 0))

        self._bar_battery.set_value(r.get("Battery Level (%)", 0))
        self._bar_sats.set_value(r.get("Satellites", 0))
        self._bar_wind.set_value(r.get("Wind Speed (m/s)", 0))
        self._bar_thrust.set_value(max(0.0, r.get("Thrust", 0)))

        # RC Sticks
        # Left stick: throttle (Y) + rudder/yaw (X)
        # Right stick: elevator/pitch (Y) + aileron/roll (X)
        self._stick_left.set_values(
            r.get("rc rudder",   1024),
            r.get("rc throttle", 1024)
        )
        self._stick_right.set_values(
            r.get("rc aileron",  1024),
            r.get("rc elevator", 1024)
        )

        # Text info
        elapsed_us = r.get("elapsed (us)", 0)
        elapsed_s  = elapsed_us / 1_000_000
        m, s       = divmod(int(elapsed_s), 60)

        self.info.update_field("Flight Ctr",  r.get("Flight Counter", "0"))
        self.info.update_field("Drone Mode",  r.get("Drone Mode (text)", "—"))
        self.info.update_field("Pos Mode",    r.get("Positioning Mode (text)", "—"))
        self.info.update_field("Flight Mode", r.get("Flight Mode (text)", "—"))
        self.info.update_field("GPS Lock",    r.get("GPS Lock", "—"))
        self.info.update_field("Batt. V",        f"{r.get('Battery (mv)')/1000:.1f}V")
        self.info.update_field("Batt. A",        f"{r.get('Battery Current (ma)')/1000:.1f}A")
        self.info.update_field("Batt. Temp",     f"{r.get('Battery Temp (c)', 0):.1f}C")
        self.info.update_field("Batt. %",        f"{r.get('Battery Level (%)', 0)}%")
        self.info.update_field("Wind Dir",      f"{r.get('Wind (deg)', 0):.1f}°")
        self.info.update_field("Wind Speed",    f"{r.get('Wind Speed (m/s)', 0):.1f} m/s")
        self.info.update_field("Record #",    str(idx + 1))
        self.info.update_field("Elapsed",     f"{m:02d}:{s:02d}")

        # Slider
        self._slider_var.set(idx)
        self._progress_var.set(f"{idx + 1} / {len(self.records)}")

        # Map marker
        self._update_markers(r)

    # ── Transport controls ────────────────────────────────────────────────

    def _toggle_play(self):
        if self.playing:
            self._pause()
        else:
            self._play()

    def _play(self):
        if not self.records:
            return
        if self.current_idx >= len(self.records) - 1:
            self.current_idx = 0
        self.playing = True
        if PLATFORM_SYSTEM == "Darwin":
            self._btn_play.configure(text="⏸️", bg=self.prefs["color_warn"], fg=self.prefs["color_bg"])
        else:
            self._btn_play.configure(text="||", bg=self.prefs["color_warn"], fg=self.prefs["color_bg"])
        self._stop_event.clear()
        self.playback_thread = threading.Thread(
            target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _pause(self):
        self.playing = False
        self._stop_event.set()
        if PLATFORM_SYSTEM == "Darwin":
            self._btn_play.configure(text="▶️", bg=self.prefs["color_accent"], fg=self.prefs["color_bg"])
        else:
            self._btn_play.configure(text=">", bg=self.prefs["color_accent"], fg=self.prefs["color_bg"])

    def _playback_loop(self):
        """Background thread that advances frames at the selected rate."""
        while not self._stop_event.is_set():
            idx = self.current_idx
            if idx >= len(self.records) - 1:
                self.after(0, self._pause)
                break

            # Calculate sleep based on elapsed time between records
            r_cur  = self.records[idx]
            r_next = self.records[idx + 1]
            dt_us  = r_next.get("elapsed (us)", 0) - r_cur.get("elapsed (us)", 0)
            dt_s   = max(0.01, dt_us / 1_000_000)
            sleep  = dt_s / self.SPEEDS[self.speed_idx]

            self.after(0, self._update_display, idx + 1)
            self.current_idx += 1

            self._stop_event.wait(timeout=sleep)

    def _step_back(self):
        self._pause()
        self._update_display(self.current_idx - 1)

    def _step_fwd(self):
        self._pause()
        self._update_display(self.current_idx + 1)

    def _go_start(self):
        self._pause()
        self._update_display(0)

    def _go_end(self):
        self._pause()
        self._update_display(len(self.records) - 1)

    def _on_slider(self, val):
        idx = int(float(val))
        if idx != self.current_idx:
            # Don't pause—let the user scrub while paused
            self._update_display(idx)

    def _set_speed(self, idx: int):
        self.speed_idx = idx

    def _set_status(self, msg: str):
        self._status_var.set(msg)

def main():
    # Allow an fc2 file to be passed as a command-line argument
    app = DroneViewer()

    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path):
            app.after(200, lambda: app._load_file(path))

    app.mainloop()

if __name__ == "__main__":
    main()
