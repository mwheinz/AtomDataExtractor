#!/usr/bin/env python3
"""
Atom 2 Flight Log Converter GUI

A cross-platform GUI front-end for atom_data_extractor.py.
"""

import os
import sys
import json
import threading
import subprocess
import queue
import traceback
import csv
import io
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import mwhlogging
from atom2parser import atom2_parser, BASIC_DATA, EXTENDED_DATA, \
        VALIDATION_DATA, log_stats
from adeversion import _version

# ---------------------------------------------------------------------------
# Preferences – persisted in a small JSON file in the user's home dir.
# ---------------------------------------------------------------------------
PREFS_FILE = Path.home() / ".atom_extractor_prefs.json"

DEFAULT_GEOMETRY="800x600"

DEFAULT_PREFS = {
    "output_dir": "", # empty → same dir as input file
    "extended": False,
    "validation": False,
    "last_input_dir": str(Path.home()),
    "last_output_dir": str(Path.home()),
    "window_geometry": DEFAULT_GEOMETRY,
    "log_level": "Debug",
}

LOG_LEVEL_MAP = {
    "Error": mwhlogging.ERROR,
    "Warning": mwhlogging.WARNING,
    "Info": mwhlogging.INFO,
    "Debug": mwhlogging.DEBUG,
}

logger = mwhlogging.MWHLogger("ade")

def load_prefs() -> dict:
    try:
        if PREFS_FILE.exists():
            with open(PREFS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            prefs = DEFAULT_PREFS.copy()
            prefs.update(saved)
            return prefs
    except Exception as e:
        messagebox.showerror("Failed to load the saved preferences.", str(e))
        logger.error("Failed to load the saved preferences.\n%s",e)

    return DEFAULT_PREFS.copy()

def save_prefs(prefs: dict) -> None:
    try:
        with open(PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        messagebox.showerror("Failed to save the preferences.", str(e))
        logger.error("Failed to save the preferences.\n%s",e)

# ---------------------------------------------------------------------------
# A thread-safe queue so the worker thread can send log messages to the GUI.
# ---------------------------------------------------------------------------
log_queue: queue.Queue = queue.Queue()

def log(msg: str) -> None:
    log_queue.put(msg)

def write_csv(file_name, records, extended=False, validation=False, destination=None):
    base_name, _ = os.path.splitext(os.path.basename(file_name))
    directory = (destination if destination is not None else os.path.dirname(file_name))

    csv_name = os.path.join(directory, f"{base_name}.csv")
    logger.debug("Creating %s", csv_name)

    with open(csv_name, mode="w", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        header = BASIC_DATA + \
            (EXTENDED_DATA if extended else []) + \
            (VALIDATION_DATA if validation else [])
        writer.writerow(header)

        for record in records:
            row = [record.get(field,"") for field in header]
            writer.writerow(row)
    logger.print(f"{csv_name} complete.")

# ---------------------------------------------------------------------------
# Patched atom2_parser that redirects print() into the log queue and raises
# exceptions instead of calling sys.exit().
# ---------------------------------------------------------------------------
def safe_atom2_parser(file_name: str, extended: bool, validation: bool,
                      destination) -> None:
    '''
        Wrapper around atom2_parser() that captures print() output → log queue
    '''

    buf = io.StringIO()
    logger.configure_logging(file_handle = buf)

    records = atom2_parser(file_name=file_name, logger=logger)
    log_stats(logger, records)

    write_csv(file_name, records,
        extended=extended,
        validation=validation,
        destination=destination if destination else None)

    # Relay any captured prints to the log.
    for line in buf.getvalue().splitlines():
        if line.strip():
            log(line)

# ---------------------------------------------------------------------------
# Main Application Window
# ---------------------------------------------------------------------------
class AtomConverterApp:
    '''
        Main application window.
    '''

    # ---- construction -------------------------------------------------------

    def __init__(self, root: tk.Tk):
        self.root = root
        self.prefs = load_prefs()
        self.file_list: list[str] = []       # files queued for conversion
        self.converting = False

        self.file_listbox = None
        self.output_dir_var = None
        self.extended_var = False
        self.validation_var = False
        self.log_level_var = None
        self.progress = None
        self.status_var = None
        self.open_output_btn = None
        self.convert_btn = None
        self.log_text = None

        self._build_ui()
        self._restore_geometry()
        self._poll_log_queue()

    # ---- UI construction ----------------------------------------------------

    def _build_ui(self):
        self.root.title("Atom 2 Flight Log Converter")
        self.root.minsize(620, 500)
        self.root.resizable(True, True)

        menubar = tk.Menu(self.root)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About…", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

        # ---- styling ----
        style = ttk.Style()
        # Use a native-looking theme on each platform
        available = style.theme_names()
        for preferred in ("aqua", "vista", "clam", "alt", "default"):
            if preferred in available:
                style.theme_use(preferred)
                break

        style.configure("Drop.TFrame", relief="solid", borderwidth=2)
        style.configure("Convert.TButton", padding=6)
        style.configure("Header.TLabel", font=("TkDefaultFont", 11, "bold"))

        # ---- main layout ----
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)   # log area expands

        # ---- Section 1: file drop / file list ----
        self._build_file_section(main_frame, row=0)

        # ---- Section 2: options ----
        self._build_options_section(main_frame, row=1)

        # ---- Section 3: log ----
        self._build_log_section(main_frame, row=2)

        # ---- Section 4: action bar ----
        self._build_action_bar(main_frame, row=3)

    def _build_file_section(self, parent, row):
        frame = ttk.LabelFrame(parent, text="Input Files (.fc2)", padding=8)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        # File listbox
        list_frame = ttk.Frame(frame)
        list_frame.grid(row=1, column=0, columnspan=3, sticky="ew")
        list_frame.columnconfigure(0, weight=1)

        self.file_listbox = tk.Listbox(
            list_frame,
            height=5,
            selectmode=tk.EXTENDED,
            activestyle="dotbox",
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                   command=self.file_listbox.yview)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Buttons row
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, sticky="w", pady=(6, 0))

        ttk.Button(btn_frame, text="Add Files…",
                   command=self._browse_add_files).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Remove Selected",
                   command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Clear All",
                   command=self._clear_files).pack(side=tk.LEFT)

    def _build_options_section(self, parent, row):
        frame = ttk.LabelFrame(parent, text="Options", padding=8)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        # Output directory
        ttk.Label(frame, text="Output folder:").grid(
            row=0, column=0, sticky="w", padx=(0, 6))

        self.output_dir_var = tk.StringVar(value=self.prefs.get("output_dir", ""))
        out_entry = ttk.Entry(frame, textvariable=self.output_dir_var)
        out_entry.grid(row=0, column=1, sticky="ew", padx=(0, 4))

        ttk.Button(frame, text="Browse…",
                   command=self._browse_output_dir).grid(row=0, column=2, sticky="w")

        ttk.Label(frame, text="(Specify where the CSV files should be saved.)",
                  foreground="gray").grid(row=1, column=1, sticky="w", pady=(2, 6))

        # Checkboxes
        self.extended_var = tk.BooleanVar(value=self.prefs.get("extended", False))
        self.validation_var = tk.BooleanVar(value=self.prefs.get("validation", False))

        ttk.Checkbutton(
            frame,
            text="Include extended fields (IMU, magnetometer, component voltages…)",
            variable=self.extended_var,
        ).grid(row=2, column=0, columnspan=3, sticky="w")

        ttk.Checkbutton(
            frame,
            text="Include validation fields (derived distance & speed calculations)",
            variable=self.validation_var,
        ).grid(row=3, column=0, columnspan=3, sticky="w")

        ttk.Label(frame, text="Log: level").grid(
            row=4, column=0, sticky="w", pady=(10,0))
        log_level_frame = ttk.Frame(frame)
        log_level_frame.grid(row=4, column=1, columnspan=2, sticky="w", pady=(10, 0))

        saved_level = self.prefs.get("log_level", "Warning")
        self.log_level_var = tk.StringVar(value=saved_level)

        for label in ("Error", "Warning", "Info", "Debug"):
            ttk.Radiobutton(
                log_level_frame,
                text=label,
                variable=self.log_level_var,
                value=label,
            ).pack(side=tk.LEFT, padx=(0, 12))

    def _build_log_section(self, parent, row):
        frame = ttk.LabelFrame(parent, text="Conversion Log", padding=8)
        frame.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            frame,
            height=8,
            state=tk.DISABLED,
            wrap=tk.WORD,
            font=("TkFixedFont", 10),
            background="#1e1e1e",
            foreground="#d4d4d4",
            insertbackground="white",
            relief="flat",
        )
        log_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL,
                                    command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

        self.log_text.tag_configure("error", foreground="#f48771")
        self.log_text.tag_configure("success", foreground="#4ec9b0")
        self.log_text.tag_configure("info", foreground="#9cdcfe")

        ttk.Button(frame, text="Clear Log",
                   command=self._clear_log).grid(row=1, column=0, sticky="e",
                                                  pady=(4, 0))

    def _build_action_bar(self, parent, row):
        action_bar = ttk.Frame(parent)
        action_bar.grid(row=row, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(action_bar, mode="determinate", length=200)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(action_bar, textvariable=self.status_var, foreground="gray").grid(
            row=0, column=1, sticky="w", padx=(0, 10))

        self.open_output_btn = ttk.Button(
            action_bar, text="Open Output Folder",
            command=self._open_output_folder, state=tk.DISABLED)
        self.open_output_btn.grid(row=0, column=2, padx=(0, 8))

        self.convert_btn = ttk.Button(
            action_bar, text="Convert All", style="Convert.TButton",
            command=self._start_conversion)
        self.convert_btn.grid(row=0, column=3)

    # ---- geometry -----------------------------------------------------------

    def _restore_geometry(self):
        geom = self.prefs.get("window_geometry", "")
        if geom:
            try:
                self.root.geometry(geom)
            except Exception:
                self.root.geometry(DEFAULT_GEOMETRY)
        else:
            self.root.geometry(DEFAULT_GEOMETRY)

        self.root.update_idletasks()
        self.root.resizable(True,True)

    def _save_geometry(self):
        self.prefs["window_geometry"] = self.root.geometry()

    # ---- file management ----------------------------------------------------

    def _add_files(self, paths: list[str]):
        for p in paths:
            p = p.strip()
            # tkinterdnd2 wraps paths with spaces in braces on Windows
            p = p.strip("{}")
            if p and p not in self.file_list and p.lower().endswith(".fc2"):
                if Path(p).exists():
                    self.file_list.append(p)
                    self.file_listbox.insert(tk.END, Path(p).name)
                    # remember last used directory
                    self.prefs["last_input_dir"] = str(Path(p).parent)
                else:
                    self._log_msg(f"File not found: {p}", tag="error")
            elif p and not p.lower().endswith(".fc2"):
                self._log_msg(f"Skipped (not .fc2): {Path(p).name}", tag="error")

    def _browse_add_files(self):
        start = self.prefs.get("last_input_dir", str(Path.home()))
        files = filedialog.askopenfilenames(
            title="Select Atom 2 flight log files",
            initialdir=start,
            filetypes=[("Atom 2 flight logs", "*.fc2"), ("All files", "*.*")],
        )
        if files:
            self._add_files(list(files))

    def _remove_selected(self):
        selected = list(self.file_listbox.curselection())
        for i in reversed(selected):
            self.file_listbox.delete(i)
            del self.file_list[i]

    def _clear_files(self):
        self.file_listbox.delete(0, tk.END)
        self.file_list.clear()

    # ---- output dir ---------------------------------------------------------

    def _browse_output_dir(self):
        start = self.prefs.get("last_output_dir", str(Path.home()))
        directory = filedialog.askdirectory(
            title="Choose output folder for CSV files",
            initialdir=start,
        )
        if directory:
            self.output_dir_var.set(directory)
            self.prefs["last_output_dir"] = directory

    # ---- conversion ---------------------------------------------------------

    def _start_conversion(self):
        '''
            Load the fc2 file, parse it and save it.
        '''
        if self.converting:
            return
        if not self.file_list:
            messagebox.showwarning("No Files", "Please add at least one .fc2 file.")
            return

        # Snapshot options
        out_dir = self.output_dir_var.get().strip()
        if out_dir is None or out_dir == "":
            messagebox.showerror("Bad Output Dir",
                                  "Please select an output folder.")
            return
        if not Path(out_dir).is_dir():
            messagebox.showerror("Bad Output Dir",
                                  f"Output folder does not exist:\n{out_dir}")
            return

        extended = self.extended_var.get()
        validation = self.validation_var.get()
        log_level_str = self.log_level_var.get()
        log_level_int = LOG_LEVEL_MAP.get(log_level_str, 1)
        logger.configure_logging(level=log_level_int)

        files = list(self.file_list)

        # Persist prefs
        self.prefs["output_dir"] = out_dir
        self.prefs["extended"] = extended
        self.prefs["validation"] = validation
        self.prefs["log_level"] = log_level_str
        save_prefs(self.prefs)

        self.converting = True
        self.convert_btn.config(state=tk.DISABLED)
        self.open_output_btn.config(state=tk.DISABLED)
        self.progress["value"] = 0
        self.progress["maximum"] = len(files)
        self._set_status(f"Converting 0 / {len(files)}…")
        self._log_msg(
            f"Starting conversion of {len(files)} file(s).", tag="info")

        # Run in a background thread so the GUI stays responsive.
        thread = threading.Thread(
            target=self._conversion_worker,
            args=(files, out_dir, extended, validation),
            daemon=True,
        )
        thread.start()

    def _conversion_worker(self, files, out_dir, extended, validation):
        """Background worker — do NOT touch tkinter widgets directly."""
        success_count = 0
        fail_count = 0
        last_out_dir = out_dir

        for i, f in enumerate(files):
            try:
                safe_atom2_parser(
                    f,
                    extended=extended,
                    validation=validation,
                    destination=out_dir,
                )
                success_count += 1
            except Exception as e:
                log(f"✗  Error converting {Path(f).name}: {e}")
                log(traceback.format_exc())
                fail_count += 1

            # Signal progress back to the GUI thread via the queue.
            log_queue.put(("__progress__", i + 1, last_out_dir))

        # Signal completion.
        log_queue.put(("__done__", success_count, fail_count, last_out_dir))

    # ---- log ----------------------------------------------------------------

    def _log_msg(self, msg: str, tag: str = ""):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_status(self, msg: str):
        self.status_var.set(msg)

    # ---- poll the queue (runs on main thread via after()) -------------------

    def _poll_log_queue(self):
        try:
            while True:
                item = log_queue.get_nowait()

                if isinstance(item, tuple):
                    kind = item[0]
                    if kind == "__progress__":
                        _, done, last_dir = item
                        self.progress["value"] = done
                        total = self.progress["maximum"]
                        self._set_status(f"Converting {done} / {total}…")
                        if last_dir:
                            self._last_out_dir = last_dir

                    elif kind == "__done__":
                        _, ok, fail, last_dir = item
                        self.converting = False
                        self.convert_btn.config(state=tk.NORMAL)
                        total = ok + fail
                        msg = f"Done: {ok} succeeded, {fail} failed."
                        self._log_msg(msg,
                                      tag="success" if fail == 0 else "error")
                        self._set_status(msg)
                        if last_dir:
                            self._last_out_dir = last_dir
                            self.open_output_btn.config(state=tk.NORMAL)
                        save_prefs(self.prefs)
                else:
                    # Plain string log message
                    tag = ""
                    if "✓" in item:
                        tag = "success"
                    elif "✗" in item or "error" in item.lower():
                        tag = "error"
                    self._log_msg(item, tag=tag)

        except queue.Empty:
            pass

        self.root.after(100, self._poll_log_queue)

    # ---- open output folder -------------------------------------------------

    def _open_output_folder(self):
        out_dir = getattr(self, "_last_out_dir", None) \
                  or self.output_dir_var.get().strip() \
                  or str(Path.home())

        if not Path(out_dir).is_dir():
            messagebox.showwarning("Folder Not Found",
                                    f"Cannot open:\n{out_dir}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(out_dir)          # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", out_dir])
            else:
                subprocess.Popen(["xdg-open", out_dir])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder:\n{e}")

    # ---- shutdown -----------------------------------------------------------

    def on_close(self):
        if self.converting:
            if not messagebox.askyesno(
                "Conversion in Progress",
                "A conversion is still running. Quit anyway?"
            ):
                return
        self._save_geometry()
        save_prefs(self.prefs)
        self.root.destroy()

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Atom 2 Data Extractor\n"
            f"Version {_version}\n\n"
            "Converts Potensic Atom 2 flight logs (.fc2) to CSV.\n\n"
            "Written by Michael Heinz.\n"
            "Based on work by Michael Heinz, Koen Aerts, and Rob Pritt."
        )

def main():
    root = tk.Tk()

    app = AtomConverterApp(root)
    root.createcommand("tk::mac::Quit", app.on_close)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
