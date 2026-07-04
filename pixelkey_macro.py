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

        self.log_queue = queue.Queue()

        # pixel watch state
        self.watch_x = tk.IntVar(value=0)
        self.watch_y = tk.IntVar(value=0)
        self.target_color = (255, 0, 0)
        self.tolerance = tk.IntVar(value=20)
        self.watch_enabled = tk.BooleanVar(value=False)
        self.poll_interval = tk.DoubleVar(value=0.1)

        self.start_hotkey = tk.StringVar(value="f6")
        self.stop_hotkey = tk.StringVar(value="f7")

        self.idle_hold_enabled = tk.BooleanVar(value=False)
        self.idle_hold_key = tk.StringVar(value="f")

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
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 6))
        tk.Label(header, text="PixelKey Macro", bg=BG, fg=ORG, font=FONT_TITLE).pack(side="left")
        self.status_lbl = tk.Label(header, text="● STOPPED", bg=BG, fg=FG_DIM, font=FONT_B)
        self.status_lbl.pack(side="right")

        nb_style = ttk.Style()
        nb_style.theme_use("default")
        nb_style.configure("TNotebook", background=BG, borderwidth=0)
        nb_style.configure("TNotebook.Tab", background=BG2, foreground=FG,
                            padding=(14, 8), font=FONT_B)
        nb_style.map("TNotebook.Tab", background=[("selected", ORG)],
                     foreground=[("selected", "#1C1917")])

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=20, pady=10)

        seq_tab = tk.Frame(nb, bg=BG)
        trig_tab = tk.Frame(nb, bg=BG)
        pixel_tab = tk.Frame(nb, bg=BG)
        settings_tab = tk.Frame(nb, bg=BG)
        nb.add(seq_tab, text="  Sequence  ")
        nb.add(trig_tab, text="  Trigger Sequence  ")
        nb.add(pixel_tab, text="  Pixel Trigger  ")
        nb.add(settings_tab, text="  Settings  ")

        self._build_step_editor(seq_tab, is_trigger=False)
        self._build_step_editor(trig_tab, is_trigger=True)
        self._build_pixel_tab(pixel_tab)
        self._build_settings_tab(settings_tab)

        # console
        self._section_label(self.root, "CONSOLE", pad=(0, 4))
        console_frame = tk.Frame(self.root, bg=BG2)
        console_frame.pack(fill="both", padx=20, pady=(0, 4))
        self.console = tk.Text(console_frame, height=8, bg=BG2, fg="#8CE99A",
                                font=FONT_MONO, bd=0, highlightthickness=0,
                                state="disabled", wrap="word")
        self.console.pack(fill="both", expand=True, padx=8, pady=8)
        RoundButton(self.root, "Clear Console", self._clear_console, bg=BG3, fg=FG,
                    hover="#3f3a36", width=14).pack(anchor="e", padx=20, pady=(0, 8))

        # bottom controls
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 18))
        self.start_btn = RoundButton(bottom, "▶ START (F6)", self.start_macro, bg=GREEN, fg="white")
        self.start_btn.pack(side="left", padx=(0, 8), fill="x", expand=True)
        self.stop_btn = RoundButton(bottom, "■ STOP (F7)", self.stop_macro, bg=RED, fg="white")
        self.stop_btn.pack(side="left", fill="x", expand=True)

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", tk.END)
        self.console.config(state="disabled")

    def _section_label(self, parent, text, pad=(12, 4)):
        px = 20 if parent is self.root else 0
        tk.Label(parent, text=text, bg=BG, fg=FG_DIM, font=FONT_B).pack(anchor="w", pady=pad, padx=px)

    # ---- generic step editor (used for both Sequence and Trigger Sequence)
    def _build_step_editor(self, parent, is_trigger):
        target_list = self.trigger_steps if is_trigger else self.steps
        title = "REACTION STEPS (what to do when pixel color is detected)" if is_trigger \
            else "MAIN STEPS (executed in order, top to bottom)"
        self._section_label(parent, title)

        list_frame = tk.Frame(parent, bg=BG2)
        list_frame.pack(fill="both", expand=True, pady=(0, 8))
        listbox = tk.Listbox(list_frame, bg=BG2, fg=FG, font=FONT,
                              selectbackground=ORG, selectforeground="#1C1917",
                              bd=0, highlightthickness=0, activestyle="none")
        listbox.pack(fill="both", expand=True, padx=8, pady=8)

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
        self._section_label(parent, "PIXEL COLOR TRIGGER")
        tk.Label(parent, text="When enabled, the current step pauses (remembering exactly\n"
                              "where it was) and the Trigger Sequence runs as soon as the\n"
                              "chosen pixel matches the target color.",
                 bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(0, 10))

        tk.Checkbutton(parent, text="Enable pixel-color trigger", variable=self.watch_enabled,
                       bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                       activeforeground=FG, font=FONT_B).pack(anchor="w", pady=(0, 10))

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
        tol_frame.pack(fill="x", pady=10)
        tk.Label(tol_frame, text="Tolerance:", bg=BG, fg=FG, font=FONT).pack(side="left", padx=(0, 8))
        tk.Scale(tol_frame, from_=0, to=100, orient="horizontal", variable=self.tolerance,
                 bg=BG, fg=FG, troughcolor=BG3, highlightthickness=0, length=250).pack(side="left")

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
        RoundButton(parent, "Apply Hotkeys", self._register_hotkeys, width=14).pack(anchor="w", pady=10)

        self._section_label(parent, "PIXEL POLL INTERVAL (seconds)")
        tk.Scale(parent, from_=0.02, to=1.0, resolution=0.02, orient="horizontal",
                 variable=self.poll_interval, bg=BG, fg=FG, troughcolor=BG3,
                 highlightthickness=0, length=250).pack(anchor="w")

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

    # ------------------------------------------------ macro engine
    def _register_hotkeys(self):
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(self.start_hotkey.get(), self.start_macro)
            keyboard.add_hotkey(self.stop_hotkey.get(), self.stop_macro)
            self.log(f"Hotkeys set: Start={self.start_hotkey.get()}  Stop={self.stop_hotkey.get()}")
        except Exception as e:
            self.log(f"ERROR setting hotkeys: {e}")
            messagebox.showerror("Hotkey Error", str(e))

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
        self.status_lbl.config(text="● RUNNING", fg=GREEN)
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
            self.root.after(0, lambda: self.status_lbl.config(text="● ERROR", fg=RED))

    def stop_macro(self):
        if not self.running and self.status_lbl.cget("text") == "● STOPPED":
            return
        self.stop_flag.set()
        self.running = False
        self.status_lbl.config(text="● STOPPED", fg=FG_DIM)
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

    def _watch_loop(self):
        while not self.stop_flag.is_set():
            if self.watch_enabled.get() and not self.trigger_event.is_set():
                now = time.time()
                if now - self._last_trigger_time >= self.cooldown.get():
                    try:
                        x, y = self.watch_x.get(), self.watch_y.get()
                        px = ImageGrab.grab().getpixel((x, y))[:3]
                        if self._colors_match(px, self.target_color, self.tolerance.get()):
                            self.log(f"Pixel color MATCHED at ({x},{y}) -> RGB{px}. Triggering reaction sequence.")
                            self.trigger_event.set()
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
            self.root.after(0, lambda: self.status_lbl.config(text="● STOPPED", fg=FG_DIM))
            self.log("Main sequence finished (no loop).")

    def _execute_step_interruptible(self, step):
        """Runs a single main-sequence step, remembering exact elapsed time so a
        pixel-trigger interrupt can resume it precisely where it paused."""
        total = step.duration_seconds()
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
        keyboard.press(key)
        last_reassert = time.time()

        while not self.stop_flag.is_set():
            if self.watch_enabled.get() and self.trigger_event.is_set():
                self.log(f"Idle Hold on '{key}' interrupted -> running Trigger Sequence")
                keyboard.release(key)
                self.trigger_event.clear()
                self._last_trigger_time = time.time()

                self._run_trigger_sequence()

                if self.trigger_mode.get() == "stop":
                    self.log("Trigger mode = STOP. Halting macro.")
                    self.root.after(0, self.stop_macro)
                    return

                self.log(f"Resuming Idle Hold on '{key}'")
                keyboard.press(key)
                last_reassert = time.time()

            if time.time() - last_reassert >= 0.2:
                keyboard.press(key)
                last_reassert = time.time()

            time.sleep(0.05)

        try:
            keyboard.release(key)
        except Exception:
            pass
        self.running = False

    def _press_start(self, step):
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
            dur = step.duration_seconds()
            end = time.time() + dur
            while time.time() < end:
                if self.stop_flag.is_set():
                    self._press_end(step)
                    return
                time.sleep(min(0.05, max(0, end - time.time())))
            self._press_end(step)
        self.log("Trigger Sequence complete.")

    # ------------------------------------------------ config persistence
    def _save_config(self):
        data = {
            "steps": [s.to_dict() for s in self.steps],
            "trigger_steps": [s.to_dict() for s in self.trigger_steps],
            "loop": self.loop_sequence.get(),
            "watch_x": self.watch_x.get(),
            "watch_y": self.watch_y.get(),
            "target_color": self.target_color,
            "tolerance": self.tolerance.get(),
            "watch_enabled": self.watch_enabled.get(),
            "poll_interval": self.poll_interval.get(),
            "start_hotkey": self.start_hotkey.get(),
            "stop_hotkey": self.stop_hotkey.get(),
            "trigger_mode": self.trigger_mode.get(),
            "cooldown": self.cooldown.get(),
            "idle_hold_enabled": self.idle_hold_enabled.get(),
            "idle_hold_key": self.idle_hold_key.get(),
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
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
            self.steps = [Step.from_dict(d) for d in data.get("steps", [])]
            self.trigger_steps = [Step.from_dict(d) for d in data.get("trigger_steps", [])]
            self.loop_sequence.set(data.get("loop", False))
            self.watch_x.set(data.get("watch_x", 0))
            self.watch_y.set(data.get("watch_y", 0))
            self.target_color = tuple(data.get("target_color", (255, 0, 0)))
            self.tolerance.set(data.get("tolerance", 20))
            self.watch_enabled.set(data.get("watch_enabled", False))
            self.poll_interval.set(data.get("poll_interval", 0.1))
            self.start_hotkey.set(data.get("start_hotkey", "f6"))
            self.stop_hotkey.set(data.get("stop_hotkey", "f7"))
            self.trigger_mode.set(data.get("trigger_mode", "resume"))
            self.cooldown.set(data.get("cooldown", 1.5))
            self.idle_hold_enabled.set(data.get("idle_hold_enabled", False))
            self.idle_hold_key.set(data.get("idle_hold_key", "f"))
            self._refresh_main_list()
            self._refresh_trigger_list()
            self.color_swatch.config(bg=self._hex(self.target_color))
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
