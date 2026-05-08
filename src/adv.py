#!/usr/bin/env -S python3 -OO
"""
Atom 2 Flight Log Visualizer
Displays drone flight path, telemetry gauges, and RC stick positions
with playback controls. Uses tkinter + tkintermapview.
"""

import os
import sys
import math
import threading
import json
import platform
from pathlib import Path
import tkinter as tk
import tkinter.font as tkf
from io import StringIO
from tkinter import ttk, filedialog, messagebox
from tkinter.colorchooser import askcolor
import tkintermapview
from PIL import Image, ImageDraw, ImageTk, ImageFont
from adeversion import _version
from atom2parser import atom2_parser, log_stats, is_valid_latlon, BASIC_DATA, \
    EXTENDED_DATA, DERIVED_DATA
import mwhlogging
from mwhlogging import MWHLogger

# ─────────────────────────────────────────────────────────────────────────────
# Configure the logger to write to a buffer as well as the console.
#
# We will load the buffer into a dialog box on request.
# ─────────────────────────────────────────────────────────────────────────────
my_logger=MWHLogger("adv")
my_logger.setLevel(mwhlogging.DEBUG)
my_logging_buf=StringIO()
my_logger.configure_logging(file_handle=my_logging_buf)

class LogDialog(tk.Toplevel):
    '''
        Display the contents of the my_logger buffer.
    '''

    def __init__(self, parent, log_buffer: StringIO, prefs, menubar):
        super().__init__(parent)
        self.title("Atom Data Viewer Log")
        self.geometry("640x480")
        self.resizable(True, True)
        self.transient(parent)
        self.configure(menu=menubar)

        btn_row=tk.Frame(self)
        btn_row.pack(fill=tk.X, padx=8, pady=(4, 8), side=tk.BOTTOM)
        tk.Button(btn_row, text="Refresh",
                  command=lambda: self._load(log_buffer)).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Copy All", command=self._copy_all).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_row, text="Close", command=self.destroy).pack(side=tk.RIGHT)

        h_scroll=ttk.Scrollbar(self, orient=tk.HORIZONTAL)
        h_scroll.pack(fill=tk.X, padx=8, side=tk.BOTTOM)

        text_frame=tk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand = True, padx = 8, pady=(8, 4))

        scroll_bar=ttk.Scrollbar(text_frame)
        scroll_bar.pack(side=tk.RIGHT, fill = tk.Y)

        self._text=tk.Text(text_frame, wrap=tk.NONE,
                             yscrollcommand=scroll_bar.set,
                             xscrollcommand=h_scroll.set,
                             font="TkFixedFont",
                             state=tk.DISABLED)
        self._text.pack(fill=tk.BOTH, expand=True)

        h_scroll.configure(command=self._text.xview)
        scroll_bar.configure(command=self._text.yview)

        self._center_on(parent)
        self._load(log_buffer)

    def _center_on(self, parent):
        x=parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y=parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _load(self, log_buffer: StringIO):
        contents=log_buffer.getvalue()
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.insert(tk.END, contents)
        self._text.configure(state=tk.DISABLED)
        self._text.see(tk.END)  # scroll to bottom

    def _copy_all(self):
        self.clipboard_clear()
        self.clipboard_append(self._text.get("1.0", tk.END))

# ─────────────────────────────────────────────────────────────────────────────
# Each pair represents a panel label and the matching data field.
# Section headers begin with None and the second field is the header label.
# None by itself will act as a spacer.
# Items will appear in the panel in the order they are listed.
# ─────────────────────────────────────────────────────────────────────────────
PANEL_ITEMS=[
    (None, "Time"),
    ("Flt Ctr", "Flight Counter"),
    ("Record #", "rid"),
    ("Elapsed", "elapsed (us)"),

    (None, "Status"),
    ("Drn Mode", "Drone Mode (text)"),
    ("Flt Mode", "Flight Mode (text)"),
    ("Pos Mode", "Positioning Mode (text)"),

    (None, "Battery"),
    ("Batt. mV", "Battery (mv)"),
    ("Batt. mA", "Battery Current (ma)"),
    ("Batt. Temp", "Battery Temp (c)"),
    ("Batt. %", "Battery Level (%)"),

    (None, "Position"),
    ("GPS", "GPS Lock"),
    ("Sats", "Satellites"),
    ("Lat", "lat (deg)"),
    ("Lon", "lon (deg)"),
    ("Alt m", "alt (m)"),
    ("HDOP", "HDOP"),
    ("H Lat", "Home Lat (deg)"),
    ("H Lon", "Home Lon (deg)"),

    (None, "Distance"),
    ("2d Dist. m", "2d Derived Distance (m)"),
    ("3d Dist. m", "3d Derived Distance (m)"),
    ("2d T Dist. m", "2d Travelled Distance (m)"),
    ("3d T Dist. m", "3d Travelled Distance (m)"),

    (None, "Orientation"),
    ("Bank Deg", "bank (deg)"),
    ("Pitch Deg", "pitch angle (deg)"),
    ("Heading Deg", "heading (deg)"),

    (None, "Speed"),
    ("2d m/s", "2d Derived Speed (m/s)"),
    ("3d m/s", "3d Derived Speed (m/s)"),

    (None, "Wind"),
    ("Wind Deg", "Wind (deg)"),
    ("Wind m/s", "Wind Speed (m/s)"),

    (None, "Motor"),
    ("1 State", "Motor 1 State"),
    ("1 RPM", "Motor 1 RPM"),
    ("2 State", "Motor 2 State"),
    ("2 RPM", "Motor 2 RPM"),
    ("3 State", "Motor 3 State"),
    ("3 RPM", "Motor 3 RPM"),
    ("4 State", "Motor 4 State"),
    ("4 RPM", "Motor 4 RPM"),

    (None, "Controls"),
    ("Up/Down", "rc elevator"),
    ("Turn", "rc rudder"),
    ("Throttle", "rc throttle"),
    ("Bank", "rc aileron"),

    #Disabling these for performance reasons.
    #(None, "IMU"),
    #("X m/s2", "Accelerometer X (m/s2)"),
    #("Y m/s2", "Accelerometer Y (m/s2)"),
    #("Z m/s2", "Accelerometer Z (m/s2)"),
    #(None),
    #("Gyr X d/s", "Gyroscope X (deg/s)"),
    #("Gyr Y d/s", "Gyroscope Y (deg/s)"),
    #("Gyr Z d/s", "Gyroscope Z (deg/s)"),
    #("Air pres", "Air Pressure (pascals)"),
    #("Mag X", "Magnetometer X"),
    #("Mag Y", "Magnetometer Y"),
]

PANEL_SKIP={ "Elapsed", "Lat", "Lon", "H Lat", "H Lon",
             "Distance", "2d Dist", "3d Dist", "2d Speed",
             "3d Speed"}

PREFS_FILE=Path.home() / ".atom_data_viewer.json"

DEFAULT_PREFS={
    # ─────────────────────────────────────────────────────────────────────────
    # Basic settings.
    # ─────────────────────────────────────────────────────────────────────────
    "window_geometry": "1200x800",
    "log_level"      : "Debug",
    "input_dir"      : str(Path.home()),

    # ─────────────────────────────────────────────────────────────────────────
    # Gauge Limits
    # ─────────────────────────────────────────────────────────────────────────
    "max_speed"      : 57,
    "max_alt"        : 200,
    "max_dist"       : 500,
    "max_wind"       : 10,

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
    "font_label"     : ["TkDefaultFont", 10],
    "font_title"     : ["TkDefaultFont", 13, "bold"],
    "font_marker"    : "",
    "font_small"     : ["TkDefaultFont", 8],
}

# ─────────────────────────────────────────────────────────────────────────────
# Use fonts that should be available on the current platform.
# ─────────────────────────────────────────────────────────────────────────────
PLATFORM_SYSTEM=platform.system()
if PLATFORM_SYSTEM == "Linux":
    DEFAULT_PREFS["font_label"] =["Liberation", 10]
    DEFAULT_PREFS["font_title"] =["Times", 13, "bold"]
    DEFAULT_PREFS["font_marker"]=""
    DEFAULT_PREFS["font_small"] =["Liberation", 8]
elif PLATFORM_SYSTEM == "Darwin":
    DEFAULT_PREFS["font_label"] =["Helvetica Neue", 10]
    DEFAULT_PREFS["font_title"] =["Helvetica Neue", 13, "bold"]
    DEFAULT_PREFS["font_marker"]="/System/Library/Fonts/HelveticaNeue.ttc"
    DEFAULT_PREFS["font_small"] =["Helvetica Neue", 8]

LOG_LEVEL_MAP={
    "Error": mwhlogging.ERROR,
    "Warning": mwhlogging.WARNING,
    "Info": mwhlogging.INFO,
    "Debug": mwhlogging.DEBUG,
}

def load_prefs() -> dict:
    my_logger.debug("Loading preferences from %s", PREFS_FILE)
    try:
        if PREFS_FILE.exists():
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                saved=json.load(f)
            prefs=DEFAULT_PREFS.copy()
            prefs.update(saved)
            return prefs
    except Exception as e:
        messagebox.showerror("Failed to load the saved preferences.", str(e))
        my_logger.error("Failed to load the saved preferences: %s", str(e))

    return DEFAULT_PREFS.copy()

def save_prefs(prefs: dict) -> None:
    my_logger.debug("Saving preferences to %s", PREFS_FILE)
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        messagebox.showerror("Failed to save the preferences.", str(e))
        my_logger.error("Failed to save the preferences: %s", str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Preferences Dialog
# ─────────────────────────────────────────────────────────────────────────────

class PrefsDialog(tk.Toplevel):
    """
    Modal dialog for editing the application preferences.
    Edits a copy of prefs and calls on_save(new_prefs) if the user clicks Save.
    """

    COLOR_FIELDS=[
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

    FONT_FIELDS=[
        ("font_label",  "Label Font"),
        ("font_title",  "Title Font"),
        ("font_small",  "Small Font"),
    ]

    # Use this to restrict input on the numeric fields.
    @staticmethod
    def _validate_digit(P) -> bool:
        return (P.isdigit() or P =="")

    def __init__(self, parent, prefs: dict, on_save, menubar):
        super().__init__(parent)
        my_logger.debug("Creating the Prefs dialog")
        self.title("Preferences")
        self.resizable(False, False)
        self.grab_set()             # make modal
        self.transient(parent)      # keep on top of parent
        self.menubar=menubar
        self.validate=parent.register(self._validate_digit)

        self.configure(menu=self.menubar)
        self._prefs  =prefs.copy()
        self._on_save=on_save
        self._swatches: dict[str, tk.Label]={}
        self._font_vars: dict[str, tuple]  ={}

        self._build()
        self._center_on(parent)

    # ── Layout ────────────────────────────────────────────────────────────

    def _build(self):
        PAD={"padx" : 10, "pady" : 4}

        tk.Label(self, text="Some changes will not take effect until restart.",
             font=self._prefs["font_label"]).pack(padx=12, pady=(8, 0),
                                                  anchor="w")

        # ── Limits ────────────────────────────────────────────────────────
        limits_frame=tk.LabelFrame(self, text="Gauge Limits", padx=6, pady=6)
        limits_frame.pack(fill=tk.X, padx=4, pady=4)

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
            col=(i % 2) * 3       # 3 columns per side: label | swatch | button

            tk.Label(color_frame, text=label + ":", anchor="w",
                     width=12).grid(row=row, column=col, sticky="w", **PAD)

            swatch=tk.Label(color_frame, width=3,
                              bg=self._prefs.get(key, "#000000"),
                              relief=tk.SOLID, bd=1)
            swatch.grid(row=row, column=col + 1, padx=(0, 4), pady=4)
            self._swatches[key]=swatch

            tk.Button(color_frame, text="Choose…",
                      command=lambda k=key: self._pick_color(k),
                      padx=4).grid(row=row, column=col + 2, **PAD)

        # ── Fonts ─────────────────────────────────────────────────────────
        font_frame=tk.LabelFrame(self, text=" Fonts ", padx=6, pady=6)
        font_frame.pack(fill=tk.X, padx=4, pady=4)

        families=self._get_font_families()

        for i, (key, label) in enumerate(self.FONT_FIELDS):
            current=self._prefs.get(key, ("Helvetica", 10))
            # current may be a list if loaded from JSON (JSON turns tuples into lists)
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

        # Font marker path (separate — it's a file path, not a tkinter font)
        tk.Label(font_frame, text="Marker Font:", anchor="w",
                width=12).grid(row=len(self.FONT_FIELDS), column=0,
                                sticky="w", padx=(10, 4), pady=4)
        self._marker_var=tk.StringVar(value=self._prefs.get("font_marker", ""))
        tk.Entry(font_frame, textvariable=self._marker_var,
                width=28).grid(row=len(self.FONT_FIELDS), column=1,
                                columnspan=2, padx=4, pady=4, sticky="w")
        tk.Button(font_frame, text="Browse…",
                command=self._pick_marker_font).grid(
            row=len(self.FONT_FIELDS), column=3, padx=4, pady=4)

        # ── Logging ───────────────────────────────────────────────────────
        log_frame=tk.LabelFrame(self, text=" Logging ", padx=6, pady=6)
        log_frame.pack(fill=tk.X, padx=12, pady=4)

        tk.Label(log_frame, text="Log Level:").pack(side=tk.LEFT, padx=(4, 8))
        self._log_var=tk.StringVar(value=self._prefs.get("log_level", "Info"))
        for level in ("Error", "Warning", "Info", "Debug"):
            tk.Radiobutton(log_frame, text=level,
                           variable=self._log_var, value=level).pack(
                side=tk.LEFT, padx=4)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_row=tk.Frame(self)
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
        path=filedialog.askopenfilename(
            title="Select marker font file",
            filetypes=[("Font files", "*.ttf *.ttc *.otf"), ("All files", "*.*")],
            parent=self
        )
        if path:
            self._marker_var.set(path)

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

    def _restore_defaults(self):
        self._max_speed.set(DEFAULT_PREFS.get("max_speed"))
        self._max_dist.set(DEFAULT_PREFS.get("max_dist"))
        self._max_alt.set(DEFAULT_PREFS.get("max_alt"))
        self._max_wind.set(DEFAULT_PREFS.get("max_wind"))
        for key, _ in self.COLOR_FIELDS:
            default=DEFAULT_PREFS.get(key, "#000000")
            self._prefs[key]=default
            self._swatches[key].configure(bg=default)
        for key, _ in self.FONT_FIELDS:
            default=DEFAULT_PREFS.get(key, ("Helvetica", 10))
            family_var, size_var, bold_var=self._font_vars[key]
            family_var.set(default[0])
            size_var.set(default[1])
            bold_var.set(len(default) > 2 and default[2] == "bold")
        self._marker_var.set(DEFAULT_PREFS.get("font_marker", ""))
        self._log_var.set(DEFAULT_PREFS.get("log_level", "Info"))
        self.update_idletasks()


    def _save(self):
        for key, _ in self.FONT_FIELDS:
            family_var, size_var, bold_var=self._font_vars[key]
            if bold_var.get():
                self._prefs[key]=(family_var.get(), size_var.get(), "bold")
            else:
                self._prefs[key]=(family_var.get(), size_var.get())

        self._prefs["font_marker"]=self._marker_var.get()
        self._prefs["log_level"]=self._log_var.get()
        self._prefs["max_speed"]=int(self._max_speed.get())
        self._prefs["max_dist"]=int(self._max_dist.get())
        self._prefs["max_alt"]=int(self._max_alt.get())
        self._prefs["max_wind"]=int(self._max_wind.get())
        self._on_save(self._prefs)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
# Canvas-based gauge widgets
# ─────────────────────────────────────────────────────────────────────────────

class CompassGauge(tk.Canvas):

    def __init__(self, parent, prefs:dict, label="", size=120, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        my_logger.debug("Creating Compass %s", label)
        self.prefs=prefs
        self.label=label
        self.size=size
        self.heading=0.0
        self._draw_static()
        self._draw()

    def _draw_static(self):
        s=self.size
        cx=cy = s / 2
        r=s / 2 - 4

        self.delete("all")

        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                         outline=self.prefs["color_border"], width=2,
                         fill=self.prefs["color_gauge_bg"])

        for label, angle in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            rad=math.radians(angle - 90)
            lx=cx + (r - 14) * math.cos(rad)
            ly=cy + (r - 14) * math.sin(rad)
            color=self.prefs["color_danger"] if label == "N" else self.prefs["color_label"]
            self.create_text(lx, ly, text=label, fill=color,
                             font=self.prefs["font_small"])

        for i in range(36):
            ang=math.radians(i * 10 - 90)
            inner=r - 6 if i % 9 == 0 else r - 4
            x1=cx + inner * math.cos(ang)
            y1=cy + inner * math.sin(ang)
            x2=cx + r * math.cos(ang)
            y2=cy + r * math.sin(ang)
            self.create_line(x1, y1, x2, y2, fill=self.prefs["color_border"])

        self.create_text(cx, cy - r * 0.25,
                         text=self.label, fill=self.prefs["color_label"],
                         font=self.prefs["font_small"])


    def _draw(self):

        self.delete("dynamic")

        s=self.size
        cx=cy = s / 2
        r=s / 2 - 4
        needle_rad=math.radians(self.heading - 90)
        nx=cx + (r - 18) * math.cos(needle_rad)
        ny=cy + (r - 18) * math.sin(needle_rad)
        tx=cx - 8 * math.cos(needle_rad)
        ty=cy - 8 * math.sin(needle_rad)

        self.create_line(tx, ty, nx, ny, fill=self.prefs["color_accent"],
                         width=2, arrow=tk.LAST, arrowshape=(8,10,3), tags="dynamic")
        self.create_oval(cx-3, cy-3, cx+3, cy+3,
                         fill=self.prefs["color_accent"], outline="", tags="dynamic")
        self.create_text(cx, s-8, text=f"{self.heading:.1f}°",
                         fill=self.prefs["color_value"], font=self.prefs["font_small"],
                         tags="dynamic")

    def set_value(self, heading: float):
        h = heading % 360
        if self.heading != h:
            self.heading = h
            self._draw()


class ArcGauge(tk.Canvas):
    """
    Semi-circular arc gauge for a single numeric value.
    Shows a coloured arc fill + needle + numeric readout.
    """

    def __init__(self, parent, prefs:dict, label=None, min_val=0, max_val=0,
                 unit="", warn_pct=0.5, danger_pct=0.95,
                 size=110, **kw):
        super().__init__(parent, width=size, height=int(size * 0.6),
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        my_logger.debug("Creating Gauge %s", label)
        self.prefs    =prefs
        self.label    =label
        self.min_val  =min_val
        self.max_val  =max_val
        self.unit     =unit
        self.warn_pct =warn_pct
        self.danger_pct= danger_pct
        self.size     =size
        self.value    =min_val
        self._draw_static()
        self._draw()

    def _draw_static(self):
        s=self.size
        h=int(s * 0.6)
        cx=s / 2
        cy=h * 0.88
        r =s * 0.42

        self.delete("all")

        # Background arc (180°)
        self.create_arc(cx-r, cy-r, cx+r, cy+r,
                        start=0, extent=180,
                        style=tk.ARC, outline=self.prefs["color_border"], width=8)

        # Label
        self.create_text(cx, cy - r * 0.5,
                         text=self.label, fill=self.prefs["color_label"],
                         font=self.prefs["font_small"])

    def _draw(self):
        s=self.size
        h=int(s * 0.6)
        cx=s / 2
        cy=h * 0.88
        r =s * 0.42

        self.delete("dynamic")

        # Value
        val_text=f"{self.value:.1f}{self.unit}"
        self.create_text(cx, cy - 10, tags="dynamic",
                         text=val_text, fill=self.prefs["color_value"],
                         font=self.prefs["font_label"])

        # Colored fill arc
        pct=(self.value - self.min_val) / max(self.max_val - self.min_val, 1e-9)
        pct=max(0.0, min(1.0, pct))
        extent=pct * 180

        color=self.prefs["color_safe"]
        if pct >= self.danger_pct:
            color=self.prefs["color_danger"]
        elif pct >= self.warn_pct:
            color=self.prefs["color_warn"]

        if extent > 0:
            self.create_arc(cx-r, cy-r, cx+r, cy+r, tags="dynamic",
                            start=180 - extent, extent=extent,
                            style=tk.ARC, outline=color, width=8)

        # Needle
        needle_angle=math.radians(180 - pct * 180)
        nx=cx + (r - 2) * math.cos(needle_angle)
        ny=cy - (r - 2) * math.sin(needle_angle)
        self.create_line(cx, cy, nx, ny, fill=self.prefs["color_value"],
                         tags="dynamic", width=2)
        self.create_oval(cx-3, cy-3, cx+3, cy+3, fill=self.prefs["color_value"],
                         tags="dynamic", outline="")

    def set_value(self, value: float):
        if value != self.value:
            self.value=value
            self._draw()


class StickDisplay(tk.Canvas):
    """
    Renders a single joystick as a 2D crosshair inside a square.
    x_val, y_val should be in range 0..2048 (centre=1024).
    """

    def __init__(self, parent, prefs, label, size=100, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        my_logger.debug("Creating Stick %s", label)
        self.prefs =prefs
        self.label =label
        self.size  =size
        self.pad   =2
        self.inner =size - 2 * self.pad
        self.x_val =1024.0   # 0..2048
        self.y_val =1024.0
        self.mid   =size / 2
        self._draw_static()
        self._draw()

    def _draw_static(self):
        self.delete("all")

        # Box
        self.create_rectangle(self.pad, self.pad, self.size - self.pad,
                              self.size - self.pad,
                              outline=self.prefs["color_border"],
                              fill=self.prefs["color_gauge_bg"])

        # Centre cross
        self.create_line(self.pad, self.mid, self.size - self.pad, self.mid,
                         fill=self.prefs["color_border"], dash=(2, 3))
        self.create_line(self.mid, self.pad, self.mid, self.size - self.pad,
                         fill=self.prefs["color_border"], dash=(2, 3))

        # Label
        self.create_text(self.mid, self.size - 5, text=self.label,
                         fill=self.prefs["color_label"], font=self.prefs["font_small"])

    def _draw(self):

        self.delete("dynamic")

        # Dot position
        nx=self.pad + (self.x_val / 2048.0) * self.inner
        ny=self.pad + (1.0 - self.y_val / 2048.0) * self.inner  # invert Y

        # Glow circle
        gr=12
        self.create_oval(nx - gr, ny - gr, nx + gr, ny + gr, tags="dynamic",
                         fill=self.prefs["color_gauge_bg"], outline="")
        self.create_oval(nx - 5, ny - 5, nx + 5, ny + 5, tags="dynamic",
                         fill=self.prefs["color_accent"], outline="")

    def set_values(self, x_val: float, y_val: float):
        if x_val != self.x_val or self.y_val != y_val:
            self.x_val=x_val
            self.y_val=y_val
            self._draw()


class BarGauge(tk.Canvas):
    """Vertical bar gauge (e.g. battery, satellites)."""

    def __init__(self, parent, prefs, label="", min_val=0, max_val=10,
                 unit="", size_w=50, size_h=90, warn_low=False,
                 warn_high=False, danger_low=False, danger_high=False, **kw):
        super().__init__(parent, width=size_w, height=size_h,
                         bg=prefs["color_bg"], highlightthickness=0, **kw)
        my_logger.debug("Creating Bar %s", label)
        self.prefs  =prefs
        self.label  =label
        self.min_val=min_val
        self.max_val=max_val
        self.unit   =unit
        self.size_w =size_w
        self.size_h =size_h
        self.value  =min_val
        self.warn_low=warn_low
        self.warn_high=warn_high
        self.danger_low=danger_low
        self.danger_high=danger_high
        self._draw_static()
        self._draw()

    def _draw_static(self):
        w=self.size_w
        h=self.size_h
        pad_x=8
        bar_top=18
        bar_bot=h - 24

        self.delete("all")

        # Background
        self.create_rectangle(pad_x, bar_top, w - pad_x, bar_bot,
                              outline=self.prefs["color_border"],
                              fill=self.prefs["color_gauge_bg"])

        # Label
        self.create_text(w / 2, 9, text=self.label,
                         fill=self.prefs["color_label"],
                         font=self.prefs["font_small"])

    def _draw(self):
        w=self.size_w
        h=self.size_h
        pad_x=8
        bar_top=18
        bar_bot=h - 24
        bar_h  =bar_bot - bar_top

        self.delete("dynamic")

        pct=(self.value - self.min_val) / max(self.max_val - self.min_val, 1e-9)
        pct=max(0.0, min(1.0, pct))

        color=self.prefs["color_safe"]
        if self.danger_low is not False and pct <= self.danger_low:
            color=self.prefs["color_danger"]
        elif self.warn_low is not False and pct <= self.warn_low:
            color=self.prefs["color_warn"]
        elif self.danger_high is not False and pct >= self.danger_high:
            color=self.prefs["color_danger"]
        elif self.warn_high is not False and pct >= self.warn_high:
            color=self.prefs["color_warn"]

        fill_top=bar_bot - pct * bar_h
        if pct > 0:
            self.create_rectangle(pad_x + 1, fill_top,
                                  w - pad_x - 1, bar_bot - 1,
                                  fill=color, outline="",
                                  tags="dynamic")

        # Value
        self.create_text(w / 2, h - 10, tags="dynamic",
                         text=f"{self.value:.0f}{self.unit}",
                         fill=self.prefs["color_value"],
                         font=self.prefs["font_small"])

    def set_value(self, value: float):
        # Don't redraw unless the value has changed.
        if self.value != value:
            self.value=value
            self._draw()


# ─────────────────────────────────────────────────────────────────────────────
# Text info panel
# ─────────────────────────────────────────────────────────────────────────────

class InfoPanel(tk.LabelFrame):
    """Key/value text readout for status fields."""

    def __init__(self, parent, prefs, fields: list, **kw):
        super().__init__(parent, bg=prefs["color_bg"], **kw)
        my_logger.debug("Creating InfoPanel")
        self._vars={}
        self._labels=[]
        self.prefs=prefs

        self._canvas=tk.Canvas(self, bg=prefs["color_bg"],
                                 highlightthickness=0, height=64)
        scrollbar=ttk.Scrollbar(self, orient=tk.VERTICAL,
                                  command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner=tk.Frame(self._canvas, bg=prefs["color_bg"])
        self._window_id=self._canvas.create_window((0,0), window=self._inner,
                                                     anchor="nw")

        # Resize the scroll region whenever the inner frame changes size
        self._inner.bind("<Configure>", self._on_inner_configure)
        # Stretch the inner frame to fill canvas width
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        col=0
        row=0
        ufont=self.prefs["font_label"].copy()
        ufont.append("underline")

        for field in fields:
            if field is None:
                row += 1
                col=0
                continue

            if field[0] is None:
                if col > 0:
                    row += 1
                if field[1] is not None:
                    lbl=tk.Label(self._inner, text=field[1],
                                bg=self.prefs["color_bg"],
                                fg=self.prefs["color_accent"],
                                font=ufont,
                                anchor="w")
                    lbl.grid(row=row, column=0, columnspan=4,
                            sticky="ew", padx=6, pady=(6, 1))
                row += 1
                col=0
                continue

            key_lbl=tk.Label(self._inner, text=field[0] + ":", bg=self.prefs["color_bg"],
                    fg=self.prefs["color_label"],
                    font=self.prefs["font_label"],
                    anchor="w")
            key_lbl.grid(row=row, column=col, sticky="w",
                        padx=(6, 2), pady=1)
            var=tk.StringVar(value="—")
            val_lbl=tk.Label(self._inner, textvariable=var,
                                bg=self.prefs["color_bg"],
                                fg=self.prefs["color_value"],
                                font=self.prefs["font_label"],
                                anchor="w")
            val_lbl.grid(row=row, column=col+1, sticky="w",
                            padx=(2, 6), pady=1)
            col += 2
            if col > 2:
                col=0
                row += 1

            self._vars[field[0]]=var
            self._labels.append((key_lbl, val_lbl))

        self._bind_mousewheel(self._inner)

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>",  self._on_mousewheel)      # Windows/macOS
        widget.bind("<Button-4>",    self._on_mousewheel)      # Linux scroll up
        widget.bind("<Button-5>",    self._on_mousewheel)      # Linux scroll down
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def _on_inner_configure(self, event):
        """Update scroll region when inner frame resizes."""
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        """Keep inner frame width matched to canvas width."""
        self._canvas.itemconfig(self._window_id, width=event.width)

    def _on_mousewheel(self, event):
        if event.num == 4:          # Linux scroll up
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:        # Linux scroll down
            self._canvas.yview_scroll(1, "units")
        else:                       # Windows / macOS
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def redraw(self):
        """Reconfigure all labels to pick up changed prefs."""
        self._canvas.configure(bg=self.prefs["color_bg"])
        self._inner.configure(bg=self.prefs["color_bg"])
        self.configure(bg=self.prefs["color_bg"])
        for key_lbl, val_lbl in self._labels:
            key_lbl.configure(bg=self.prefs["color_bg"],
                              fg=self.prefs["color_label"],
                              font=self.prefs["font_label"])
            val_lbl.configure(bg=self.prefs["color_bg"],
                              fg=self.prefs["color_value"],
                              font=self.prefs["font_label"])

    def update_field(self, name: str, value):
        if name in self._vars:
            new = str(value)
            if new != self._vars[name].get():
                self._vars[name].set(new)


# ─────────────────────────────────────────────────────────────────────────────
# Main application window
# ─────────────────────────────────────────────────────────────────────────────

class DroneViewer(tk.Tk):

    def __init__(self):
        super().__init__()

        my_logger.debug("Creating DroneViewer window")

        self.prefs=load_prefs()

        self.title("Atom 2 Flight Log Viewer")
        self.configure(bg=self.prefs["color_bg"])
        self.minsize(1100, 720)

        my_logger.setLevel(LOG_LEVEL_MAP[self.prefs["log_level"]])
        geometry=self.prefs.get("window_geometry", "1280x800")

        self.geometry(geometry)

        # ── State ─────────────────────────────────────────────────────────
        self.records            =[]
        self.current_idx        =0
        self.playing            =False
        self.pending_update     =False
        self.speed_idx          =0
        self.playback_thread    =None
        self._stop_event        =threading.Event()

        # Map markers / path
        self._path_line         =None
        self._drone_marker      =None
        self._drone_heading     =-1
        self._drone_cache       ={}
        self._home_marker       =None
        self._played_path       =[]         # coords shown so far
        self._heading           =None

        self._apply_styles()
        self._build_ui()

        # Make a loop-invariant list of info fields to update.
        self.PANEL_UPDATE_ITEMS = [
            (label, key) for (label, key) in
            (f for f in PANEL_ITEMS if f is not None and f[0] is not None)
            if label not in PANEL_SKIP
        ]

        # Adding support for double-clicking on fc2 files.
        if platform.system() == "Darwin":
            self.createcommand('::tk::mac::OpenDocument', 
                self.mac_handle_doubleclick)

    def mac_handle_doubleclick(self, *filenames):
        self.after(100, lambda: self.load_file(filenames[0]))

    # ── UI construction ───────────────────────────────────────────────────
    def _show_prefs(self):
        if self.playing:
            self._pause()
        PrefsDialog(self, self.prefs, self._on_prefs_saved, self.menubar)

    def _show_log(self):
        LogDialog(self, my_logging_buf, self.prefs, self.menubar)

    def _on_prefs_saved(self, new_prefs: dict):
        self.prefs.update(new_prefs)
        save_prefs(self.prefs)
        my_logger.setLevel(LOG_LEVEL_MAP[self.prefs["log_level"]])
        # Redraw all canvas gauges so they pick up the new colors immediately
        self._gauge_speed.max_val=self.prefs["max_speed"]
        self._gauge_dist.max_val=self.prefs["max_dist"]
        self._gauge_alt.max_val=self.prefs["max_alt"]
        self._gauge_wind.max_val=self.prefs["max_wind"]
        for widget in (self._gauge_speed, self._gauge_alt, self._gauge_dist,
                       self._gauge_compass, self._bar_battery, self._bar_sats,
                       self._bar_wind, self._stick_left,
                       self._stick_right, self._gauge_wind):
            widget._draw_static()
            widget._draw()
        self.info.redraw()

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
        self.prefs["window_geometry"]=self.geometry()
        save_prefs(self.prefs)
        self.quit()

    def _build_ui(self):

        my_logger.debug("Building the UI")

        self.option_add('*tearOff', False)

        self.menubar=tk.Menu(self)
        self.configure(menu=self.menubar)

        file_menu=tk.Menu(self.menubar)
        self.menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open FC2", command=self._open_file)
        file_menu.add_separator()
        file_menu.add_command(label="Preferences…", command=self._show_prefs)  # ← add this
        file_menu.add_separator()
        file_menu.add_command(label="About", command=self._show_about)
        file_menu.add_command(label="View Log…", command=self._show_log)
        file_menu.add_command(label="Quit", command=self._on_close)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.createcommand("tk::mac::Quit", self._on_close)

        # ── Top bar ───────────────────────────────────────────────────────
        top=tk.Frame(self, bg=self.prefs["color_bg"], pady=6)
        top.pack(fill=tk.X, side=tk.TOP)

        tk.Label(top, text="ATOM 2 FLIGHT VIEWER",
                 bg=self.prefs["color_bg"], fg=self.prefs["color_accent"],
                 font=self.prefs["font_title"]).pack(side=tk.LEFT, padx=16)

        self._file_label=tk.Label(top, text="No file loaded",
                                    bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                                    font=self.prefs["font_title"])
        self._file_label.pack(side=tk.LEFT, padx=8)

        open_btn=tk.Button(top, text="Open FC2…",
                             command=self._open_file,
                             fg=self.prefs["color_bg"], relief=tk.FLAT,
                             font=self.prefs["font_label"],
                             padx=10, pady=2, cursor="hand2")
        open_btn.pack(side=tk.RIGHT, padx=16)

        # ── Main paned area ───────────────────────────────────────────────
        main_pane=tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              bg=self.prefs["color_bg"], sashwidth=4, sashrelief=tk.FLAT)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Left: map
        map_frame=tk.Frame(main_pane, bg=self.prefs["color_bg"])
        main_pane.add(map_frame, stretch="always", minsize=500)

        self.map_widget=tkintermapview.TkinterMapView(
            map_frame, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True)

        # Override the scroll wheel, it doesn't seem to work correctly in
        # Darwin.
        if PLATFORM_SYSTEM == "Darwin":
            def _map_mouse_zoom(event):
                relative_x=event.x / self.map_widget.width
                relative_y=event.y / self.map_widget.height
                delta=event.delta * 0.01
                new_zoom=self.map_widget.zoom + delta
                self.map_widget.set_zoom(new_zoom,
                             relative_pointer_x=relative_x,
                             relative_pointer_y=relative_y)

            self.map_widget.canvas.bind("<MouseWheel>", _map_mouse_zoom)

        # Right: gauges + controls
        right=tk.Frame(main_pane, bg=self.prefs["color_bg"], width=380)
        right.pack_propagate(False)
        main_pane.add(right, stretch="never", minsize=380)

        self._build_gauges(right)
        self._build_controls(right)

        # ── Bottom status bar ─────────────────────────────────────────────
        bot=tk.Frame(self, bg=self.prefs["color_bg"], pady=3)
        bot.pack(fill=tk.X, side=tk.BOTTOM)

        self._status_var=tk.StringVar(value="Ready. Open an FC2 file to begin.")
        tk.Label(bot, textvariable=self._status_var,
                 bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                 font=self.prefs["font_small"]).pack(side=tk.LEFT, padx=10)

        self._progress_var=tk.StringVar(value="0 / 0")
        tk.Label(bot, textvariable=self._progress_var,
                 bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                 font=self.prefs["font_small"]).pack(side=tk.RIGHT, padx=10)

    def _build_gauges(self, parent):
        """Build the entire right-side gauge panel."""

        my_logger.debug("Building the Gauges")

        # ── Section: Arc gauges row ───────────────────────────────────────
        arc_row=tk.LabelFrame(parent, bg=self.prefs["color_bg"])
        arc_row.pack(fill=tk.X, padx=6, pady=(6, 0))

        self._gauge_speed =ArcGauge(arc_row, self.prefs, "SPEED", min_val=0,
                                      max_val=self.prefs["max_speed"],
                                      unit=" kph",
                                      warn_pct=0.5, danger_pct=0.8, size=110)
        self._gauge_alt   =ArcGauge(arc_row, self.prefs, "ALT", min_val=0,
                                      max_val=self.prefs["max_alt"],
                                      unit=" m",
                                      warn_pct=0.5, danger_pct=0.8, size=110)
        self._gauge_dist  =ArcGauge(arc_row, self.prefs, "DIST", min_val=0,
                                      max_val=self.prefs["max_dist"],
                                      unit=" m",
                                      warn_pct=0.5, danger_pct=0.8, size=110)

        for g in (self._gauge_speed, self._gauge_alt, self._gauge_dist):
            g.pack(side=tk.LEFT, expand=True)

        # ── Section: Compass + bars ───────────────────────────────────────
        mid_row=tk.Frame(parent, bg=self.prefs["color_bg"])
        mid_row.pack(fill=tk.X, padx=6, pady=4)

        self._gauge_compass=CompassGauge(mid_row, self.prefs, label="HEADING", size=110)
        self._gauge_compass.pack(side=tk.LEFT, padx=(0, 8))

        bars=tk.Frame(mid_row, bg=self.prefs["color_bg"])
        bars.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._bar_battery=BarGauge(bars, self.prefs, label="BATT",
                                     max_val=100, unit="%", size_w=36,
                                     size_h=110, warn_low=0.5, danger_low=0.25)
        self._bar_sats   =BarGauge(bars, self.prefs, label="SATS", max_val=30,
                                     size_w=36, size_h=110, warn_low=0.5,
                                     danger_low=0.3)
        self._bar_wind   =BarGauge(bars, self.prefs, label="WIND",
                                     max_val=self.prefs["max_wind"],
                                     unit=" m/s", size_w=36, size_h=110,
                                     warn_high=0.5, danger_high=0.9)

        for b in (self._bar_battery, self._bar_sats, self._bar_wind):
            b.pack(side=tk.LEFT, padx=2)

        self._gauge_wind=CompassGauge(mid_row, self.prefs, label="WIND", size=110)
        self._gauge_wind.pack(side=tk.LEFT, padx=(0, 8))

        # ── Section: Text info ────────────────────────────────────────────
        info_frame=tk.Frame(parent, bg=self.prefs["color_bg"], bd=0)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self.info=InfoPanel(info_frame, self.prefs, PANEL_ITEMS)
        self.info.pack(fill=tk.BOTH, expand=True)

        # ── Section: RC Sticks ────────────────────────────────────────────
        sticks_frame=tk.Frame(parent, bg=self.prefs["color_bg"])
        sticks_frame.pack(padx=6, pady=6)

        tk.Label(sticks_frame, text="CONTROLLER",
                 bg=self.prefs["color_bg"], fg=self.prefs["color_label"],
                 font=self.prefs["font_small"]).pack(padx=8)

        self._stick_left =StickDisplay(sticks_frame, self.prefs,
                                         "Throttle & Yaw",  size=110)
        self._stick_right=StickDisplay(sticks_frame, self.prefs,
                                         "Pitch & Bank", size=110)
        self._stick_left.pack(side=tk.LEFT, padx=(0, 4))
        self._stick_right.pack(side=tk.LEFT)

    def _build_controls(self, parent):
        """Transport controls at the bottom of the right panel."""

        my_logger.debug("Building the Controls")

        ctrl=tk.LabelFrame(parent, bg=self.prefs["color_bg"], pady=8)
        ctrl.pack(fill=tk.X, side=tk.BOTTOM, padx=0, pady=0)

        # Slider
        self._slider_var=tk.IntVar(value=0)
        self._slider=ttk.Scale(ctrl, from_=0, to=1,
                                 variable=self._slider_var,
                                 orient=tk.HORIZONTAL,
                                 command=self._on_slider)
        self._slider.pack(fill=tk.X, padx=10, pady=(4, 6))

        btn_row=tk.Frame(ctrl, bg=self.prefs["color_bg"])
        btn_row.pack()

        def btn(text, cmd, color=self.prefs["color_gauge_bg"], fg=self.prefs["color_value"]):
            return tk.Button(btn_row, text=text, command=cmd,
                             bg=color, fg=fg, relief=tk.FLAT,
                             font=self.prefs["font_label"],
                             cursor="hand2", activebackground=self.prefs["color_border"],
                             activeforeground=color, bd=1)

        self.bind("<space>",      lambda e: self._toggle_play())
        self.bind("<Left>",       lambda e: self._step_back())
        self.bind("<Right>",      lambda e: self._step_fwd())

        if PLATFORM_SYSTEM == "Darwin":
            self._btn_rw   =btn("⏮️", self._slow_down)
            self._btn_back =btn("⏪", self._step_back)
            self._btn_play =btn("▶️", self._toggle_play)
            self._btn_fwd  =btn("⏩", self._step_fwd)
            self._btn_ff   =btn("⏭️", self._speed_up)
            self.bind("<Command-o>",  lambda e: self._open_file())  # macOS
        else:
            self._btn_rw   =btn("<<<", self._slow_down)
            self._btn_back =btn("<<", self._step_back)
            self._btn_play =btn(">", self._toggle_play)
            self._btn_fwd  =btn(">>", self._step_fwd)
            self._btn_ff   =btn(">>>", self._speed_up)
            self.bind("<Control-o>",  lambda e: self._open_file())  # Windows/Linux

        for b in (self._btn_rw, self._btn_back, self._btn_play,
                  self._btn_fwd, self._btn_ff):
            b.pack(side=tk.LEFT, padx=2)

        # Speed selector
        speed_row=tk.Frame(ctrl, bg=self.prefs["color_bg"])
        speed_row.pack(pady=(4, 2))

        self._speed_var=tk.StringVar(value="1×")
        speeds=["1×", "2×", "4×", "8×", "16×"]
        for i, label in enumerate(speeds):
            rb=tk.Radiobutton(speed_row, text=label,
                                variable=self._speed_var, value=label,
                                command=lambda i=i: self._set_speed(i),
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
        style=ttk.Style(self)
        # Use a native-looking theme on each platform
        available=style.theme_names()
        # For some reason, "clam" sometimes messes up the radio buttons in
        # Ubuntu, so prefer "alt" over "clam".
        for preferred in ("aqua", "vista", "alt", "clam", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break

        style.configure("TScale", background=self.prefs["color_gauge_bg"],
                        troughcolor=self.prefs["color_border"],
                        slidercolor=self.prefs["color_accent"])

    # ── File loading ──────────────────────────────────────────────────────

    def _open_file(self):
        file=filedialog.askopenfilename(
            title="Open Atom 2 FC2 Log",
            initialdir=self.prefs.get("input_dir",""),
            filetypes=[("FC2 flight logs", "*.fc2"), ("All files", "*.*")]
        )
        if not file or not Path(file).exists():
            return

        self.prefs["input_dir"] = str(Path(file).parent)

        self.load_file(file)

    def load_file(self, path: str):
        my_logger.info("Loading %s", path)
        self._set_status("Loading…")
        self.update_idletasks()

        try:
            records=atom2_parser(file_name=path, logger=my_logger)
        except Exception as e:
            messagebox.showerror("Parse error", str(e))
            self._set_status("Error loading file.")
            return

        self.records=[r for r in records if r.get("GPS Lock") == "Yes"]
        if not self.records:
            messagebox.showwarning("No data",
                "No valid records found in this file.")
            return
        self.records_len=len(self.records) - 1

        self.coords=[(r["lat (deg)"], r["lon (deg)"]) for r in self.records]

        self.current_idx=0

        # Slider range
        self._slider.configure(to=len(self.records) - 1)
        self._slider_var.set(0)

        # Draw full path on map
        self._draw_map_path()

        self._bar_wind.max_val=self.prefs["max_wind"]
        self._gauge_alt.max_val=self.prefs["max_alt"]
        self._gauge_speed.max_val=self.prefs["max_speed"]
        self._gauge_dist.max_val=self.prefs["max_dist"]

        # Get the initial bounding box for the map.
        field_range=[r[0] for r in self.coords]
        self.min_lat, self.max_lat=min(field_range),max(field_range)
        field_range=[r[1] for r in self.coords]
        self.min_lon, self.max_lon=min(field_range),max(field_range)

        # Centre map on first point, scale the map to fit the entire path.
        my_logger.debug("Map bounding box: %s, %s",
                        (self.max_lat,self.min_lon), (self.min_lat,self.max_lon))
        self.map_widget.fit_bounding_box((self.max_lat, self.min_lon),
                                         (self.min_lat, self.max_lon))

        if my_logger.level <= mwhlogging.INFO:
            log_stats(my_logger, records)

        self._file_label.configure(text=os.path.basename(path))
        self._set_status(f"Loaded {len(records)} GPS records.")
        self._update_display(0)

    # ── Map drawing ───────────────────────────────────────────────────────

    def _draw_map_path(self):
        if self._path_line:
            self._path_line.delete()
            self._path_line=None

        if len(self.coords) >= 2:
            self._path_line=self.map_widget.set_path(
                self.coords, color=self.prefs["color_path"], width=4)

    #
    # Icons for the map
    #
    def _make_drone_icon(self, heading) -> ImageTk.PhotoImage:
        """Draw a simple arrow head rotated to the current heading."""
        size=21 # Make this an odd number so we actually have a center pixel.
        # Note we add 4 pixels of padding on all sides to make sure there's
        # room for the rotation.
        pad=4
        tsize=size + pad * 2
        img=Image.new("RGBA", (tsize, tsize), (0, 0, 0, 0))
        draw=ImageDraw.Draw(img)

        cx=cy = tsize // 2

        # Draw a simple arrow/chevron pointing "up" (north=0°)
        # Note the 4-pixel pad on the top and left.
        draw.polygon([(cx, pad),
                      (cx + size//2, pad + size),
                      (cx, cy+ pad),
                      (cx - size//2, pad + size)],
                    fill=self.prefs["color_danger"], outline=self.prefs["color_border"])

        img=img.rotate(-heading, resample=Image.BICUBIC, expand=False)

        return ImageTk.PhotoImage(img)

    def _make_home_icon(self) -> ImageTk.PhotoImage:
        size=20
        img=Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw=ImageDraw.Draw(img)

        cc=size // 2

        if self.prefs["font_marker"] == "":
            # Draw a simple house icon.
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
            font=ImageFont.truetype(self.prefs["font_marker"], size)
            draw.ellipse([(0,0),(size,size)], fill=self.prefs["color_bg"],
                         outline=self.prefs["color_path"])
            draw.text((cc, cc), "H", font=font,
                      fill=self.prefs["color_path"],
                      anchor="mm")

        return ImageTk.PhotoImage(img)

    def _update_markers(self, heading, lat, lon, home_lat, home_lon):
        '''
        Updates the position (and orientation) of the home and drone markers.
        '''
        # Home marker
        if is_valid_latlon(home_lat, home_lon):
            if self._home_marker is None:
                self._home_marker=self.map_widget.set_marker(
                    home_lat, home_lon,
                    icon=self._make_home_icon(),
                )
                # Make sure the drone is drone on top of the home marker.
                if self._drone_marker is not None:
                    self._drone_marker.delete()
                    self._drone_marker=None
            else:
                self._home_marker.set_position(home_lat,home_lon)

        h2 = round(heading/5,0)*5
        if h2 not in self._drone_cache:
            self._drone_cache[h2]=self._make_drone_icon(h2)

        if self._drone_marker is None:
            self._drone_marker=self.map_widget.set_marker(
                lat, lon,
                icon=self._drone_cache[h2],
            )
            self._drone_heading=h2
        else:
            self._drone_marker.set_position(lat,lon)
            if h2 != self._drone_heading:
                self._drone_heading=h2
                self._drone_marker.change_icon(self._drone_cache[h2])


    @staticmethod
    def _deg_to_dms(deg:float) ->str:
        m=(deg - math.floor(deg))*60
        s=(m - math.floor(m))*60
        deg=math.floor(deg)
        m=math.floor(m)
        s=round(s,1)
        return f"{deg}:{m:02d}:{s:04.1f}"

    def _update_display(self, idx: int):
        idx=max(0, min(idx, len(self.records) - 1))
        self.current_idx=idx
        r=self.records[idx]

        # Gauges - Note that we count on set_value to avoid unnneeded
        # updates.
        self._gauge_speed.set_value(r.get("3d Derived Speed (m/s)", 0)*3.6)
        #self._gauge_speed.set_value(r.get("speed (m/s)", 0)*3.6)
        self._gauge_alt.set_value(r.get("alt (m)", 0))
        self._gauge_dist.set_value(r.get("distance (m)", 0))
        heading = r.get("heading (deg)", 0)
        self._gauge_compass.set_value(heading)
        self._gauge_wind.set_value(r.get("Wind (deg)", 0))

        self._bar_battery.set_value(r.get("Battery Level (%)", 0))
        self._bar_sats.set_value(r.get("Satellites", 0))
        self._bar_wind.set_value(r.get("Wind Speed (m/s)", 0))

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

        # Update panel items. This turned out to be surprisingly
        # expensive, so we use an invariant list of items to update and we
        # count on update_field to only change fields that have changed.
        for field in self.PANEL_UPDATE_ITEMS:
            if field is None:
                continue
            self.info.update_field(field[0], r.get(field[1], "—"))

        # Handle panel items that have special formatting.
        elapsed_us=r.get("elapsed (us)", 0)
        elapsed_s =elapsed_us / 1_000_000
        m, s      =divmod(int(elapsed_s), 60)
        self.info.update_field("Elapsed",     f"{m:02d}:{s:02d}")

        lat=r.get("lat (deg)")
        lon=r.get("lon (deg)")
        if is_valid_latlon(lat, lon):
            self.info.update_field("Lat",     self._deg_to_dms(lat))
            self.info.update_field("Lon",     self._deg_to_dms(lon))

        hlat=r.get("Home Lat (deg)")
        hlon=r.get("Home Lon (deg)")
        if is_valid_latlon(hlat, hlon):
            self.info.update_field("H Lat",    self._deg_to_dms(hlat))
            self.info.update_field("H Lon",    self._deg_to_dms(hlon))
        else:
            self.info.update_field("H Lat","—")
            self.info.update_field("H Lon","—")

        # Slider
        self._slider_var.set(idx)
        self._progress_var.set(f"{idx + 1} / {len(self.records)}")

        # Map marker
        self._update_markers(heading, lat, lon, hlat, hlon)

        self.pending_update=False

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
            self.current_idx=0
        self.playing=True
        if PLATFORM_SYSTEM == "Darwin":
            self._btn_play.configure(text="⏸️", bg=self.prefs["color_warn"],
                                     fg=self.prefs["color_bg"])
        else:
            self._btn_play.configure(text="||", bg=self.prefs["color_warn"],
                                     fg=self.prefs["color_bg"])
        self._stop_event.clear()
        self.playback_thread=threading.Thread(
            target=self._playback_loop, daemon=True)
        self.playback_thread.start()

    def _pause(self):
        self.playing=False
        self._stop_event.set()
        if PLATFORM_SYSTEM == "Darwin":
            self._btn_play.configure(text="▶️", bg=self.prefs["color_accent"],
                                     fg=self.prefs["color_bg"])
        else:
            self._btn_play.configure(text=">", bg=self.prefs["color_accent"],
                                     fg=self.prefs["color_bg"])

    # Playback speed multipliers
    PLAYBACK_SPEED=[1, 2, 4, 8, 16]
    # To improve performance, we skip records when running at higher
    # playback speeds.
    PLAYBACK_INCREMENT=[1, 1, 2, 4, 8]

    def _playback_loop(self):
        """Background thread that advances frames at the selected rate."""
        while not self._stop_event.is_set():

            i_next=self.current_idx + self.PLAYBACK_INCREMENT[self.speed_idx]
            if i_next >= self.records_len:
                self.after(0, self._pause)
                break

            # Calculate sleep based on elapsed time between records
            # divided by the playback multiplier.
            r_cur =self.records[self.current_idx]
            r_next=self.records[i_next]
            dt_us =r_next.get("elapsed (us)", 0) - r_cur.get("elapsed (us)", 0)
            dt_us =dt_us / self.PLAYBACK_SPEED[self.speed_idx]
            sleep =max(0.01, dt_us / 1_000_000)

            if not self.pending_update:
                self.pending_update=True
                self.current_idx = i_next
                self.after(0, self._update_display, i_next)

            self._stop_event.wait(timeout=sleep)



    def _step_back(self):
        self._update_display(self.current_idx - 100)

    def _step_fwd(self):
        self._update_display(self.current_idx + 100)

    def _slow_down(self):
        self._set_speed(self.speed_idx-1)
        self._speed_var.set(f"{self.PLAYBACK_SPEED[self.speed_idx]}×")

    def _speed_up(self):
        self._set_speed(self.speed_idx+1)
        self._speed_var.set(f"{self.PLAYBACK_SPEED[self.speed_idx]}×")

    def _on_slider(self, val):
        idx=int(float(val))
        if idx != self.current_idx:
            self._update_display(idx)

    def _set_speed(self, idx: int):
        self.speed_idx=max(0, min(len(self.PLAYBACK_SPEED)-1, idx))

    def _set_status(self, msg: str):
        self._status_var.set(msg)

def main():
    app=DroneViewer()

    if len(sys.argv) > 1:
        path=sys.argv[1]
        if os.path.exists(path):
            app.after(200, lambda: app.load_file(path))
        else:
            my_logger.error(f"{path} does not exist.")

    app.mainloop()

if __name__ == "__main__":
    main()
