"""
Adds simple color logging, formatted the way I like it.

Supports two output modes (independently or together):
  • stderr   – ANSI-colored text, same as before.
  • tkinter  – A Text widget window that parses ANSI escape sequences and
               renders each level in the matching color.

Usage (tkinter window):
    import tkinter as tk
    from mwhlogging import MWHLogger

    root = tk.Tk()
    logger = MWHLogger("myapp")
    logger.configure_logging(tk_parent=root)   # opens the log window
    logger.info("Hello from the log window!")
    root.mainloop()

The tkinter window is completely optional; if tk_parent is never passed the
module has no tkinter dependency at all.
"""

import logging
import re
import sys
import platform
from logging.handlers import RotatingFileHandler

PLATFORM_SYSTEM = platform.system()

# ── Public level constants (convenience re-exports) ──────────────────────────
ERROR    = logging.ERROR
WARNING  = logging.WARNING
INFO     = logging.INFO
DEBUG    = logging.DEBUG

LOG_LEVEL_MAP={
    "Error": logging.ERROR,
    "Warning": logging.WARNING,
    "Info": logging.INFO,
    "Debug": logging.DEBUG,
}

# ── ANSI color definitions ────────────────────────────────────────────────────
# Map each log level to the same ANSI code used in the terminal formatter so
# both outputs stay visually consistent.
_ANSI_COLORS: dict[int, str] = {
    logging.DEBUG:    "\033[1;34m",   # Bold blue
    logging.INFO:     "\033[1;32m",   # Bold green
    logging.WARNING:  "\033[1;33m",   # Bold yellow
    logging.ERROR:    "\033[1;31m",   # Bold red
    logging.CRITICAL: "\033[1;41m",   # Bold white on red background
}
_ANSI_RESET = "\033[0m"

# Map the same levels to Tk-compatible color pairs (fg, bg).
# bg=None means use the widget's default background.
_TK_LEVEL_COLORS: dict[int, tuple[str, str | None]] = {
    logging.DEBUG:    ("#5599ff", None),      # blue
    logging.INFO:     ("#44cc44", None),      # green
    logging.WARNING:  ("#ddaa00", None),      # amber
    logging.ERROR:    ("#ff4444", None),      # red
    logging.CRITICAL: ("#ffffff", "#cc0000"), # white on red
}

# ── ANSI → Tk tag parser ──────────────────────────────────────────────────────
# We only need to parse the small subset of codes we ourselves emit, but the
# parser is written generically enough to handle arbitrary SGR sequences.

_ANSI_RE = re.compile(r'\033\[([0-9;]*)m')

# SGR code → (attribute, value) understood by Tk Text tags.
# Bold is approximated by font weight; background codes 40-47 map to colors.
_SGR_FG = {
    30: "black",   31: "#ff4444", 32: "#44cc44", 33: "#ddaa00",
    34: "#5599ff", 35: "#cc44cc", 36: "#44cccc", 37: "white",
}
_SGR_BG = {
    40: "black",   41: "#cc0000", 42: "#007700", 43: "#886600",
    44: "#0000cc", 45: "#880088", 46: "#006666", 47: "#aaaaaa",
}


def _parse_ansi(text: str) -> list[tuple[str, dict]]:
    """
    Split *text* into (chunk, tag_kwargs) pairs where tag_kwargs holds the
    Tk Text tag options (foreground, background, font weight) for that chunk.
    """
    segments: list[tuple[str, dict]] = []
    current: dict = {}
    pos = 0

    for m in _ANSI_RE.finditer(text):
        # Text before this escape sequence uses the current style.
        if m.start() > pos:
            segments.append((text[pos:m.start()], dict(current)))

        codes = m.group(1).split(";") if m.group(1) else ["0"]
        for code_str in codes:
            code = int(code_str) if code_str else 0
            if code == 0:
                current = {}                          # reset
            elif code == 1:
                current["bold"] = True
            elif code in _SGR_FG:
                current["foreground"] = _SGR_FG[code]
            elif code in _SGR_BG:
                current["background"] = _SGR_BG[code]
        pos = m.end()

    # Remaining text after the last escape sequence.
    if pos < len(text):
        segments.append((text[pos:], dict(current)))

    return segments


# ── Tkinter log window ────────────────────────────────────────────────────────

class _TkLogWindow:
    """
    A floating Toplevel (or embedded Frame) that displays log records.

    The widget is created lazily on the first log message so that it is always
    constructed on the main thread even when configure_logging() is called
    early during startup.

    All methods that touch Tk widgets must be called from the main thread.
    Use _append_threadsafe() from background threads.
    """

    # Dark terminal-style defaults
    BG        = "#1e1e1e"
    FG        = "#d4d4d4"
    FONT_FACE = "Courier New"   # monospaced; falls back gracefully
    FONT_SIZE = 11
    MAX_LINES = 2_000           # trim oldest lines when exceeded

    def __init__(self, parent, menubar, title: str = "Log"):
        import tkinter as tk  # imported here to keep the module lightweight
        self._tk   = tk
        self._root = parent
        self._win  = None
        self._text = None
        self._title = title
        self._menubar = menubar
        self._pending: list[str] = []   # messages queued before window exists

    # ── public ───────────────────────────────────────────────────────────────

    def append(self, formatted_message: str) -> None:
        """Append a formatted (ANSI-colored) log line. Call from any thread."""
        try:
            import threading
            if threading.current_thread() is threading.main_thread():
                self._ensure_window()
                self._write(formatted_message + "\n")
            else:
                self._append_threadsafe(formatted_message)
        except Exception:
            pass   # never let logging crash the app

    def show(self) -> None:
        """Open the window for the first time, un-hide it, or raise it."""
        self._ensure_window()
        if self._win:
            self._win.deiconify()
            self._win.lift()
            self._win.focus_force()
            self._center_on(self._root)

    def _append_threadsafe(self, message: str) -> None:
        """Schedule a write via after() so Tk is only touched on main thread."""
        if self._root is not None:
            self._root.after(0, lambda m=message: self._write_safe(m))

    def _write_safe(self, message: str) -> None:
        self._ensure_window()
        self._write(message + "\n")

    # ── private ──────────────────────────────────────────────────────────────

    def _center_on(self, parent):
        x=parent.winfo_x() + (parent.winfo_width()  - self._win.winfo_width())  // 2
        y=parent.winfo_y() + (parent.winfo_height() - self._win.winfo_height()) // 2
        self._win.geometry(f"+{x}+{y}")

    def _ensure_window(self) -> None:
        """Build the window the first time it is needed."""
        if self._win is not None:
            return
        tk = self._tk
        win = tk.Toplevel(self._root)
        win.title(self._title)
        win.geometry("900x400")
        if PLATFORM_SYSTEM == "Darwin":
            win.configure(bg=self.BG, menu=self._menubar)
        win.withdraw()

        # ── toolbar ──────────────────────────────────────────────────────────
        toolbar = tk.Frame(win, bg=self.BG)
        toolbar.pack(side="top", fill="x", padx=4, pady=(4, 0))

        # ── text widget + scrollbar ───────────────────────────────────────────
        frame = tk.Frame(win, bg=self.BG)
        frame.pack(fill="both", expand=True, padx=4, pady=4)

        sb = tk.Scrollbar(frame)
        sb.pack(side="right", fill="y")

        text = tk.Text(
            frame,
            bg=self.BG, fg=self.FG,
            font=(self.FONT_FACE, self.FONT_SIZE),
            yscrollcommand=sb.set,
            state="disabled",
            wrap="none",
            relief="flat",
            borderwidth=0,
        )
        text.pack(side="left", fill="both", expand=True)
        sb.config(command=text.yview)

        # Horizontal scrollbar (long lines are common in logs)
        hb = tk.Scrollbar(win, orient="horizontal", command=text.xview)
        hb.pack(side="bottom", fill="x")
        text.configure(xscrollcommand=hb.set)

        self._text = text
        self._win  = win

        # Hide instead of destroy when the user clicks the close button.
        win.protocol("WM_DELETE_WINDOW", lambda: win.withdraw())
        if PLATFORM_SYSTEM == "Darwin":
            win.bind("<Command-w>", lambda e: win.withdraw())
        else:
            win.bind("<Control-w>", lambda e: win.withdraw())

        # Register Tk Text tags for every level.
        for level, (fg, bg) in _TK_LEVEL_COLORS.items():
            tag_opts: dict = {"foreground": fg}
            if bg:
                tag_opts["background"] = bg
            text.tag_configure(f"level_{level}", **tag_opts)

        # Bold tag (used by the ANSI parser).
        text.tag_configure(
            "bold",
            font=(self.FONT_FACE, self.FONT_SIZE, "bold")
        )

    def _write(self, text: str) -> None:
        """Parse ANSI codes and insert styled text into the Text widget."""
        if self._text is None:
            return
        widget = self._text
        widget.configure(state="normal")

        segments = _parse_ansi(text)
        for chunk, style in segments:
            tags: list[str] = []

            if "foreground" in style or "background" in style:
                # Create a unique tag for this color combination on demand.
                tag_name = (
                    f"ansi_{style.get('foreground','')}"
                    f"_{style.get('background','')}"
                )
                if tag_name not in widget.tag_names():
                    opts: dict = {}
                    if "foreground" in style:
                        opts["foreground"] = style["foreground"]
                    if "background" in style:
                        opts["background"] = style["background"]
                    widget.tag_configure(tag_name, **opts)
                tags.append(tag_name)

            if style.get("bold"):
                tags.append("bold")

            widget.insert("end", chunk, tags if tags else "")

        widget.configure(state="disabled")

        # Trim old lines to cap memory use.
        line_count = int(widget.index("end-1c").split(".")[0])
        if line_count > self.MAX_LINES:
            widget.configure(state="normal")
            widget.delete("1.0", f"{line_count - self.MAX_LINES}.0")
            widget.configure(state="disabled")

        widget.see("end")

# ── Handlers ──────────────────────────────────────────────────────────────────

class _TkHandler(logging.Handler):
    """Logging handler that routes records to a _TkLogWindow."""

    def __init__(self, window: _TkLogWindow):
        super().__init__()
        self._window = window

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._window.append(msg)
        except Exception:
            self.handleError(record)


# ── Formatters ────────────────────────────────────────────────────────────────

class MWHFormatter(logging.Formatter):
    """Compact, optionally ANSI-colored log formatter."""

    def __init__(self, use_color: bool = True):
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s:%(lineno)-4d %(message)s",
            datefmt="%H:%M:%S",
        )
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        if self.use_color:
            color = _ANSI_COLORS.get(record.levelno, "")
            if color:
                levelname = record.levelname.ljust(8)
                base = base.replace(
                    levelname, f"{color}{levelname}{_ANSI_RESET}", 1
                )
        return base


# ── Main logger class ─────────────────────────────────────────────────────────

class MWHLogger(logging.Logger):
    """
    Drop-in replacement for the standard Logger with color support for both
    stderr and an optional tkinter log window.
    """

    def __init__(self, name: str = None):
        super().__init__(name=name)

        stream = sys.stderr
        self._stderr_handler = logging.StreamHandler(stream)
        self._stderr_handler.setFormatter(
            MWHFormatter(use_color=stream.isatty())
        )
        self.addHandler(self._stderr_handler)

        self._tk_handler:   _TkHandler | None       = None
        self._tk_window:    _TkLogWindow | None      = None

        self.setLevel(INFO)
        self.propagate = False

    # ── configuration ─────────────────────────────────────────────────────────

    def configure_logging(
        self,
        level:      int  = None,
        tk_parent        = None,
        tk_menubar       = None,
        tk_title:   str  = None,
    ) -> None:
        """
        Adjust log level and output destinations.

        Parameters
        ----------
        level       : New log level (DEBUG, INFO, WARNING, ERROR).
        tk_parent   : A tk.Tk or tk.Toplevel instance. Passing this opens
                      (or reuses) the tkinter log window.
        tk_menubar  : the parent instance's menu bar.
        tk_title    : Title for the tkinter log window.
        """

        if tk_title is None:
            tk_title = self.name

        if tk_parent is not None:
            self.open_tk_window(tk_parent, tk_menubar, tk_title)

        if level is not None:
            self.setLevel(level)

    def open_tk_window(self, parent, menubar, title: str) -> None:
        """Create the tkinter log window and attach its handler."""
        if self._tk_handler is not None:
            # Already open; just raise the window.
            if self._tk_window and self._tk_window._win:
                self._tk_window._win.lift()
            return

        self._tk_window = _TkLogWindow(parent, menubar, title=title)
        h = _TkHandler(self._tk_window)
        # Use ANSI formatter — the Tk handler's _parse_ansi() strips the codes
        # and converts them to Tk tags, so the Text widget gets real colors.
        h.setFormatter(MWHFormatter(use_color=True))
        h.setLevel(self.level)
        self.addHandler(h)
        self._tk_handler = h

    # ── level propagation ────────────────────────────────────────────────────

    def setLevel(self, level: int) -> None:
        self.level = level
        super().setLevel(level)
        for h in self.handlers:
            h.setLevel(level)
