"""
PixelKey Macro
--------------
Macro tool with:
  - Custom key-sequence builder (hold key for N seconds/minutes, or press key,
    any number of steps, optional loop)
  - Pixel color watcher (pick a screen pixel + target color + tolerance,
    triggers the sequence automatically when the color is detected)
  - Global hotkey Start/Stop

Author: JadeSCRIPTZ
"""

import json
import os
import threading
import time
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
FONT_TITLE = ("Segoe UI", 15, "bold")

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".pixelkey_macro_config.json")

STEP_TYPES = ["Hold Key", "Press Key"]
TIME_UNITS = ["seconds", "minutes"]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


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
        return f'Press "{self.key}"  ({self.duration} {self.unit} pause after)'


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
        self.root.geometry("620x680")
        self.root.minsize(560, 600)

        self.steps = []
        self.loop_sequence = tk.BooleanVar(value=False)
        self.running = False
        self.watching = False
        self.stop_flag = threading.Event()

        # pixel watch state
        self.watch_x = tk.IntVar(value=0)
        self.watch_y = tk.IntVar(value=0)
        self.target_color = (255, 0, 0)
        self.tolerance = tk.IntVar(value=20)
        self.watch_enabled = tk.BooleanVar(value=False)
        self.poll_interval = tk.DoubleVar(value=0.1)

        self.start_hotkey = tk.StringVar(value="f6")
        self.stop_hotkey = tk.StringVar(value="f7")

        self._build_ui()
        self._load_config()
        self._register_hotkeys()

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
                            padding=(16, 8), font=FONT_B)
        nb_style.map("TNotebook.Tab", background=[("selected", ORG)],
                     foreground=[("selected", "#1C1917")])

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=20, pady=10)

        seq_tab = tk.Frame(nb, bg=BG)
        pixel_tab = tk.Frame(nb, bg=BG)
        settings_tab = tk.Frame(nb, bg=BG)
        nb.add(seq_tab, text="  Sequence  ")
        nb.add(pixel_tab, text="  Pixel Trigger  ")
        nb.add(settings_tab, text="  Settings  ")

        self._build_sequence_tab(seq_tab)
        self._build_pixel_tab(pixel_tab)
        self._build_settings_tab(settings_tab)

        # bottom controls
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 18))
        self.start_btn = RoundButton(bottom, "▶ START (F6)", self.start_macro, bg=GREEN, fg="white")
        self.start_btn.pack(side="left", padx=(0, 8), fill="x", expand=True)
        self.stop_btn = RoundButton(bottom, "■ STOP (F7)", self.stop_macro, bg=RED, fg="white")
        self.stop_btn.pack(side="left", fill="x", expand=True)

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=FG_DIM, font=FONT_B).pack(anchor="w", pady=(12, 4))

    # ---- Sequence tab
    def _build_sequence_tab(self, parent):
        self._section_label(parent, "STEPS (executed in order, top to bottom)")

        list_frame = tk.Frame(parent, bg=BG2)
        list_frame.pack(fill="both", expand=True, pady=(0, 8))
        self.steps_listbox = tk.Listbox(list_frame, bg=BG2, fg=FG, font=FONT,
                                         selectbackground=ORG, selectforeground="#1C1917",
                                         bd=0, highlightthickness=0, activestyle="none")
        self.steps_listbox.pack(fill="both", expand=True, padx=8, pady=8)

        form = tk.Frame(parent, bg=BG)
        form.pack(fill="x", pady=6)

        tk.Label(form, text="Action:", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, sticky="w", padx=4)
        self.action_var = tk.StringVar(value=STEP_TYPES[0])
        action_menu = ttk.Combobox(form, textvariable=self.action_var, values=STEP_TYPES,
                                    state="readonly", width=12)
        action_menu.grid(row=0, column=1, padx=4)

        tk.Label(form, text="Key:", bg=BG, fg=FG, font=FONT).grid(row=0, column=2, sticky="w", padx=4)
        self.key_var = tk.StringVar(value="a")
        key_entry = tk.Entry(form, textvariable=self.key_var, width=8, bg=BG3, fg=FG,
                              insertbackground=FG, relief="flat")
        key_entry.grid(row=0, column=3, padx=4)

        tk.Label(form, text="Duration:", bg=BG, fg=FG, font=FONT).grid(row=0, column=4, sticky="w", padx=4)
        self.duration_var = tk.DoubleVar(value=1.0)
        dur_entry = tk.Entry(form, textvariable=self.duration_var, width=6, bg=BG3, fg=FG,
                              insertbackground=FG, relief="flat")
        dur_entry.grid(row=0, column=5, padx=4)

        self.unit_var = tk.StringVar(value="seconds")
        unit_menu = ttk.Combobox(form, textvariable=self.unit_var, values=TIME_UNITS,
                                  state="readonly", width=8)
        unit_menu.grid(row=0, column=6, padx=4)

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(fill="x", pady=6)
        RoundButton(btn_row, "+ Add Step", self.add_step, width=12).pack(side="left", padx=(0, 6))
        RoundButton(btn_row, "Remove Selected", self.remove_step, bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)
        RoundButton(btn_row, "↑", self.move_up, bg=BG3, fg=FG, hover="#3f3a36", width=3).pack(side="left", padx=6)
        RoundButton(btn_row, "↓", self.move_down, bg=BG3, fg=FG, hover="#3f3a36", width=3).pack(side="left", padx=6)
        RoundButton(btn_row, "Clear All", self.clear_steps, bg=BG3, fg=FG, hover="#3f3a36").pack(side="left", padx=6)

        loop_row = tk.Frame(parent, bg=BG)
        loop_row.pack(fill="x", pady=(8, 0))
        chk = tk.Checkbutton(loop_row, text="Loop sequence continuously until Stop",
                              variable=self.loop_sequence, bg=BG, fg=FG,
                              selectcolor=BG2, activebackground=BG, activeforeground=FG,
                              font=FONT)
        chk.pack(anchor="w")

    def _build_pixel_tab(self, parent):
        self._section_label(parent, "PIXEL COLOR TRIGGER")
        tk.Label(parent, text="When enabled, the sequence starts automatically as soon as\n"
                              "the chosen pixel matches the target color.",
                 bg=BG, fg=FG_DIM, font=FONT, justify="left").pack(anchor="w", pady=(0, 10))

        chk = tk.Checkbutton(parent, text="Enable pixel-color auto-trigger", variable=self.watch_enabled,
                              bg=BG, fg=FG, selectcolor=BG2, activebackground=BG,
                              activeforeground=FG, font=FONT_B)
        chk.pack(anchor="w", pady=(0, 10))

        coord_frame = tk.Frame(parent, bg=BG)
        coord_frame.pack(fill="x", pady=4)
        tk.Label(coord_frame, text="X:", bg=BG, fg=FG, font=FONT).grid(row=0, column=0, padx=4)
        tk.Entry(coord_frame, textvariable=self.watch_x, width=8, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=1, padx=4)
        tk.Label(coord_frame, text="Y:", bg=BG, fg=FG, font=FONT).grid(row=0, column=2, padx=4)
        tk.Entry(coord_frame, textvariable=self.watch_y, width=8, bg=BG3, fg=FG,
                 insertbackground=FG, relief="flat").grid(row=0, column=3, padx=4)
        RoundButton(coord_frame, "🎯 Pick Pixel (hover + Enter)", self.pick_pixel,
                    bg=BG3, fg=FG, hover="#3f3a36").grid(row=0, column=4, padx=10)

        color_frame = tk.Frame(parent, bg=BG)
        color_frame.pack(fill="x", pady=10)
        self.color_swatch = tk.Label(color_frame, text="", bg=self._hex(self.target_color),
                                      width=6, relief="flat")
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

        self.live_color_lbl = tk.Label(parent, text="Live pixel color: -", bg=BG, fg=FG_DIM, font=FONT)
        self.live_color_lbl.pack(anchor="w", pady=(10, 0))
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

    # ------------------------------------------------ helpers
    def _hex(self, rgb):
        return '#%02x%02x%02x' % rgb

    def _update_live_color(self):
        try:
            x, y = self.watch_x.get(), self.watch_y.get()
            px = ImageGrab.grab().getpixel((x, y))
            self.live_color_lbl.config(text=f"Live pixel color: RGB{px}",
                                        fg=self._hex(px[:3]) if isinstance(px, tuple) else FG_DIM)
        except Exception:
            pass
        self.root.after(500, self._update_live_color)

    def pick_pixel(self):
        messagebox.showinfo("Pick Pixel",
                             "Move your mouse over the target pixel on screen,\n"
                             "then press ENTER (in this app is fine, just don't move away)\n"
                             "You have 3 seconds after closing this dialog.")
        self.root.after(3000, self._capture_mouse_pos)

    def _capture_mouse_pos(self):
        x, y = pyautogui.position()
        self.watch_x.set(x)
        self.watch_y.set(y)
        messagebox.showinfo("Pixel Captured", f"Captured pixel at ({x}, {y})")

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
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ------------------------------------------------ steps management
    def add_step(self):
        try:
            dur = float(self.duration_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Invalid duration", "Duration must be a number.")
            return
        if dur <= 0:
            messagebox.showerror("Invalid duration", "Duration must be greater than 0.")
            return
        key = self.key_var.get().strip()
        if not key:
            messagebox.showerror("Invalid key", "Please enter a key.")
            return
        step = Step(self.action_var.get(), key, dur, self.unit_var.get())
        self.steps.append(step)
        self._refresh_list()

    def remove_step(self):
        sel = self.steps_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        del self.steps[idx]
        self._refresh_list()

    def move_up(self):
        sel = self.steps_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self.steps[i - 1], self.steps[i] = self.steps[i], self.steps[i - 1]
        self._refresh_list()
        self.steps_listbox.selection_set(i - 1)

    def move_down(self):
        sel = self.steps_listbox.curselection()
        if not sel or sel[0] == len(self.steps) - 1:
            return
        i = sel[0]
        self.steps[i + 1], self.steps[i] = self.steps[i], self.steps[i + 1]
        self._refresh_list()
        self.steps_listbox.selection_set(i + 1)

    def clear_steps(self):
        if messagebox.askyesno("Clear All", "Remove all steps?"):
            self.steps.clear()
            self._refresh_list()

    def _refresh_list(self):
        self.steps_listbox.delete(0, tk.END)
        for i, s in enumerate(self.steps, 1):
            self.steps_listbox.insert(tk.END, f"{i}. {s.label()}")

    # ------------------------------------------------ macro engine
    def _register_hotkeys(self):
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        try:
            keyboard.add_hotkey(self.start_hotkey.get(), self.start_macro)
            keyboard.add_hotkey(self.stop_hotkey.get(), self.stop_macro)
        except Exception as e:
            messagebox.showerror("Hotkey Error", str(e))

    def start_macro(self):
        if self.running:
            return
        if not self.steps:
            messagebox.showwarning("No Steps", "Add at least one step to the sequence first.")
            return
        self.stop_flag.clear()
        self.running = True
        self.status_lbl.config(text="● RUNNING", fg=GREEN)

        if self.watch_enabled.get():
            self.watching = True
            threading.Thread(target=self._watch_loop, daemon=True).start()
        else:
            threading.Thread(target=self._run_sequence, daemon=True).start()

    def stop_macro(self):
        self.stop_flag.set()
        self.running = False
        self.watching = False
        self.status_lbl.config(text="● STOPPED", fg=FG_DIM)
        # release any held keys just in case
        for s in self.steps:
            if s.action == "Hold Key":
                try:
                    keyboard.release(s.key)
                except Exception:
                    pass

    def _colors_match(self, c1, c2, tol):
        return all(abs(a - b) <= tol for a, b in zip(c1, c2))

    def _watch_loop(self):
        x, y = self.watch_x.get(), self.watch_y.get()
        tol = self.tolerance.get()
        interval = self.poll_interval.get()
        while not self.stop_flag.is_set():
            try:
                px = ImageGrab.grab().getpixel((x, y))[:3]
                if self._colors_match(px, self.target_color, tol):
                    self._run_sequence(single_pass_only=not self.loop_sequence.get())
                    if not self.loop_sequence.get():
                        break
            except Exception:
                pass
            time.sleep(interval)
        self.root.after(0, lambda: self.status_lbl.config(text="● STOPPED", fg=FG_DIM))
        self.running = False

    def _run_sequence(self, single_pass_only=False):
        first = True
        while first or (self.loop_sequence.get() and not self.stop_flag.is_set() and not self.watch_enabled.get()):
            first = False
            for step in self.steps:
                if self.stop_flag.is_set():
                    return
                if step.action == "Hold Key":
                    keyboard.press(step.key)
                    self._sleep_interruptible(step.duration_seconds())
                    keyboard.release(step.key)
                else:  # Press Key
                    keyboard.press_and_release(step.key)
                    self._sleep_interruptible(step.duration_seconds())
            if single_pass_only:
                break
        if not self.watch_enabled.get():
            self.running = False
            self.root.after(0, lambda: self.status_lbl.config(text="● STOPPED", fg=FG_DIM))

    def _sleep_interruptible(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            if self.stop_flag.is_set():
                return
            time.sleep(min(0.05, max(0, end - time.time())))

    # ------------------------------------------------ config persistence
    def _save_config(self):
        data = {
            "steps": [s.to_dict() for s in self.steps],
            "loop": self.loop_sequence.get(),
            "watch_x": self.watch_x.get(),
            "watch_y": self.watch_y.get(),
            "target_color": self.target_color,
            "tolerance": self.tolerance.get(),
            "watch_enabled": self.watch_enabled.get(),
            "poll_interval": self.poll_interval.get(),
            "start_hotkey": self.start_hotkey.get(),
            "stop_hotkey": self.stop_hotkey.get(),
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            self.steps = [Step.from_dict(d) for d in data.get("steps", [])]
            self.loop_sequence.set(data.get("loop", False))
            self.watch_x.set(data.get("watch_x", 0))
            self.watch_y.set(data.get("watch_y", 0))
            self.target_color = tuple(data.get("target_color", (255, 0, 0)))
            self.tolerance.set(data.get("tolerance", 20))
            self.watch_enabled.set(data.get("watch_enabled", False))
            self.poll_interval.set(data.get("poll_interval", 0.1))
            self.start_hotkey.set(data.get("start_hotkey", "f6"))
            self.stop_hotkey.set(data.get("stop_hotkey", "f7"))
            self._refresh_list()
            self.color_swatch.config(bg=self._hex(self.target_color))
        except Exception:
            pass

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
