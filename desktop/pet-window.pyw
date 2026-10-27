"""Mint Budgie desktop overlay for DeepSeek Harness.

The dsh Host writes state.json. This independent process polls that file,
plays the matching sprite row, and shows a Codex-style task bubble only while
the agent is busy.
"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageTk

import tkinter as tk


CELL_W = 192
CELL_H = 208
DEFAULT_SCALE = 0.62
DEFAULT_SIZE_PERCENT = 65
MIN_SIZE_PERCENT = 30
MAX_SIZE_PERCENT = 180
DEFAULT_OPACITY_PERCENT = 75
MIN_OPACITY_PERCENT = 20
MAX_OPACITY_PERCENT = 100
MIN_SETTINGS_WIDTH = 320
MIN_SETTINGS_HEIGHT = 230
DEFAULT_SETTINGS_WIDTH = 420
DEFAULT_SETTINGS_HEIGHT = 270
POSE_NAMES = ("idle", "head-tilt", "head-stretch")
GESTURE_POSES = ("head-tilt", "head-stretch")
CLICK_POSES = ("head-tilt", "head-stretch")
STAND_FRAME_MS = 80
POSE_FRAME_MS = {
    "idle": 1000,
    "head-tilt": 220,
    "head-stretch": 180,
}
POSE_FRAME_COUNTS = {
    "idle": 6,
    "head-tilt": 7,
    "head-stretch": 7,
}
RUNNING_JUMP_SCALE = 0.4

ROWS = [
    ("idle", 6),
    ("running-right", 8),
    ("running-left", 8),
    ("waving", 4),
    ("jumping", 5),
    ("failed", 8),
    ("waiting", 6),
    ("running", 6),
    ("review", 6),
]
ROW_INDEX = {name: index for index, (name, _) in enumerate(ROWS)}
ROW_FRAMES = [frames for _, frames in ROWS]

FRAME_MS = {
    "idle": 220,
    "running-right": 90,
    "running-left": 90,
    "waving": 200,
    "jumping": 130,
    "failed": 150,
    "waiting": 240,
    "running": 190,
    "review": 200,
}

STATUS_COLORS = {
    "running": (154, 216, 184, 255),
    "waiting": (242, 191, 92, 255),
    "failed": (247, 123, 123, 255),
    "review": (151, 192, 244, 255),
}

ROW_FOR_STATUS = {
    "running": "running",
    "waiting": "waiting",
    "failed": "failed",
    "review": "review",
    "idle": "idle",
}

TRANSPARENT_KEY = "#010203"
CARD_BG = "#242424"
CARD_RAISED = "#30343c"
TEXT = "#f2f4f8"
TEXT_MUTED = "#aeb4c0"
ACCENT = "#9ad8b8"
BUBBLE_WIDTH = 284
BUBBLE_HEIGHT = 65
BUBBLE_RADIUS = 18
BUBBLE_OPACITY = 0.88
MARQUEE_STEP_MS = 38

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def load_font(size: int, bold: bool = False):
    candidates = FONT_CANDIDATES
    if bold and os.path.exists(r"C:\Windows\Fonts\msyhbd.ttc"):
        candidates = [r"C:\Windows\Fonts\msyhbd.ttc", *FONT_CANDIDATES]
    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def keyed_photo(image: Image.Image) -> ImageTk.PhotoImage:
    """Flatten alpha onto Tk's colour key without dark anti-alias fringes."""
    rgba = image.convert("RGBA")
    mask = rgba.getchannel("A").point(lambda alpha: 255 if alpha >= 128 else 0)
    keyed = Image.new("RGB", rgba.size, TRANSPARENT_KEY)
    keyed.paste(rgba.convert("RGB"), (0, 0), mask)
    return ImageTk.PhotoImage(keyed)




def rounded_card(
    width: int,
    height: int,
    radius: int = 14,
    fill=(34, 37, 43, 255),
    outline=None,
) -> Image.Image:
    scale = 4
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale,
        fill=fill,
        outline=outline,
        width=0 if outline is None else scale,
    )
    return image.resize((width, height), Image.Resampling.LANCZOS)


def fit_text(draw, text: str, font, max_width: int) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    clipped = text
    while clipped:
        candidate = clipped + "\u2026"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
        clipped = clipped[:-1]
    return "\u2026"


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text: str, command, width: int, primary=False):
        super().__init__(
            parent,
            width=width,
            height=32,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.command = command
        self.primary = primary
        self.hovered = False
        self.text = text
        self._draw()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", lambda _event: self.command())

    def _draw(self):
        self.delete("all")
        width = int(self.cget("width"))
        height = int(self.cget("height"))
        if self.primary:
            fill = "#edf9f2" if self.hovered else "#d9f1e5"
            fg = "#17251e"
            outline = fill
        else:
            fill = "#3a3f49" if self.hovered else CARD_RAISED
            fg = TEXT
            outline = "#454b56"
        self.create_rectangle(1, 1, width - 1, height - 1, fill=fill, outline=outline)
        self.create_text(
            width // 2,
            height // 2 + 1,
            text=self.text,
            fill=fg,
            font=("Microsoft YaHei UI", 9),
        )

    def _on_enter(self, _event):
        self.hovered = True
        self._draw()

    def _on_leave(self, _event):
        self.hovered = False
        self._draw()


class SettingSlider:
    """Label, hint, track, thumb, editable value and reset action."""

    def __init__(
        self,
        parent,
        y: int,
        title: str,
        hint: str,
        value: int,
        minimum: int,
        maximum: int,
        default: int,
        command,
        on_reset,
        layout,
    ):
        self.parent = parent
        self.y = y
        self.minimum = minimum
        self.maximum = maximum
        self.command = command
        self.on_reset = on_reset
        self.layout_callback = layout
        self.value = clamp(value, minimum, maximum)

        self.title_label = tk.Label(
            parent,
            text=title,
            bg=CARD_BG,
            fg=TEXT,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.hint_label = tk.Label(
            parent,
            text=hint,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Microsoft YaHei UI", 8),
        )

        self.track = tk.Canvas(
            parent,
            width=1,
            height=28,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.track.place(
            x=0,
            y=0,
            width=1,
            height=28,
        )
        self.track.bind("<Button-1>", self._on_track_press)
        self.track.bind("<B1-Motion>", self._on_track_drag)
        self.track.bind("<ButtonRelease-1>", self._on_track_release)
        self.track.bind("<Configure>", lambda _event: self.parent.after_idle(self._draw_track))
        self.track_press = None

        self.value_var = tk.StringVar(value=str(self.value))
        self.entry = tk.Entry(
            parent,
            textvariable=self.value_var,
            width=4,
            justify="right",
            bg=CARD_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#3a3a3a",
            highlightcolor="#6f6f6f",
            font=("Microsoft YaHei UI", 9),
        )
        self.entry.place(x=0, y=0, width=43, height=25)
        self.percent_label = tk.Label(
            parent,
            text="%",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Microsoft YaHei UI", 8),
        )

        self.reset_label = tk.Label(
            parent,
            text="\u91cd\u7f6e",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            cursor="hand2",
            font=("Microsoft YaHei UI", 9),
        )
        self.reset_label.bind("<Button-1>", lambda _event: self.on_reset())
        self.reset_label.bind(
            "<Enter>", lambda _event: self.reset_label.configure(fg=TEXT)
        )
        self.reset_label.bind(
            "<Leave>", lambda _event: self.reset_label.configure(fg=TEXT_MUTED)
        )

        self._entry_job = None
        self.entry.bind("<Return>", self._apply_entry)
        self.entry.bind("<FocusOut>", self._apply_entry)
        self.entry.bind("<KeyRelease>", self._schedule_entry)
        self.layout()
        self._draw_track()

    @property
    def height(self) -> int:
        return 80

    def layout(self):
        left, width = self.layout_callback()
        label_width = 150 if width >= 380 else 132
        value_left = left + width - 82
        track_left = left + label_width
        track_right = value_left - 12
        track_width = max(54, track_right - track_left)
        self.title_label.place(x=left, y=self.y)
        self.hint_label.place(x=left, y=self.y + 21)
        self.track.place(
            x=track_left,
            y=self.y + 11,
            width=track_width,
            height=28,
        )
        self.entry.place(x=value_left, y=self.y + 3, width=43, height=25)
        self.percent_label.place(x=value_left + 46, y=self.y + 8)
        self.reset_label.place(x=value_left + 4, y=self.y + 34)
        self._draw_track()

    def _thumb_x(self, width: int) -> int:
        fraction = (self.value - self.minimum) / (self.maximum - self.minimum)
        return round(9 + fraction * max(0, width - 18))

    def _draw_track(self):
        width = max(20, self.track.winfo_width())
        thumb = self._thumb_x(width)
        self.track.delete("all")
        self.track.create_line(
            9,
            14,
            width - 9,
            14,
            fill="#4b4b4b",
            width=2,
        )
        self.track.create_line(
            9,
            14,
            thumb,
            14,
            fill="#d9d9d9",
            width=2,
        )
        self.track.create_oval(
            thumb - 8,
            6,
            thumb + 8,
            22,
            fill="#f0f0f0",
            outline="#f0f0f0",
        )

    def _set_from_x(self, x: int, notify: bool):
        width = max(20, self.track.winfo_width())
        fraction = (x - 9) / max(1, width - 18)
        value = round(self.minimum + fraction * (self.maximum - self.minimum))
        self.set_value(value, notify)

    def _on_track_press(self, event):
        # Grabbing the track or thumb moves it immediately; a background click
        # outside the thumb does not jump the value unexpectedly.
        thumb = self._thumb_x(max(20, self.track.winfo_width()))
        if abs(event.x - thumb) <= 14:
            self.track_press = event.x
            self._set_from_x(event.x, True)
        else:
            self.track_press = None

    def _on_track_drag(self, event):
        if self.track_press is None:
            return
        self._set_from_x(event.x, True)

    def _on_track_release(self, _event):
        self.track_press = None

    def set_value(self, value: int, notify: bool):
        value = clamp(round(value), self.minimum, self.maximum)
        changed = value != self.value
        self.value = value
        self.value_var.set(str(value))
        self._draw_track()
        if notify and changed:
            self.command(value)

    def _schedule_entry(self, _event=None):
        if self._entry_job:
            try:
                self.parent.after_cancel(self._entry_job)
            except tk.TclError:
                pass
        self._entry_job = self.parent.after(300, self._apply_entry)

    def _apply_entry(self, _event=None):
        self._entry_job = None
        try:
            value = round(float(self.value_var.get().strip()))
        except ValueError:
            self.value_var.set(str(self.value))
            return
        self.set_value(value, True)


def enable_dpi_awareness():
    """Keep Tk coordinates aligned with physical pixels across mixed-DPI screens."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_context = user32.SetProcessDpiAwarenessContext
        set_context.argtypes = [wintypes.HANDLE]
        set_context.restype = wintypes.BOOL
        if set_context(wintypes.HANDLE(-4)):
            return
    except (AttributeError, OSError, OverflowError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class StatusBubble:
    """Separate translucent rounded task bubble above the pet."""

    def __init__(self, pet):
        self.pet = pet
        self.pet_hovered = False
        self.minimize_hovered = False
        self.window = tk.Toplevel(pet.root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.window.attributes("-alpha", BUBBLE_OPACITY)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.canvas = tk.Canvas(
            self.window,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.image_item = self.canvas.create_image(0, 0, anchor="nw")
        self.photo = None
        self.width = 0
        self.height = 0
        self.task_font = load_font(13, bold=True)
        self.activity_font = load_font(11)
        self.status = "idle"
        self.task = ""
        self.activity = ""
        self.activity_width = 0
        self.visible = False
        self.collapsed = False
        self.minimize_pressed = False
        self.scroll_offset = 0
        self.marquee_job = None
        self.last_width = BUBBLE_WIDTH

        for widget in (self.window, self.canvas):
            widget.bind("<ButtonPress-1>", self._on_press)
            widget.bind("<B1-Motion>", self.pet._on_drag)
            widget.bind("<ButtonRelease-1>", self._on_release)
            widget.bind("<Double-Button-1>", self._on_double_click)
            widget.bind("<Button-3>", self.pet._on_right_click)
            widget.bind("<Motion>", self._on_motion)
            widget.bind("<Leave>", self._on_leave)

    def update(self, status: str, task: str, activity: str = ""):
        self.status = status
        self.task = task.strip()
        self.activity = activity.strip()
        self.visible = status in ("running", "waiting", "failed", "review")
        if not self.visible or self.collapsed:
            self._stop_marquee()
            self.window.withdraw()
            return
        self.scroll_offset = 0
        self._render()
        self.window.deiconify()
        self.window.lift()
        self.place()
        self._start_marquee()

    def toggle_collapsed(self):
        self.collapsed = not self.collapsed
        if self.collapsed or not self.visible:
            self._stop_marquee()
            self.window.withdraw()
            return
        self.scroll_offset = 0
        self._render()
        self.window.deiconify()
        self.window.lift()
        self.place()
        self._start_marquee()

    def minimize(self):
        if not self.collapsed:
            self.toggle_collapsed()

    def hide_temporarily(self):
        self.collapsed = True
        self._stop_marquee()
        self.window.withdraw()

    def restore(self):
        if self.collapsed:
            self.toggle_collapsed()

    def _render(self):
        probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        width = BUBBLE_WIDTH
        height = BUBBLE_HEIGHT
        title_text = fit_text(probe, self.task, self.task_font, width - 52)
        card = rounded_card(
            width,
            height,
            radius=BUBBLE_RADIUS,
            fill=(31, 32, 37, 255),
            outline=None,
        )
        draw = ImageDraw.Draw(card)
        dot_color = STATUS_COLORS.get(self.status, TEXT_MUTED)
        draw.ellipse((17, 15, 21, 19), fill=dot_color)
        draw.text((29, 8), title_text, font=self.task_font, fill=TEXT)
        self._draw_minimize_button(card, self.minimize_hovered)
        activity_text = self.activity
        self.activity_width = probe.textbbox(
            (0, 0),
            activity_text,
            font=self.activity_font,
        )[2]
        activity_area = width - 46
        if self.activity_width <= activity_area:
            self.scroll_offset = 0
            draw.text(
                (29, 37),
                activity_text,
                font=self.activity_font,
                fill=TEXT_MUTED,
            )
        else:
            gap = 48
            cycle = self.activity_width + gap
            start_x = width - 10
            x = start_x - self.scroll_offset
            strip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            strip_draw = ImageDraw.Draw(strip)
            strip_draw.text(
                (x, 37),
                activity_text,
                font=self.activity_font,
                fill=TEXT_MUTED,
            )
            strip_draw.text(
                (x + cycle, 37),
                activity_text,
                font=self.activity_font,
                fill=TEXT_MUTED,
            )
            # Keep the card intact and mask only the independently drawn text.
            mask = Image.new("L", (width, height), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rectangle((27, 32, width - 18, height - 8), fill=255)
            alpha = Image.composite(
                strip.getchannel("A"),
                Image.new("L", (width, height), 0),
                mask,
            )
            strip.putalpha(alpha)
            card.alpha_composite(strip)
        self.width = width
        self.height = height
        self.photo = keyed_photo(card)
        self.canvas.configure(width=width, height=height)
        self.canvas.delete("all")
        self.image_item = self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.window.geometry(f"{width}x{height}+0+0")

    def _on_press(self, event):
        if self._inside_minimize(event.x, event.y):
            self.minimize_pressed = True
            return "break"
        return self.pet._on_press(event)

    def _on_release(self, event):
        if self.minimize_pressed:
            should_minimize = self._inside_minimize(event.x, event.y)
            self.minimize_pressed = False
            if should_minimize:
                self.minimize()
            return "break"
        return self.pet._on_release(event)

    def _on_double_click(self, event):
        if self._inside_minimize(event.x, event.y):
            return "break"
        return self.pet._on_double_click(event)

    @staticmethod
    def _inside_minimize(x, y):
        return BUBBLE_WIDTH - 37 <= x <= BUBBLE_WIDTH - 8 and 7 <= y <= 34

    def _on_motion(self, event):
        hovered = self._inside_minimize(event.x, event.y)
        if hovered != self.minimize_hovered:
            self.minimize_hovered = hovered
            self.canvas.configure(cursor="hand2" if hovered else "")
            self._render()

    def _on_leave(self, _event):
        self.minimize_pressed = False
        if self.minimize_hovered:
            self.minimize_hovered = False
            self.canvas.configure(cursor="")
            self._render()

    @staticmethod
    def _draw_minimize_button(card, hovered=False):
        button = Image.new("RGBA", card.size, (0, 0, 0, 0))
        button_draw = ImageDraw.Draw(button)
        button_draw.line(
            (BUBBLE_WIDTH - 29, 18, BUBBLE_WIDTH - 18, 18),
            fill=(235, 238, 242, 255 if hovered else 210),
            width=2,
        )
        card.alpha_composite(button)

    def _start_marquee(self):
        self._stop_marquee()
        if self.visible and self.activity_width > BUBBLE_WIDTH - 46:
            self.marquee_job = self.window.after(
                MARQUEE_STEP_MS,
                self._advance_marquee,
            )

    def _advance_marquee(self):
        self.marquee_job = None
        if not self.visible:
            return
        cycle = self.activity_width + 42
        self.scroll_offset = (self.scroll_offset + 1) % max(1, cycle)
        self._render()
        self.marquee_job = self.window.after(
            MARQUEE_STEP_MS,
            self._advance_marquee,
        )

    def _stop_marquee(self):
        if self.marquee_job is not None:
            try:
                self.window.after_cancel(self.marquee_job)
            except tk.TclError:
                pass
            self.marquee_job = None

    def place(self):
        if not self.visible:
            return
        try:
            self.window.update_idletasks()
            pet_w = self.pet.root.winfo_width()
            pet_h = self.pet.root.winfo_height()
        except tk.TclError:
            return
        if pet_w <= 1 or pet_h <= 1:
            return
        pet_x = self.pet.root.winfo_x()
        pet_y = self.pet.root.winfo_y()
        x = pet_x + pet_w // 2 - self.width // 2
        y = pet_y - self.height - 7
        desktop_left, desktop_top, desktop_right, desktop_bottom = (
            self.pet.virtual_desktop()
        )
        if y < desktop_top:
            y = pet_y + pet_h + 4
        x = clamp(x, desktop_left, max(desktop_left, desktop_right - self.width))
        y = clamp(y, desktop_top, max(desktop_top, desktop_bottom - self.height))
        self.window.geometry(f"+{x}+{y}")

    def destroy(self):
        self._stop_marquee()
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class ContextMenu:
    """Codex-style rounded menu opened by right-clicking the pet."""

    WIDTH = 180
    PAD = 7
    ROW_H = 38

    def __init__(self, pet, x_root: int, y_root: int):
        self.pet = pet
        self.items = [
            ("\u8bbe\u7f6e", pet.open_settings),
            ("\u9690\u85cf\u5ba0\u7269", pet.hide),
        ]
        self.hover = -1
        self.height = self.PAD * 2 + self.ROW_H * len(self.items)
        self.window = tk.Toplevel(pet.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.window.attributes("-alpha", 0.96 * pet.opacity_percent / 100)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.canvas = tk.Canvas(
            self.window,
            width=self.WIDTH,
            height=self.height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.canvas.pack()
        self.photo = None
        self.font = load_font(11)
        self._render()
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_click)
        self.window.bind("<Escape>", lambda _event: self.close())

        desktop_left, desktop_top, desktop_right, desktop_bottom = (
            pet.virtual_desktop()
        )
        x = clamp(x_root, desktop_left, max(desktop_left, desktop_right - self.WIDTH))
        y = clamp(y_root, desktop_top, max(desktop_top, desktop_bottom - self.height))
        self.window.geometry(f"{self.WIDTH}x{self.height}+{x}+{y}")
        self.window.lift()
        try:
            self.window.focus_force()
        except tk.TclError:
            pass

    def _row_at(self, y: int) -> int:
        index = (y - self.PAD) // self.ROW_H
        return index if 0 <= index < len(self.items) else -1

    def _render(self):
        image = rounded_card(self.WIDTH, self.height, radius=12)
        draw = ImageDraw.Draw(image)
        for index, (label, _command) in enumerate(self.items):
            top = self.PAD + index * self.ROW_H
            if index == self.hover:
                draw.rounded_rectangle(
                    (6, top + 2, self.WIDTH - 6, top + self.ROW_H - 2),
                    radius=8,
                    fill=(58, 63, 73, 255),
                )
            draw.text((18, top + 10), label, font=self.font, fill=TEXT)
        self.photo = keyed_photo(image)
        self.canvas.delete("all")
        self.background_item = self.canvas.create_image(
            0,
            0,
            image=self.photo,
            anchor="nw",
        )

    def _on_motion(self, event):
        row = self._row_at(event.y)
        if row != self.hover:
            self.hover = row
            self._render()

    def _on_click(self, event):
        row = self._row_at(event.y)
        if row < 0:
            return
        command = self.items[row][1]
        self.close()
        command()

    def close(self):
        if getattr(self.pet, "menu", None) is self:
            self.pet.menu = None
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class SettingsWindow:
    PAD = 24
    MIN_WIDTH = MIN_SETTINGS_WIDTH
    MIN_HEIGHT = MIN_SETTINGS_HEIGHT
    GRIP = 16

    def __init__(self, pet):
        self.pet = pet
        self.width, self.height = self._load_size()
        self.resize_origin = None
        self.resize_start = None
        self.window = tk.Toplevel(pet.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.window.attributes("-alpha", pet.opacity_percent / 100)
        self.window.configure(bg=TRANSPARENT_KEY)
        self.window.withdraw()
        self.canvas = tk.Canvas(
            self.window,
            width=self.width,
            height=self.height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.photo = None
        self.background_item = self.canvas.create_image(0, 0, anchor="nw")

        desktop_left, desktop_top, desktop_right, desktop_bottom = (
            pet.virtual_desktop()
        )
        x = clamp(
            pet.root.winfo_x() + pet.root.winfo_width() // 2 - self.width // 2,
            desktop_left,
            max(desktop_left, desktop_right - self.width),
        )
        y = clamp(
            pet.root.winfo_y() - self.height - 14,
            desktop_top,
            max(desktop_top, desktop_bottom - self.height),
        )
        if y <= desktop_top:
            y = clamp(
                pet.root.winfo_y() + pet.root.winfo_height() + 14,
                desktop_top,
                max(desktop_top, desktop_bottom - self.height),
            )
        self.window.update_idletasks()
        self.window.geometry(f"{self.width}x{self.height}+{x}+{y}")

        self.title = tk.Label(
            self.window,
            text="\u81ea\u5b9a\u4e49\u865a\u62df\u5ba0\u7269",
            bg=CARD_BG,
            fg=TEXT,
            font=("Microsoft YaHei UI", 13, "bold"),
        )
        self.title.place(x=self.PAD, y=17)

        self.close_button = tk.Canvas(
            self.window,
            width=28,
            height=28,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.close_button.create_line(9, 9, 19, 19, fill=TEXT_MUTED, width=1)
        self.close_button.create_line(19, 9, 9, 19, fill=TEXT_MUTED, width=1)
        self.close_button.bind("<Button-1>", lambda _event: self.close())

        self.size_slider = SettingSlider(
            self.window,
            y=70,
            title="\u865a\u62df\u5ba0\u7269\u5927\u5c0f",
            hint="\u8c03\u6574\u865a\u62df\u5ba0\u7269\u5927\u5c0f",
            value=pet.size_percent,
            minimum=MIN_SIZE_PERCENT,
            maximum=MAX_SIZE_PERCENT,
            default=DEFAULT_SIZE_PERCENT,
            command=pet.set_size_percent,
            on_reset=lambda: self.size_slider.set_value(
                DEFAULT_SIZE_PERCENT, notify=True
            ),
            layout=self._content_layout,
        )
        self.opacity_slider = SettingSlider(
            self.window,
            y=154,
            title="\u5ba0\u7269\u900f\u660e\u5ea6",
            hint="\u8c03\u6574\u5ba0\u7269\u548c\u4efb\u52a1\u6c14\u6ce1\u7684\u900f\u660e\u5ea6",
            value=pet.opacity_percent,
            minimum=MIN_OPACITY_PERCENT,
            maximum=MAX_OPACITY_PERCENT,
            default=DEFAULT_OPACITY_PERCENT,
            command=pet.set_opacity_percent,
            on_reset=lambda: self.opacity_slider.set_value(
                DEFAULT_OPACITY_PERCENT, notify=True
            ),
            layout=self._content_layout,
        )
        self.grip = tk.Canvas(
            self.window,
            width=self.GRIP,
            height=self.GRIP,
            bg=CARD_BG,
            highlightthickness=0,
            bd=0,
            cursor="bottom_right_corner",
        )
        self.grip.bind("<ButtonPress-1>", self._resize_press)
        self.grip.bind("<B1-Motion>", self._resize_drag)
        self.grip.bind("<ButtonRelease-1>", self._resize_release)

        self.window.bind("<Configure>", self._on_configure)
        self.window.bind("<Escape>", lambda _event: self.close())
        self._layout()
        self.window.deiconify()

    def _load_size(self):
        if not self.pet.settings_path or not self.pet.settings_path.exists():
            return DEFAULT_SETTINGS_WIDTH, DEFAULT_SETTINGS_HEIGHT
        try:
            data = json.loads(self.pet.settings_path.read_text("utf-8"))
            width = round(float(data.get("settingsWidth", DEFAULT_SETTINGS_WIDTH)))
            height = round(float(data.get("settingsHeight", DEFAULT_SETTINGS_HEIGHT)))
            return (
                clamp(width, self.MIN_WIDTH, 720),
                clamp(height, self.MIN_HEIGHT, 560),
            )
        except (OSError, ValueError, TypeError):
            return DEFAULT_SETTINGS_WIDTH, DEFAULT_SETTINGS_HEIGHT

    def _content_layout(self):
        return self.PAD, max(1, self.width - self.PAD * 2)

    def _layout(self):
        self._render_background()
        self.close_button.place(x=self.width - 42, y=14)
        self.size_slider.layout()
        self.opacity_slider.layout()
        self.grip.place(x=self.width - self.GRIP - 5, y=self.height - self.GRIP - 4)
        self._draw_grip()

    def _draw_grip(self):
        self.grip.delete("all")
        for offset in (4, 8, 12):
            self.grip.create_line(
                offset,
                self.GRIP - 1,
                self.GRIP - 1,
                offset,
                fill=TEXT_MUTED,
                width=1,
            )

    def _render_background(self):
        image = rounded_card(
            self.width,
            self.height,
            radius=20,
            fill=(36, 36, 36, 255),
            outline=(255, 255, 255, 18),
        )
        self.photo = keyed_photo(image)
        self.canvas.itemconfigure(self.background_item, image=self.photo)

    def _on_configure(self, event):
        if event.widget is not self.window:
            return
        width = max(self.MIN_WIDTH, event.width)
        height = max(self.MIN_HEIGHT, event.height)
        if width == self.width and height == self.height:
            return
        self.width = width
        self.height = height
        self._render_background()
        self.close_button.place(x=self.width - 42, y=14)
        self.size_slider.layout()
        self.opacity_slider.layout()
        self.grip.place(x=self.width - self.GRIP - 5, y=self.height - self.GRIP - 4)

    def _resize_press(self, event):
        self.resize_origin = (event.x_root, event.y_root)
        self.resize_start = (self.width, self.height)

    def _resize_drag(self, event):
        if not self.resize_origin or not self.resize_start:
            return
        dx = event.x_root - self.resize_origin[0]
        dy = event.y_root - self.resize_origin[1]
        width = clamp(self.resize_start[0] + dx, self.MIN_WIDTH, 720)
        height = clamp(self.resize_start[1] + dy, self.MIN_HEIGHT, 560)
        self.window.geometry(f"{width}x{height}+{self.window.winfo_x()}+{self.window.winfo_y()}")

    def _resize_release(self, _event):
        self.resize_origin = None
        self.resize_start = None
        self._save_settings()

    def _save_settings(self):
        if not self.pet.settings_path:
            return
        try:
            data = {}
            if self.pet.settings_path.exists():
                data = json.loads(self.pet.settings_path.read_text("utf-8"))
            data["settingsWidth"] = self.width
            data["settingsHeight"] = self.height
            temp = self.pet.settings_path.with_suffix(".tmp")
            temp.write_text(json.dumps(data), "utf-8")
            temp.replace(self.pet.settings_path)
        except (OSError, ValueError, TypeError):
            pass

    def close(self):
        if getattr(self.pet, "settings_window", None) is self:
            self.pet.settings_window = None
        self._save_settings()
        self.pet._save_settings()
        try:
            self.window.destroy()
        except tk.TclError:
            pass


class PetWindow:
    def __init__(
        self,
        sprite_path: Path,
        state_path: Path,
        position_path,
        settings_path,
    ):
        self.sprite_path = sprite_path
        self.state_path = state_path
        self.position_path = position_path
        self.settings_path = settings_path
        self.last_state = None
        self.task = ""
        self.status = "idle"
        self.row = "idle"
        self.pose = "idle"
        self.gesture_token = 0
        self.gesture_after_job = None
        self.next_click_pose = 0
        self.single_click_job = None
        self.frame = 0
        self.drag_origin = None
        self.window_origin = None
        self.dragged = False
        self.anchor_pid = 0
        self.dsh_pid_path = state_path.with_name("dsh.pid")
        self.hidden_path = state_path.with_name("hidden.flag")
        self.log_path = state_path.with_name("pet-window.log")
        saved_settings = self._load_settings()
        self.size_percent = saved_settings[0]
        self.opacity_percent = saved_settings[1]
        self.menu = None
        self.settings_window = None

        self.sheet = Image.open(sprite_path).convert("RGBA")
        pose_root = sprite_path.parent / "poses"
        self.poses = {}
        for pose_name in POSE_NAMES:
            frames = []
            for frame_index in range(POSE_FRAME_COUNTS[pose_name]):
                pose_path = pose_root / f"{pose_name}_{frame_index}.png"
                if not pose_path.exists():
                    frames = []
                    break
                frames.append(Image.open(pose_path).convert("RGBA"))
            if not frames:
                fallback = pose_root / f"{pose_name}.png"
                if fallback.exists():
                    frames = [Image.open(fallback).convert("RGBA")]
            if frames:
                self.poses[pose_name] = frames
        self.root = tk.Tk()
        self.root.title("Mint Budgie")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT_KEY)
        self.root.attributes("-alpha", self.opacity_percent / 100)
        self.root.configure(bg=TRANSPARENT_KEY)

        width, height = self._window_size()
        self.root.geometry(f"{width}x{height}+0+0")
        self.canvas = tk.Canvas(
            self.root,
            width=width,
            height=height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)
        self.image_item = self.canvas.create_image(
            width // 2,
            self._sprite_top() + self._display_height() // 2,
            anchor="center",
        )
        self.photo = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.root.bind("<Configure>", self._on_configure)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        self.bubble = StatusBubble(self)
        self._render_frame()
        self.root.geometry(self._initial_geometry(width, height))
        self.root.after(120, self._tick_state)
        self.root.after(60, self._tick_animation)

    def _load_settings(self) -> tuple[int, int]:
        if not self.settings_path or not self.settings_path.exists():
            return DEFAULT_SIZE_PERCENT, DEFAULT_OPACITY_PERCENT
        try:
            data = json.loads(self.settings_path.read_text("utf-8"))
            size = round(float(data.get("sizePercent", DEFAULT_SIZE_PERCENT)))
            opacity = round(
                float(data.get("opacityPercent", DEFAULT_OPACITY_PERCENT))
            )
            return (
                clamp(size, MIN_SIZE_PERCENT, MAX_SIZE_PERCENT),
                clamp(opacity, MIN_OPACITY_PERCENT, MAX_OPACITY_PERCENT),
            )
        except (OSError, ValueError, TypeError):
            return DEFAULT_SIZE_PERCENT, DEFAULT_OPACITY_PERCENT

    def _save_settings(self):
        if not self.settings_path:
            return
        try:
            data = {}
            if self.settings_path.exists():
                try:
                    data = json.loads(self.settings_path.read_text("utf-8"))
                except (OSError, ValueError, TypeError):
                    data = {}
            data["sizePercent"] = self.size_percent
            data["opacityPercent"] = self.opacity_percent
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix(".tmp")
            temp.write_text(json.dumps(data), "utf-8")
            temp.replace(self.settings_path)
        except OSError:
            pass

    def _load_position(self):
        if not self.position_path or not self.position_path.exists():
            return None
        try:
            saved = json.loads(self.position_path.read_text("utf-8"))
            if isinstance(saved.get("left"), int) and isinstance(saved.get("top"), int):
                return saved["left"], saved["top"]
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _initial_geometry(self, width: int, height: int) -> str:
        saved = self._load_position()
        left, top = saved or self._default_position(width, height)
        left, top = self._clamp_to_screen(left, top, width, height)
        return f"{width}x{height}+{left}+{top}"

    def _default_position(self, width: int, height: int):
        left, top, right, bottom = self.virtual_desktop()
        return right - width - 24, bottom - height - 72

    @staticmethod
    def virtual_desktop():
        """Return the complete multi-monitor Windows desktop rectangle."""
        if sys.platform != "win32":
            return 0, 0, 1920, 1080
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        return (
            user32.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            user32.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            user32.GetSystemMetrics(76) + user32.GetSystemMetrics(78),
            user32.GetSystemMetrics(77) + user32.GetSystemMetrics(79),
        )

    def _clamp_to_screen(self, left: int, top: int, width: int, height: int):
        desktop_left, desktop_top, desktop_right, desktop_bottom = (
            self.virtual_desktop()
        )
        left = max(
            desktop_left,
            min(left, max(desktop_left, desktop_right - width)),
        )
        top = max(
            desktop_top,
            min(top, max(desktop_top, desktop_bottom - height)),
        )
        return left, top

    def _display_width(self) -> int:
        return round(CELL_W * DEFAULT_SCALE * self.size_percent / 100)

    def _display_height(self) -> int:
        return round(CELL_H * DEFAULT_SCALE * self.size_percent / 100)

    def _window_size(self):
        # Reserve the full 192x208 cell so wide head-tilt and wing frames never
        # clip at the top or sides while the pet body stays on one baseline.
        margin = 8
        return self._display_width() + margin * 2, self._display_height() + margin * 2

    @staticmethod
    def _sprite_top() -> int:
        return 8

    def _scaled_running_jump(self, cell: Image.Image) -> Image.Image:
        """Keep the work bob, but reduce its vertical travel to 40%."""
        if self.row != "running":
            return cell
        bbox = cell.getchannel("A").getbbox()
        if not bbox:
            return cell
        _, _, _, bottom = bbox
        target_bottom = round(194 - (194 - bottom) * RUNNING_JUMP_SCALE)
        shift = target_bottom - bottom
        if shift <= 0:
            return cell
        reduced = Image.new("RGBA", cell.size, (0, 0, 0, 0))
        reduced.alpha_composite(cell, (0, shift))
        return reduced

    def set_size_percent(self, percent: int):
        percent = clamp(round(percent), MIN_SIZE_PERCENT, MAX_SIZE_PERCENT)
        if percent == self.size_percent:
            return
        old_w = max(1, self.root.winfo_width())
        old_h = max(1, self.root.winfo_height())
        old_x = self.root.winfo_x()
        old_y = self.root.winfo_y()
        center_x = old_x + old_w // 2
        bottom = old_y + old_h

        self.size_percent = percent
        width, height = self._window_size()
        left = round(center_x - width / 2)
        top = bottom - height
        left, top = self._clamp_to_screen(left, top, width, height)
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.canvas.configure(width=width, height=height)
        self._render_frame()
        self.root.after_idle(self.bubble.place)
        self._save_settings()

    def set_opacity_percent(self, percent: int):
        percent = clamp(
            round(percent),
            MIN_OPACITY_PERCENT,
            MAX_OPACITY_PERCENT,
        )
        if percent == self.opacity_percent:
            return
        self.opacity_percent = percent
        alpha = percent / 100
        self.root.attributes("-alpha", alpha)
        self.bubble.window.attributes("-alpha", BUBBLE_OPACITY * alpha)
        if self.menu is not None:
            try:
                self.menu.window.attributes("-alpha", 0.96 * alpha)
            except tk.TclError:
                pass
        if self.settings_window is not None:
            try:
                self.settings_window.window.attributes("-alpha", alpha)
            except tk.TclError:
                pass
        self._save_settings()

    def _on_press(self, event):
        self._log(
            f"pet press x={event.x_root} y={event.y_root} "
            f"status={self.status} pose={self.pose} frame={self.frame}"
        )
        if self.menu is not None:
            self.menu.close()
        self.drag_origin = (event.x_root, event.y_root)
        self.window_origin = (self.root.winfo_x(), self.root.winfo_y())
        self.dragged = False

    def _on_drag(self, event):
        if not self.drag_origin or not self.window_origin:
            return
        dx = event.x_root - self.drag_origin[0]
        dy = event.y_root - self.drag_origin[1]
        if abs(dx) >= 4 or abs(dy) >= 4:
            self.dragged = True
        width, height = self._window_size()
        left, top = self._clamp_to_screen(
            self.window_origin[0] + dx,
            self.window_origin[1] + dy,
            width,
            height,
        )
        self.root.geometry(f"+{left}+{top}")

    def _on_release(self, _event):
        self.drag_origin = None
        self.window_origin = None
        self._log(
            f"pet release dragged={self.dragged} status={self.status} "
            f"pose={self.pose} frame={self.frame}"
        )
        if not self.dragged:
            self._schedule_single_click()
        elif self.position_path:
            payload = {"left": self.root.winfo_x(), "top": self.root.winfo_y()}
            try:
                self.position_path.write_text(json.dumps(payload), "utf-8")
            except OSError:
                pass

    def _schedule_single_click(self):
        self._cancel_single_click()
        # Delay the single-click gesture so a recognized double-click can
        # replace it cleanly instead of briefly starting another pose.
        self.single_click_job = self.root.after(260, self._run_single_click)

    def _run_single_click(self):
        self.single_click_job = None
        pose = self._next_click_gesture()
        self._log(f"single-click gesture pose={pose}")
        self._start_gesture(pose)

    def _next_click_gesture(self):
        pose = CLICK_POSES[self.next_click_pose]
        self.next_click_pose = (self.next_click_pose + 1) % len(CLICK_POSES)
        return pose

    def _cancel_single_click(self):
        if self.single_click_job is None:
            return
        try:
            self.root.after_cancel(self.single_click_job)
        except tk.TclError:
            pass
        self.single_click_job = None

    def _start_gesture(self, pose: str):
        if pose not in GESTURE_POSES or pose not in self.poses:
            self._log(f"gesture skipped pose={pose}: pose unavailable")
            return
        self._cancel_gesture_timer()
        self.pose = pose
        self.gesture_token += 1
        token = self.gesture_token
        self.frame = 0
        self._log(
            f"gesture start pose={self.pose} frame={self.frame} "
            f"frames={len(self.poses[self.pose])} token={token}"
        )
        self._render_frame()
        self.gesture_after_job = self.root.after(
            self._gesture_frame_delay(self.pose, self.frame),
            lambda: self._advance_gesture(token),
        )

    def _advance_gesture(self, token=None):
        if token is not None and token != self.gesture_token:
            return
        if self.pose not in GESTURE_POSES or self.pose not in self.poses:
            return
        self.frame += 1
        if self.frame >= len(self.poses[self.pose]):
            self._finish_gesture()
            return
        self._render_frame()
        self.gesture_after_job = self.root.after(
            self._gesture_frame_delay(self.pose, self.frame),
            lambda: self._advance_gesture(token),
        )

    def _gesture_frame_delay(self, pose: str, frame: int) -> int:
        frames = self.poses.get(pose, ())
        if frame <= 0 or frame >= len(frames) - 1:
            return STAND_FRAME_MS
        return POSE_FRAME_MS.get(pose, 240)

    def _finish_gesture(self):
        self._cancel_gesture_timer()
        self.gesture_token += 1
        self._log(
            f"gesture finish pose={self.pose} frame={self.frame}"
        )
        self.pose = "idle"
        self.frame = 0
        self._render_frame()

    def _cancel_gesture_timer(self):
        if self.gesture_after_job is None:
            return
        try:
            self.root.after_cancel(self.gesture_after_job)
        except tk.TclError:
            pass
        self.gesture_after_job = None

    def _on_configure(self, event):
        if event.widget is self.root and self.bubble.visible:
            self.bubble.place()

    def _on_double_click(self, _event):
        if self.dragged:
            return "break"
        self._cancel_single_click()
        pose = self._next_click_gesture()
        self._log(f"double-click gesture pose={pose}")
        self.dragged = True
        self.bubble.restore()
        self._open_dsh()
        self._start_gesture(pose)
        return "break"

    def _on_right_click(self, event):
        if self.menu is not None:
            self.menu.close()
        self.menu = ContextMenu(self, event.x_root, event.y_root)
        return "break"

    def open_settings(self):
        if self.settings_window is not None:
            try:
                self.settings_window.window.lift()
                self.settings_window.window.focus_force()
            except tk.TclError:
                self.settings_window = None
            if self.settings_window is not None:
                return
        self.settings_window = SettingsWindow(self)

    def _dsh_pid(self) -> int:
        try:
            return int(self.dsh_pid_path.read_text("utf-8").strip())
        except (OSError, ValueError):
            return self.anchor_pid

    def _log(self, message: str):
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except OSError:
            pass

    @staticmethod
    def _process_path(pid: int) -> str:
        if pid <= 0:
            return ""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(length)
            ):
                return ""
            return buffer.value
        finally:
            kernel32.CloseHandle(handle)

    def _find_dsh_window(self, preferred_pid: int) -> int:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.EnumWindows.argtypes = [
            ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM),
            wintypes.LPARAM,
        ]
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd, _lparam):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            executable = self._process_path(pid.value)
            title_length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title, title_length + 1)
            executable_matches = executable.lower().endswith("deepseek harness.exe")
            title_matches = "DeepSeek Harness" in title.value
            if not executable_matches and not title_matches:
                return True
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            visible = bool(user32.IsWindowVisible(hwnd))
            score = 0
            if pid.value == preferred_pid:
                score += 50
            if title_matches:
                score += 100
            elif title.value:
                score += 35
            if class_name.value == "Chrome_WidgetWin_1":
                score += 40
            if visible:
                score += 20
            if score >= 40:
                self._window_candidates.append(
                    (score, hwnd, pid.value, title.value)
                )
            return True

        self._window_candidates = []
        user32.EnumWindows(collect, 0)
        if not self._window_candidates:
            return 0
        self._window_candidates.sort(key=lambda item: item[0], reverse=True)
        _score, hwnd, pid, title = self._window_candidates[0]
        self._log(f"dsh window hwnd={hwnd} pid={pid} title={title}")
        try:
            self.dsh_pid_path.write_text(str(pid), "utf-8")
        except OSError:
            pass
        return hwnd

    def _focus_dsh_window(self, hwnd: int) -> bool:
        if not hwnd:
            return False
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.restype = wintypes.BOOL
        user32.SetActiveWindow.argtypes = [wintypes.HWND]
        user32.SetActiveWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.BOOL,
        ]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.FlashWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
        user32.FlashWindow.restype = wintypes.BOOL
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        else:
            user32.ShowWindow(hwnd, 5)
        current_thread = kernel32.GetCurrentThreadId()
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        attached = False
        if target_thread and target_thread != current_thread:
            attached = bool(
                user32.AttachThreadInput(current_thread, target_thread, True)
            )
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetActiveWindow(hwnd)
            focused = bool(user32.SetForegroundWindow(hwnd))
        finally:
            if attached:
                user32.AttachThreadInput(current_thread, target_thread, False)
        if not focused:
            user32.FlashWindow(hwnd, True)
        return True

    def _launch_dsh(self) -> bool:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        program_files = Path(os.environ.get("ProgramFiles", ""))
        candidates = [
            local_app_data / "Programs" / "DeepSeek Harness" / "DeepSeek Harness.exe",
            program_files / "DeepSeek Harness" / "DeepSeek Harness.exe",
        ]
        for executable in candidates:
            if executable.exists():
                try:
                    subprocess.Popen(
                        [str(executable)],
                        cwd=str(executable.parent),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    self._log(f"dsh launched: {executable}")
                    return True
                except OSError as error:
                    self._log(f"dsh launch error: {error}")
        return False

    def _open_dsh(self):
        if sys.platform != "win32":
            return
        self._log("double-click open dsh")
        hwnd = self._find_dsh_window(self._dsh_pid())
        if hwnd:
            self._focus_dsh_window(hwnd)
            return
        if self._launch_dsh():
            self.root.after(450, lambda: self._poll_dsh_focus(0))

    def _poll_dsh_focus(self, attempt: int):
        hwnd = self._find_dsh_window(self._dsh_pid())
        if hwnd:
            self._focus_dsh_window(hwnd)
            return
        if attempt < 20:
            self.root.after(500, lambda: self._poll_dsh_focus(attempt + 1))

    def hide(self):
        try:
            self.hidden_path.write_text("", "utf-8")
        except OSError:
            pass
        if self.menu is not None:
            self.menu.close()
        if self.settings_window is not None:
            self.settings_window.close()
        self.bubble.destroy()
        self.root.destroy()

    def _read_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def _tick_state(self):
        state = self._read_state()
        status = state.get("status")
        task = state.get("task") if isinstance(state.get("task"), str) else ""
        activity = state.get("activity") if isinstance(state.get("activity"), str) else ""
        working = state.get("working") is True
        if (status, task, activity, working) != self.last_state:
            self.last_state = (status, task, activity, working)
            self.task = task.strip()
            if isinstance(status, str):
                self.status = status
                self.row = ROW_FOR_STATUS.get(status, "idle")
                if self.status == "idle" and self.pose not in GESTURE_POSES:
                    self.gesture_token += 1
                    self.pose = "idle"
                    self.frame = 0
            if not working and self.status == "running":
                self.status = "idle"
                self.row = "idle"
                if self.pose not in GESTURE_POSES:
                    self.frame = 0
            visible_status = self.status
            if visible_status == "running" and self.pose not in GESTURE_POSES:
                self.row = "running"
                self.frame = 0
            self.bubble.update(visible_status, self.task, activity)
            self._render_frame()
        self.root.after(120, self._tick_state)

    def _tick_animation(self):
        if self.pose in GESTURE_POSES and self.pose in self.poses:
            # The gesture timer owns the frame while a click animation plays.
            # Do not advance or redraw the work row, or the standing frame would
            # briefly be replaced by an unrelated animation frame at the end.
            delay = 160
        elif self.status != "idle":
            # The supplied running row is nearly indistinguishable from
            # standing. Use the more legible jump cycle while work is active.
            animation_row = "jumping" if self.row == "running" else self.row
            row_index = ROW_INDEX.get(animation_row, 0)
            frames = ROW_FRAMES[row_index]
            self.frame = (self.frame + 1) % frames
            delay = FRAME_MS.get(animation_row, 200)
            self._render_frame()
        elif self.pose == "idle":
            # Standing is static. Repaint only when another state change asks
            # for it instead of running a hidden idle animation in the background.
            delay = 1000
        else:
            delay = 160
        self.root.after(delay, self._tick_animation)

    def _render_frame(self):
        width, height = self._window_size()
        display_w = self._display_width()
        display_h = self._display_height()
        if self.pose in GESTURE_POSES and self.pose in self.poses:
            frames = self.poses[self.pose]
            cell = frames[self.frame % len(frames)]
            cell = cell.resize((display_w, display_h), Image.Resampling.NEAREST)
            composed = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            composed.alpha_composite(
                cell,
                ((width - display_w) // 2, self._sprite_top()),
            )
        elif self.status == "idle" and self.pose == "idle":
            # The pose folders contain edited close-up frames. The top-left
            # sheet cell is the original upright standing frame used by Codex.
            cell = self.sheet.crop((0, 0, CELL_W, CELL_H))
            cell = cell.resize((display_w, display_h), Image.Resampling.NEAREST)
            composed = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            composed.alpha_composite(
                cell,
                ((width - display_w) // 2, self._sprite_top()),
            )
        else:
            animation_row = "jumping" if self.row == "running" else self.row
            row_index = ROW_INDEX.get(animation_row, 0)
            left = self.frame * CELL_W
            top = row_index * CELL_H
            cell = self.sheet.crop((left, top, left + CELL_W, top + CELL_H))
            cell = self._scaled_running_jump(cell)
            cell = cell.resize((display_w, display_h), Image.Resampling.NEAREST)
            composed = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            composed.alpha_composite(
                cell,
                ((width - display_w) // 2, self._sprite_top()),
            )
        self.photo = keyed_photo(composed)
        self.canvas.configure(width=width, height=height)
        self.canvas.coords(
            self.image_item,
            width // 2,
            self._sprite_top() + display_h // 2,
        )
        self.canvas.itemconfigure(self.image_item, image=self.photo)

    def run(self):
        self.root.mainloop()


def watch_parent(pid: int, root: tk.Tk):
    """Close the overlay when the dsh application shell exits."""
    if sys.platform != "win32" or pid <= 0:
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return

    def poll():
        if kernel32.WaitForSingleObject(handle, 0) == 0:
            kernel32.CloseHandle(handle)
            try:
                root.destroy()
            except tk.TclError:
                pass
            return
        root.after(1000, poll)

    root.after(1000, poll)


def main() -> int:
    enable_dpi_awareness()
    parser = argparse.ArgumentParser()
    parser.add_argument("--sprite", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--position", default="")
    parser.add_argument("--settings", default="")
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--anchor-pid", type=int, default=0)
    args = parser.parse_args()

    position_path = Path(args.position) if args.position else None
    settings_path = Path(args.settings) if args.settings else None
    pet = PetWindow(
        Path(args.sprite),
        Path(args.state),
        position_path,
        settings_path,
    )
    pet.anchor_pid = args.anchor_pid or args.parent_pid
    watcher_pid = args.anchor_pid or args.parent_pid
    if watcher_pid > 0:
        watch_parent(watcher_pid, pet.root)
    pet.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
