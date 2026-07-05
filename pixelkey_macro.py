"""
PixelKey Macro
--------------
Macro tool with:
  - Custom key-sequence builder (hold key for N seconds/minutes, or press key,
    any number of steps, optional loop)
  - Pixel color watcher (pick a screen pixel + target color + tolerance)
  - On trigger: pauses the currently running step (remembering exact elapsed
    time), runs a separate "Trigger Sequence" (keys / held right-click / etc),
    then RESUMES the interrupted step for its remaining duration, then
    continues the main sequence normally.
  - Live console log so you can see exactly what the macro is doing.
  - Global hotkey Start/Stop

Author: JadeSCRIPTZ
"""

import datetime
import json
import os
import queue
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser

import keyboard
import pyautogui
from PIL import ImageGrab

# ----------------------------- THEME ----------------------------------
BG = "#1C1917"
BG2 = "#292524"
BG3 = "#302B28"
FG = "#E7E5E4"
FG_DIM = "#A8A29E"
ORG = "#D97706"
ORG_HOVER = "#F59E0B"
RED = "#DC2626"
GREEN = "#16A34A"
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)
FONT_TITLE = ("Segoe UI", 15, "bold")

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pixelkey_macro_config.json")

STEP_TYPES = ["Hold Key", "Press Key", "Hold Right Click", "Hold Left Click"]
TIME_UNITS = ["seconds", "minutes"]


class Step:
    def __init__(self, action="Hold Key", key="a", duration=1.0, unit="seconds"):
        self.action = action
        self.key = key
        self.duration = duration
        self.unit = unit

    def duration_seconds(self):
        return self.duration * 60 if self.unit == "minutes" else self.duration

    def to_dict(self):
        return {"action": self.action, "key": self.key,
                "duration": self.duration, "unit": self.unit}

    @staticmethod
    def from_dict(d):
        return Step(d.get("action", "Hold Key"), d.get("key", "a"),
                    d.get("duration", 1.0), d.get("unit", "seconds"))

    def label(self):
        if self.action == "Hold Key":
            return f'Hold "{self.key}"  for  {self.duration} {self.unit}'
        if self.action == "Press Key":
            return f'Press "{self.key}"  ({self.duration} {self.unit} pause after)'
        if self.action == "Hold Right Click":
            return f'Hold RIGHT CLICK for {self.duration} {self.unit}'
        if self.action == "Hold Left Click":
            return f'Hold LEFT CLICK for {self.duration} {self.unit}'
        return "?"


class RoundButton(tk.Frame):
    """tk.Frame wrapping tk.Button (Canvas causes crashes on Windows)."""
    def __init__(self, master, text, command, bg=ORG, fg="#1C1917",
                 hover=ORG_HOVER, width=None, font=FONT_B, **kw):
        super().__init__(master, bg=BG)
        self.btn = tk.Button(self, text=text, command=command, bg=bg, fg=fg,
                              activebackground=hover, activeforeground=fg,
                              relief="flat", bd=0, font=font, cursor="hand2",
                              padx=14, pady=7, **kw)
        if width:
            self.btn.config(width=width)
        self.btn.pack(fill="both", expand=True)
        self.btn.bind("<Enter>", lambda e: self.btn.config(bg=hover))
        self.btn.bind("<Leave>", lambda e: self.btn.config(bg=bg))


class PixelKeyMacro:
    def __init__(self, root):
        self.root = root
        self.root.title("PixelKey Macro")
        self.root.configure(bg=BG)
        self.root.geometry("680x780")
        self.root.minsize(620, 680)

        self.steps = []            # main sequence
        self.trigger_steps = []    # runs when pixel color detected
        self.loop_sequence = tk.BooleanVar(value=False)

        self.running = False
        self.stop_flag = threading.Event()
        self.trigger_event = threading.Event()
        self.trigger_mode = tk.StringVar(value="resume")  # "resume" or "stop"
        self.cooldown = tk.DoubleVar(value=1.5)
        self._last_trigger_time = 0
        self._last_trigger_label = ""

        self.log_queue = queue.Queue()

        # pixel watch state - "staging" fields for adding a new watch point
        self.watch_points = []     # list of dicts: {x,y,color:(r,g,b),tolerance}
        self.watch_x = tk.IntVar(value=0)
        self.watch_y = tk.IntVar(value=0)
        self.target_color = (255, 0, 0)
        self.tolerance = tk.IntVar(value=20)
        self.watch_enabled = tk.BooleanVar(value=False)
        self.poll_interval = tk.DoubleVar(value=0.1)

        self.start_hotkey = tk.StringVar(value="f6")
        self.stop_hotkey = tk.StringVar(value="f7")
        self.panic_hotkey = tk.StringVar(value="esc")

        self.idle_hold_enabled = tk.BooleanVar(value=False)
        self.idle_hold_key = tk.StringVar(value="f")

        self.jitter_enabled = tk.BooleanVar(value=False)
        self.jitter_percent = tk.DoubleVar(value=15.0)
        self.dry_run = tk.BooleanVar(value=False)

        self.profile_name = tk.StringVar(value="Default")
        self.PROFILES_DIR = os.path.join(os.path.expanduser("~"), ".pixelkey_macro_profiles")
        os.makedirs(self.PROFILES_DIR, exist_ok=True)

        self._build_ui()
        self._load_config()
        self._register_hotkeys()
        self._pump_log()
        self.log("App started. Add steps in 'Sequence' tab, then press Start.")

    # ------------------------------------------------ LOGGING
    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {msg}")

    def _pump_log(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.console.config(state="normal")
                self.console.insert(tk.END, line + "\n")
                self.console.see(tk.END)
                self.console.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._pump_log)

    # ------------------------------------------------ UI BUILD
    def _build_ui(self):
        # ---------- Header ----------
        header = tk.Frame(self.root, bg=BG2, height=68)
        header.pack(fill="x")
        header.pack_propagate(False)

        logo = tk.Label(header, text="⚡", bg=ORG, fg="#1C1917", font=("Segoe UI", 18, "bold"),
                         width=2, height=1)
        logo.pack(side="left", padx=(18, 12), pady=14)

        title_box = tk.Frame(header, bg=BG2)
        title_box.pack(side="left", pady=10)
        tk.Label(title_box, text="PixelKey Macro", bg=BG2, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(title_box, text="by JadeSCRIPTZ", bg=BG2, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")

        status_pill = tk.Frame(header, bg=BG3)
        status_pill.pack(side="right", padx=18, pady=18)
        self.status_dot = tk.Label(status_pill, text="●", bg=BG3, fg=FG_DIM, font=("Segoe UI", 11))
        self.status_dot.pack(side="left", padx=(12, 2), pady=6)
        self.status_lbl = tk.Label(status_pill, text="STOPPED", bg=BG3, fg=FG_DIM, font=FONT_B)
        self.status_lbl.pack(side="left", padx=(0, 12), pady=6)

        tk.Frame(self.root, bg=ORG, height=2).pack(fill="x")

        # ---------- Body: sidebar + content ----------
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, bg=BG2, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="NAVIGATION", bg=BG2, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(22, 10))

        content = tk.Frame(body, bg=BG)
        content.pack(side="left", fill="both", expand=True, padx=18, pady=16)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        seq_page = tk.Frame(content, bg=BG)
        trig_page = tk.Frame(content, bg=BG)
        pixel_page = tk.Frame(content, bg=BG)
        settings_page = tk.Frame(content, bg=BG)
        for p in (seq_page, trig_page, pixel_page, settings_page):
            p.grid(row=0, column=0, sticky="nsew")

        self._build_step_editor(seq_page, is_trigger=False)
        self._build_step_editor(trig_page, is_trigger=True)
        self._build_pixel_tab(pixel_page)
        self._build_settings_tab(settings_page)

        self.pages = {"seq": seq_page, "trig": trig_page, "pixel": pixel_page, "settings": settings_page}
        self.nav_buttons = {}
        nav_items = [("seq", "📋", "Sequence"), ("trig", "⚡", "Trigger"),
                     ("pixel", "🎯", "Pixel Trigger"), ("settings", "⚙", "Settings")]
        for key, icon, label in nav_items:
            btn = tk.Button(sidebar, text=f"   {icon}   {label}", command=lambda k=key: self._show_page(k),
                             bg=BG2, fg=FG, activebackground=BG3, activeforeground=ORG,
                             relief="flat", bd=0, anchor="w", font=FONT, cursor="hand2",
                             padx=4, pady=12)
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn

        sidebar_footer = tk.Frame(sidebar, bg=BG2)
        sidebar_footer.pack(side="bottom", fill="x", pady=16, padx=16)
        tk.Frame(sidebar_footer, bg=BG3, height=1).pack(fill="x", pady=(0, 10))
        tk.Label(sidebar_footer, text="v2.0.0", bg=BG2, fg=FG_DIM, font=("Segoe UI", 8)).pack(anchor="w")

        self._show_page("seq")

        # ---------- Console (card style, collapsible) ----------
        console_outer = tk.Frame(self.root, bg=BG)
        console_outer.pack(fill="x", padx=18, pady=(0, 4))
        console_head = tk.Frame(console_outer, bg=BG)
        console_head.pack(fill="x")
        tk.Label(console_head, text="◆ CONSOLE", bg=BG, fg=FG_DIM, font=("Segoe UI", 8, "bold")).pack(side="left")
        RoundButton(console_head, "Clear", self._clear_console, bg=BG2, fg=FG_DIM,
                    hover=BG3, width=6, font=("Segoe UI", 8)).pack(side="right")

        console_card = tk.Frame(console_outer, bg=BG3)
        console_card.pack(fill="both", pady=(6, 0))
        console_inner = tk.Frame(console_card, bg=BG2)
        console_inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.console = tk.Text(console_inner, height=7, bg=BG2, fg="#8CE99A",
                                font=FONT_MONO, bd=0, highlightthickness=0,
                                state="disabled", wrap="word", padx=10, pady=8)
        self.console.pack(fill="both", expand=True)

        # ---------- Bottom Start/Stop bar ----------
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=18, pady=(10, 18))
        self.start_btn = RoundButton(bottom, "▶  START  (F6)", self.start_macro, bg=GREEN, fg="white",
                                      hover="#22C55E", font=("Segoe UI", 11, "bold"))
        self.start_btn.pack(side="left", padx=(0, 10), fill="x", expand=True, ipady=4)
        self.stop_btn = RoundButton(bottom, "■  STOP  (F7)", self.stop_macro, bg=RED, fg="white",
                                     hover="#EF4444", font=("Segoe UI", 11, "bold"))
        self.stop_btn.pack(side="left", fill="x", expand=True, ipady=4)

    def _set_status(self, text, color):
        self.status_lbl.config(text=text, fg=color)
        self.status_dot.config(fg=color)

    def _show_page(self, key):
        for k, page in self.pages.items():
            btn = self.nav_buttons[k]
            if k == key:
                btn.config(bg=BG3, fg=ORG)
                page.tkraise()
            else:
                btn.config(bg=BG2, fg=FG)

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.config(state="disabled")

    def _section_label(self, parent, text, pad=(14, 6)):
        row = tk.Frame(parent, bg=BG)
        row.pack(anchor="w", pady=pad, fill="x")
        tk.Frame(row, bg=ORG, width=3, height=14).pack(side="left", padx=(0, 8))
        tk.Label(row, text=text, bg=BG, fg=FG_DIM, font=("Segoe UI", 9, "bold")).pack(side="left")

    # ---- generic step editor (used for both Sequence and Trigger Sequence)
    def _build_step_editor(self, parent, is_trigger):
        target_list = self.trigger_steps if is_trigger else self.steps
        title = "REACTION STEPS (what to do when pixel color is detected)" if is_trigger \
            else "MAIN STEPS (executed in order, top to bottom)"
        self._section_label(parent, title)

        list_frame_outer = tk.Frame(parent, bg=BG3)
        list_frame_outer.pack(fill="both", expand=True, pady=(0, 8))
        list_frame = tk.Frame(list_frame_outer, bg=BG2)
        list_frame.pack(fill="both", expand=True, padx=1, pady=1)
        listbox = tk.Listbox(list_frame, bg=BG2, fg=FG, font=FONT,
                              selectbackground=ORG, selectforeground="#1C1917",
                              bd=0, highlightthickness=0, activestyle="none")
        listbox.pack(fill="both", expand=True, padx=10, pady=10)

        form = tk.Frame(parent, bg=BG)
        form.pack(fill="x", pady=6)

        tk.Label(form, text="Action:", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, sticky="w", padx=4)
        action_var = tk.StringVar(value=STEP_TYPES[0])
        ttk.Combobox(form, textvariable=action_var, values=STEP_TYPES,
                     state="readonly", width=14).grid(row=0, column=1, padx=4)

        tk.Label(form, text="Key:", bg=BG, fg=FG, font=FONT).grid(row=0, column=2, sticky="w", padx=4)
        key_var = tk.StringVar(value="a")
        tk.Entry(form, textvariable=key_var, width=8, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=3, padx=4)

        tk.Label(form, text="Duration:", bg=BG, fg=FG, font=FONT).grid(row=0, column=4, sticky="w", padx=4)
        duration_var = tk.DoubleVar(value=1.0)
        tk.Entry(form, textvariable=duration_var, width=6, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=5, padx=4)

        unit_var = tk.StringVar(value="seconds")
        ttk.Combobox(form, textvariable=unit_var, values=TIME_UNITS,
                     state="readonly", width=8).grid(row=0, column=6, padx=4)

        def refresh():
            listbox.delete(0, tk.END)
            for i, s in enumerate(target_list, 1):
                listbox.insert(tk.END, f"{i}. {s.label()}")

        def add_step():
            try:
                dur = float(duration_var.get())
            except (tk.TclError, ValueError):
                messagebox.showerror("Invalid duration", "Duration must be a number.")
                return
            if dur <= 0:
                messagebox.showerror("Invalid duration", "Duration must be greater than 0.")
                return
            act = action_var.get()
            key = key_var.get().strip()
            if act in ("Hold Key", "Press Key") and not key:
                messagebox.showerror("Invalid key", "Please enter a key.")
                return
            target_list.append(Step(act, key, dur, unit_var.get()))
            refresh()
            self.log(f"{'Trigger' if is_trigger else 'Main'} step added: {target_list[-1].label()}")

        def remove_step():
            sel = listbox.curselection()
            if not sel:
                return
            del target_list[sel[0]]
            refresh()

        def move(delta):
            sel = listbox.curselection()
            if not sel:
                return
            i = sel[0]
            j = i + delta
            if 0 <= j < len(target_list):
                target_list[i], target_list[j] = target_list[j], target_list[i]
                refresh()
                listbox.selection_set(j)

        def clear_all():
            if messagebox.askyesno("Clear All", "Remove all steps?"):
                target_list.clear()
                refresh()

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=6)
        RoundButton(btn_row, "+ Add Step", add_step, width=12).pack(side="left", padx=(0, 6))
        RoundButton(btn_row, "Remove Selected", remove_step, bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)
        RoundButton(btn_row, "↑", lambda: move(-1), bg=BG3, fg=FG, hover="#3f3a36", width=3).pack(side="left", padx=6)
        RoundButton(btn_row, "↓", lambda: move(1), bg=BG3, fg=FG, hover="#3f3a36", width=3).pack(side="left", padx=6)
        RoundButton(btn_row, "Clear All", clear_all, bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)

        if not is_trigger:
            loop_row = tk.Frame(parent, bg=BG)
            loop_row.pack(fill="x", pady=(8, 0))
            tk.Checkbutton(loop_row, text="Loop main sequence continuously until Stop",
                           variable=self.loop_sequence, bg=BG, fg=FG,
                           selectcolor=BG2, activebackground=BG, activeforeground=FG,
                           font=FONT).pack(anchor="w")

            self._section_label(parent, "IDLE HOLD MODE (simpler alternative to a Main Sequence)")
            tk.Label(parent, text="If enabled, this REPLACES the Main Sequence above: the app\n"
                                  "just holds one key continuously. When the pixel color is\n"
                                  "detected it pauses, runs the Trigger Sequence, then keeps\n"
                                  "holding the key again.",
                     bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(0, 6))
            idle_row = tk.Frame(parent, bg=BG)
            idle_row.pack(fill="x")
            tk.Checkbutton(idle_row, text="Always hold key:", variable=self.idle_hold_enabled,
                           bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                           activeforeground=FG, font=FONT_B).pack(side="left")
            tk.Entry(idle_row, textvariable=self.idle_hold_key, width=6, bg=BG3, fg=FG,
                     insertbackground=FG, relief="flat").pack(side="left", padx=8)
        else:
            tk.Label(parent, text="These steps run ONCE every time the pixel color is detected,\n"
                                  "then the main sequence resumes exactly where it paused.",
                     bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(8, 0))

        if is_trigger:
            self._refresh_trigger_list = refresh
            self.trigger_listbox = listbox
        else:
            self._refresh_main_list = refresh
            self.steps_listbox = listbox

    def _build_pixel_tab(self, parent):
        self._section_label(parent, "PIXEL COLOR TRIGGER(S)")
        tk.Label(parent, text="You can watch MULTIPLE pixels at once. If ANY of them matches\n"
                              "its target color, the current step pauses and the Trigger\n"
                              "Sequence runs, then resumes exactly where it paused.",
                 bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(0, 10))

        tk.Checkbutton(parent, text="Enable pixel-color trigger(s)", variable=self.watch_enabled,
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, font=FONT_B).pack(anchor="w", pady=(0, 8))

        list_frame_outer = tk.Frame(parent, bg=BG3)
        list_frame_outer.pack(fill="x", pady=(0, 8))
        list_frame = tk.Frame(list_frame_outer, bg=BG2)
        list_frame.pack(fill="x", padx=1, pady=1)
        self.watchpoints_listbox = tk.Listbox(list_frame, bg=BG2, fg=FG, font=FONT,
                                               selectbackground=ORG, selectforeground="#1C1917",
                                               bd=0, highlightthickness=0, activestyle="none", height=5)
        self.watchpoints_listbox.pack(fill="x", padx=10, pady=10)

        self._section_label(parent, "ADD NEW WATCH POINT")
        coord_frame = tk.Frame(parent, bg=BG)
        coord_frame.pack(fill="x", pady=4)
        tk.Label(coord_frame, text="X:", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, padx=4)
        tk.Entry(coord_frame, textvariable=self.watch_x, width=8, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=1, padx=4)
        tk.Label(coord_frame, text="Y:", bg=BG, fg=FG, font=FONT).grid(row=0, column=2, padx=4)
        tk.Entry(coord_frame, textvariable=self.watch_y, width=8, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=3, padx=4)
        RoundButton(coord_frame, "🎯 Pick Pixel (3s delay)", self.pick_pixel,
                    bg=BG3, fg=FG, hover="#3f3a36").grid(row=0, column=4, padx=10)

        color_frame = tk.Frame(parent, bg=BG)
        color_frame.pack(fill="x", pady=10)
        self.color_swatch = tk.Label(color_frame, text="", bg=self._hex(self.target_color), width=6)
        self.color_swatch.pack(side="left", padx=(0, 10))
        RoundButton(color_frame, "Choose Target Color", self.choose_color,
                    bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)
        RoundButton(color_frame, "Grab Color From Pixel Above", self.grab_color,
                    bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)

        tol_frame = tk.Frame(parent, bg=BG)
        tol_frame.pack(fill="x", pady=6)
        tk.Label(tol_frame, text="Tolerance:", bg=BG, fg=FG, font=FONT).pack(side="left", padx=(0, 8))
        tk.Scale(tol_frame, from_=0, to=100, orient="horizontal", variable=self.tolerance,
                 bg=BG, fg=FG, troughcolor=BG3, highlightthickness=0, length=220).pack(side="left")

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=6)
        RoundButton(btn_row, "+ Add Watch Point", self.add_watch_point, width=16).pack(side="left", padx=(0, 6))
        RoundButton(btn_row, "Remove Selected", self.remove_watch_point, bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)

        self._section_label(parent, "WHAT HAPPENS ON TRIGGER")
        tk.Radiobutton(parent, text="Run Trigger Sequence, then RESUME main sequence where it paused",
                       variable=self.trigger_mode, value="resume", bg=BG, fg=FG,
                       selectcolor=BG2, activebackground=BG, activeforeground=FG, font=FONT).pack(anchor="w")
        tk.Radiobutton(parent, text="Run Trigger Sequence once, then STOP everything",
                       variable=self.trigger_mode, value="stop", bg=BG, fg=FG,
                       selectcolor=BG2, activebackground=BG, activeforeground=FG, font=FONT).pack(anchor="w")

        cd_frame = tk.Frame(parent, bg=BG)
        cd_frame.pack(fill="x", pady=10)
        tk.Label(cd_frame, text="Cooldown after trigger (s):", bg=BG, fg=FG, font=FONT).pack(side="left", padx=(0, 8))
        tk.Entry(cd_frame, textvariable=self.cooldown, width=6, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").pack(side="left")

        self.live_color_lbl = tk.Label(parent, text="Live pixel color: -", bg=BG, fg=FG_DIM, font=FONT)
        self.live_color_lbl.pack(anchor="w", pady=(14, 0))
        self._update_live_color()

    def _build_settings_tab(self, parent):
        self._section_label(parent, "HOTKEYS")
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=4)
        tk.Label(row, text="Start hotkey:", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Entry(row, textvariable=self.start_hotkey, width=10, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=1, padx=4)
        tk.Label(row, text="Stop hotkey:", bg=BG, fg=FG, font=FONT).grid(row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Entry(row, textvariable=self.stop_hotkey, width=10, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=1, column=1, padx=4)
        tk.Label(row, text="Panic hotkey (always stops):", bg=BG, fg=FG, font=FONT).grid(row=2, column=0, sticky="w", padx=4, pady=4)
        tk.Entry(row, textvariable=self.panic_hotkey, width=10, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=2, column=1, padx=4)
        RoundButton(parent, "Apply Hotkeys", self._register_hotkeys, width=14).pack(anchor="w", pady=10)

        self._section_label(parent, "PIXEL POLL INTERVAL (seconds)")
        tk.Scale(parent, from_=0.02, to=1.0, resolution=0.02, orient="horizontal",
                 variable=self.poll_interval, bg=BG, fg=FG, troughcolor=BG3,
                 highlightthickness=0, length=250).pack(anchor="w")

        self._section_label(parent, "TIMING RANDOMIZATION (anti-detection)")
        tk.Checkbutton(parent, text="Randomize durations slightly so it looks less robotic",
                       variable=self.jitter_enabled, bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG, font=FONT).pack(anchor="w")
        jrow = tk.Frame(parent, bg=BG)
        jrow.pack(fill="x", pady=4)
        tk.Label(jrow, text="Variation ±%:", bg=BG, fg=FG, font=FONT).pack(side="left", padx=(0, 8))
        tk.Scale(jrow, from_=0, to=50, orient="horizontal", variable=self.jitter_percent,
                 bg=BG, fg=FG, troughcolor=BG3, highlightthickness=0, length=200).pack(side="left")

        self._section_label(parent, "TEST MODE")
        tk.Checkbutton(parent, text="Dry Run — log actions in console WITHOUT actually pressing anything",
                       variable=self.dry_run, bg=BG, fg=FG, selectcolor=BG2,
                       activebackground=BG, activeforeground=FG, font=FONT).pack(anchor="w")

        self._section_label(parent, "PROFILES")
        tk.Label(parent, text="Save your whole setup (sequences, pixel points, hotkeys) as a\n"
                              "named profile, then switch between profiles instantly.",
                 bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(0, 6))
        prow = tk.Frame(parent, bg=BG)
        prow.pack(fill="x", pady=4)
        self.profile_combo = ttk.Combobox(prow, textvariable=self.profile_name, width=18,
                                           values=self._list_profiles())
        self.profile_combo.grid(row=0, column=0, padx=(0, 8))
        RoundButton(prow, "Save As", self._save_profile, bg=BG3, fg=FG, hover="#3f3a36", width=8).grid(row=0, column=1, padx=4)
        RoundButton(prow, "Load", self._load_profile, bg=BG3, fg=FG, hover="#3f3a36", width=8).grid(row=0, column=2, padx=4)
        RoundButton(prow, "Delete", self._delete_profile, bg=BG3, fg=FG, hover="#3f3a36", width=8).grid(row=0, column=3, padx=4)

        self._section_label(parent, "CONFIG")
        RoundButton(parent, "Save Config", self._save_config, width=14).pack(anchor="w", pady=4)
        tk.Label(parent, text="Config is saved automatically on close, and loaded on startup.",
                 bg=BG, fg=FG_DIM, font=FONT).pack(anchor="w", pady=(12, 0))

        self._section_label(parent, "TROUBLESHOOTING")
        tk.Label(parent,
                 text="If Start does nothing: run the app / .exe AS ADMINISTRATOR.\n"
                      "Windows blocks simulated key presses from non-admin apps\n"
                      "into games running as admin. Check the Console box below\n"
                      "for error messages any time something doesn't work.",
                 bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(4, 0))

    # ------------------------------------------------ helpers
    def _hex(self, rgb):
        return '#%02x%02x%02x' % tuple(int(c) for c in rgb)

    def _update_live_color(self):
        try:
            x, y = self.watch_x.get(), self.watch_y.get()
            px = ImageGrab.grab().getpixel((x, y))
            rgb = px[:3] if isinstance(px, tuple) else (px, px, px)
            self.live_color_lbl.config(text=f"Live pixel color: RGB{rgb}", fg=self._hex(rgb))
        except Exception:
            pass
        self.root.after(500, self._update_live_color)

    def pick_pixel(self):
        messagebox.showinfo("Pick Pixel", "You have 3 seconds after closing this dialog\n"
                                          "to hover the mouse over the target pixel.")
        self.root.after(3000, self._capture_mouse_pos)

    def _capture_mouse_pos(self):
        x, y = pyautogui.position()
        self.watch_x.set(x)
        self.watch_y.set(y)
        self.log(f"Pixel position captured: ({x}, {y})")

    def choose_color(self):
        rgb, _ = colorchooser.askcolor(color=self._hex(self.target_color))
        if rgb:
            self.target_color = tuple(int(c) for c in rgb)
            self.color_swatch.config(bg=self._hex(self.target_color))

    def grab_color(self):
        try:
            x, y = self.watch_x.get(), self.watch_y.get()
            px = ImageGrab.grab().getpixel((x, y))
            self.target_color = px[:3] if isinstance(px, tuple) else (px, px, px)
            self.color_swatch.config(bg=self._hex(self.target_color))
            self.log(f"Target color grabbed: RGB{self.target_color}")
        except Exception as e:
            self.log(f"ERROR grabbing color: {e}")
            messagebox.showerror("Error", str(e))

    def add_watch_point(self):
        wp = {"x": self.watch_x.get(), "y": self.watch_y.get(),
              "color": tuple(self.target_color), "tolerance": self.tolerance.get()}
        self.watch_points.append(wp)
        self._refresh_watchpoints_list()
        self.log(f"Watch point added: ({wp['x']},{wp['y']}) target RGB{wp['color']} tol={wp['tolerance']}")

    def remove_watch_point(self):
        sel = self.watchpoints_listbox.curselection()
        if not sel:
            return
        del self.watch_points[sel[0]]
        self._refresh_watchpoints_list()

    def _refresh_watchpoints_list(self):
        self.watchpoints_listbox.delete(0, tk.END)
        for i, wp in enumerate(self.watch_points, 1):
            self.watchpoints_listbox.insert(
                tk.END, f"{i}. ({wp['x']},{wp['y']})  RGB{tuple(wp['color'])}  tol={wp['tolerance']}")

    # ------------------------------------------------ profiles
    def _list_profiles(self):
        try:
            return sorted(f[:-5] for f in os.listdir(self.PROFILES_DIR) if f.endswith(".json"))
        except Exception:
            return []

    def _profile_path(self, name):
        safe = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip() or "Default"
        return os.path.join(self.PROFILES_DIR, safe + ".json")

    def _save_profile(self):
        name = self.profile_name.get().strip() or "Default"
        try:
            with open(self._profile_path(name), "w") as f:
                json.dump(self._collect_config(), f, indent=2)
            self.profile_combo["values"] = self._list_profiles()
            self.log(f"Profile '{name}' saved.")
        except Exception as e:
            self.log(f"ERROR saving profile: {e}")
            messagebox.showerror("Save Profile Error", str(e))

    def _load_profile(self):
        name = self.profile_name.get().strip()
        path = self._profile_path(name)
        if not os.path.exists(path):
            messagebox.showwarning("Not Found", f"No profile named '{name}'.")
            return
        try:
            with open(path) as f:
                data = json.load(f)
            self._apply_config(data)
            self.log(f"Profile '{name}' loaded.")
        except Exception as e:
            self.log(f"ERROR loading profile: {e}")
            messagebox.showerror("Load Profile Error", str(e))

    def _delete_profile(self):
        name = self.profile_name.get().strip()
        path = self._profile_path(name)
        if os.path.exists(path) and messagebox.askyesno("Delete Profile", f"Delete profile '{name}'?"):
            os.remove(path)
            self.profile_combo["values"] = self._list_profiles()
            self.log(f"Profile '{name}' deleted.")

    # ------------------------------------------------ macro engine
    def _register_hotkeys(self):
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(self.start_hotkey.get(), self.start_macro)
            keyboard.add_hotkey(self.stop_hotkey.get(), self.stop_macro)
            keyboard.add_hotkey(self.panic_hotkey.get(), self._panic)
            self.log(f"Hotkeys set: Start={self.start_hotkey.get()}  Stop={self.stop_hotkey.get()}  "
                     f"Panic={self.panic_hotkey.get()}")
        except Exception as e:
            self.log(f"ERROR setting hotkeys: {e}")
            messagebox.showerror("Hotkey Error", str(e))

    def _panic(self):
        self.log("!!! PANIC KEY PRESSED - stopping everything immediately !!!")
        self.stop_macro()

    def start_macro(self):
        if self.running:
            self.log("Already running.")
            return
        use_idle = self.idle_hold_enabled.get()
        if not use_idle and not self.steps:
            self.log("Cannot start: no steps in Main Sequence and Idle Hold is off.")
            messagebox.showwarning("No Steps", "Add at least one step to the Sequence tab, "
                                               "or enable Idle Hold Mode, first.")
            return
        self.stop_flag.clear()
        self.trigger_event.clear()
        self.running = True
        self._set_status("RUNNING", GREEN)
        self.log("=== MACRO STARTED ===")

        if use_idle:
            threading.Thread(target=self._safe_run, args=(self._idle_hold_loop,), daemon=True).start()
        else:
            threading.Thread(target=self._safe_run, args=(self._run_sequence,), daemon=True).start()

        if self.watch_enabled.get():
            self.log(f"Pixel watcher active at ({self.watch_x.get()}, {self.watch_y.get()}) "
                     f"target RGB{self.target_color} tol={self.tolerance.get()}")
            threading.Thread(target=self._safe_run, args=(self._watch_loop,), daemon=True).start()

    def _safe_run(self, fn):
        try:
            fn()
        except Exception:
            self.log("ERROR:\n" + traceback.format_exc())
            self.running = False
            self.root.after(0, lambda: self._set_status("ERROR", RED))

    def stop_macro(self):
        if not self.running and self.status_lbl.cget("text") == "● STOPPED":
            return
        self.stop_flag.set()
        self.running = False
        self._set_status("STOPPED", FG_DIM)
        self.log("=== MACRO STOPPED ===")
        for s in self.steps + self.trigger_steps:
            try:
                if s.action == "Hold Key":
                    keyboard.release(s.key)
                elif s.action == "Hold Right Click":
                    pyautogui.mouseUp(button="right")
                elif s.action == "Hold Left Click":
                    pyautogui.mouseUp(button="left")
            except Exception:
                pass

    def _colors_match(self, c1, c2, tol):
        return all(abs(int(a) - int(b)) <= tol for a, b in zip(c1, c2))

    def _jittered(self, seconds):
        if not self.jitter_enabled.get() or seconds <= 0:
            return seconds
        import random
        pct = self.jitter_percent.get() / 100.0
        factor = 1.0 + random.uniform(-pct, pct)
        return max(0.05, seconds * factor)

    def _watch_loop(self):
        while not self.stop_flag.is_set():
            if self.watch_enabled.get() and not self.trigger_event.is_set():
                now = time.time()
                if now - self._last_trigger_time >= self.cooldown.get():
                    points = self.watch_points if self.watch_points else (
                        [{"x": self.watch_x.get(), "y": self.watch_y.get(),
                          "color": self.target_color, "tolerance": self.tolerance.get()}]
                        if self.target_color else [])
                    try:
                        img = ImageGrab.grab()
                        for wp in points:
                            px = img.getpixel((wp["x"], wp["y"]))[:3]
                            if self._colors_match(px, wp["color"], wp["tolerance"]):
                                self.log(f"Pixel MATCHED at ({wp['x']},{wp['y']}) -> RGB{px}. "
                                         f"Triggering reaction sequence.")
                                self._last_trigger_label = f"({wp['x']},{wp['y']})"
                                self.trigger_event.set()
                                break
                    except Exception as e:
                        self.log(f"Pixel read error: {e}")
            time.sleep(self.poll_interval.get())

    def _run_sequence(self):
        first = True
        while not self.stop_flag.is_set() and (first or self.loop_sequence.get()):
            first = False
            for step in self.steps:
                if self.stop_flag.is_set():
                    return
                self._execute_step_interruptible(step)
        self.running = False
        if not self.stop_flag.is_set():
            self.root.after(0, lambda: self._set_status("STOPPED", FG_DIM))
            self.log("Main sequence finished (no loop).")

    def _execute_step_interruptible(self, step):
        """Runs a single main-sequence step, remembering exact elapsed time so a
        pixel-trigger interrupt can resume it precisely where it paused."""
        total = self._jittered(step.duration_seconds())
        elapsed = 0.0
        tick = 0.05
        is_hold = step.action in ("Hold Key", "Hold Right Click", "Hold Left Click")
        last_reassert = 0.0

        self.log(f"Running: {step.label()}")
        self._press_start(step)

        while elapsed < total:
            if self.stop_flag.is_set():
                self._press_end(step)
                return

            if self.watch_enabled.get() and self.trigger_event.is_set():
                remaining = total - elapsed
                self.log(f"Interrupting '{step.label()}' at {elapsed:.1f}s/{total:.1f}s "
                         f"({remaining:.1f}s remaining) -> running Trigger Sequence")
                self._press_end(step)
                self.trigger_event.clear()
                self._last_trigger_time = time.time()

                self._run_trigger_sequence()

                if self.trigger_mode.get() == "stop":
                    self.log("Trigger mode = STOP. Halting macro.")
                    self.root.after(0, self.stop_macro)
                    return

                self.log(f"Resuming '{step.label()}' for remaining {remaining:.1f}s")
                self._press_start(step)
                total = elapsed + remaining

            # Some games/anti-cheat drop a simulated key/button that was only
            # pressed once and then held via OS state. Re-assert it periodically
            # so long holds (30s, 60s, etc.) don't silently get released early.
            if is_hold and (time.time() - last_reassert) >= 0.2:
                self._press_start(step)
                last_reassert = time.time()

            step_sleep = min(tick, total - elapsed)
            time.sleep(max(0, step_sleep))
            elapsed += step_sleep

        self._press_end(step)

    def _idle_hold_loop(self):
        """Simpler alternative to the Main Sequence: just holds one key
        continuously, pausing/resuming around pixel-trigger reactions."""
        key = self.idle_hold_key.get().strip()
        if not key:
            self.log("Idle Hold key is empty, aborting.")
            self.running = False
            return
        self.log(f"Idle Hold started: continuously holding '{key}'")
        if not self.dry_run.get():
            keyboard.press(key)
        last_reassert = time.time()

        while not self.stop_flag.is_set():
            if self.watch_enabled.get() and self.trigger_event.is_set():
                self.log(f"Idle Hold on '{key}' interrupted -> running Trigger Sequence")
                if not self.dry_run.get():
                    keyboard.release(key)
                self.trigger_event.clear()
                self._last_trigger_time = time.time()

                self._run_trigger_sequence()

                if self.trigger_mode.get() == "stop":
                    self.log("Trigger mode = STOP. Halting macro.")
                    self.root.after(0, self.stop_macro)
                    return

                self.log(f"Resuming Idle Hold on '{key}'")
                if not self.dry_run.get():
                    keyboard.press(key)
                last_reassert = time.time()

            if not self.dry_run.get() and time.time() - last_reassert >= 0.2:
                keyboard.press(key)
                last_reassert = time.time()

            time.sleep(0.05)

        try:
            if not self.dry_run.get():
                keyboard.release(key)
        except Exception:
            pass
        self.running = False

    def _press_start(self, step):
        if self.dry_run.get():
            self.log(f"[DRY RUN] would start: {step.label()}")
            return
        try:
            if step.action == "Hold Key":
                keyboard.press(step.key)
            elif step.action == "Press Key":
                keyboard.press_and_release(step.key)
            elif step.action == "Hold Right Click":
                pyautogui.mouseDown(button="right")
            elif step.action == "Hold Left Click":
                pyautogui.mouseDown(button="left")
        except Exception as e:
            self.log(f"ERROR executing step '{step.label()}': {e}")

    def _press_end(self, step):
        if self.dry_run.get():
            return
        try:
            if step.action == "Hold Key":
                keyboard.release(step.key)
            elif step.action == "Hold Right Click":
                pyautogui.mouseUp(button="right")
            elif step.action == "Hold Left Click":
                pyautogui.mouseUp(button="left")
        except Exception as e:
            self.log(f"ERROR releasing step '{step.label()}': {e}")

    def _run_trigger_sequence(self):
        if not self.trigger_steps:
            self.log("Trigger fired but Trigger Sequence is empty - nothing to do.")
            return
        for step in self.trigger_steps:
            if self.stop_flag.is_set():
                return
            self.log(f"  [reaction] {step.label()}")
            self._press_start(step)
            dur = self._jittered(step.duration_seconds())
            end = time.time() + dur
            while time.time() < end:
                if self.stop_flag.is_set():
                    self._press_end(step)
                    return
                time.sleep(min(0.05, max(0, end - time.time())))
            self._press_end(step)
        self.log("Trigger Sequence complete.")

    # ------------------------------------------------ config persistence
    def _collect_config(self):
        return {
            "steps": [s.to_dict() for s in self.steps],
            "trigger_steps": [s.to_dict() for s in self.trigger_steps],
            "loop": self.loop_sequence.get(),
            "watch_points": [{"x": wp["x"], "y": wp["y"], "color": list(wp["color"]),
                               "tolerance": wp["tolerance"]} for wp in self.watch_points],
            "watch_x": self.watch_x.get(),
            "watch_y": self.watch_y.get(),
            "target_color": list(self.target_color),
            "tolerance": self.tolerance.get(),
            "watch_enabled": self.watch_enabled.get(),
            "poll_interval": self.poll_interval.get(),
            "start_hotkey": self.start_hotkey.get(),
            "stop_hotkey": self.stop_hotkey.get(),
            "panic_hotkey": self.panic_hotkey.get(),
            "trigger_mode": self.trigger_mode.get(),
            "cooldown": self.cooldown.get(),
            "idle_hold_enabled": self.idle_hold_enabled.get(),
            "idle_hold_key": self.idle_hold_key.get(),
            "jitter_enabled": self.jitter_enabled.get(),
            "jitter_percent": self.jitter_percent.get(),
            "dry_run": self.dry_run.get(),
        }

    def _apply_config(self, data):
        self.steps = [Step.from_dict(d) for d in data.get("steps", [])]
        self.trigger_steps = [Step.from_dict(d) for d in data.get("trigger_steps", [])]
        self.loop_sequence.set(data.get("loop", False))
        self.watch_points = [{"x": wp["x"], "y": wp["y"], "color": tuple(wp["color"]),
                               "tolerance": wp["tolerance"]} for wp in data.get("watch_points", [])]
        self.watch_x.set(data.get("watch_x", 0))
        self.watch_y.set(data.get("watch_y", 0))
        self.target_color = tuple(data.get("target_color", (255, 0, 0)))
        self.tolerance.set(data.get("tolerance", 20))
        self.watch_enabled.set(data.get("watch_enabled", False))
        self.poll_interval.set(data.get("poll_interval", 0.1))
        self.start_hotkey.set(data.get("start_hotkey", "f6"))
        self.stop_hotkey.set(data.get("stop_hotkey", "f7"))
        self.panic_hotkey.set(data.get("panic_hotkey", "esc"))
        self.trigger_mode.set(data.get("trigger_mode", "resume"))
        self.cooldown.set(data.get("cooldown", 1.5))
        self.idle_hold_enabled.set(data.get("idle_hold_enabled", False))
        self.idle_hold_key.set(data.get("idle_hold_key", "f"))
        self.jitter_enabled.set(data.get("jitter_enabled", False))
        self.jitter_percent.set(data.get("jitter_percent", 15.0))
        self.dry_run.set(data.get("dry_run", False))
        self._refresh_main_list()
        self._refresh_trigger_list()
        self._refresh_watchpoints_list()
        self.color_swatch.config(bg=self._hex(self.target_color))
        self._register_hotkeys()

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self._collect_config(), f, indent=2)
            self.log("Config saved.")
        except Exception as e:
            self.log(f"ERROR saving config: {e}")
            messagebox.showerror("Save Error", str(e))

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            self._apply_config(data)
            self.log("Config loaded from previous session.")
        except Exception as e:
            self.log(f"ERROR loading config: {e}")

    def on_close(self):
        self._save_config()
        self.stop_macro()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = PixelKeyMacro(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
