"""
banner.py
---------
Animated RiffVision banner for the main window header.

Renders entirely with Pillow + tkinter Canvas — no external assets needed.
All graphics are procedurally generated at runtime.

Visual elements (all animated):
  1. Deep navy background with a subtle fretboard grid
  2. Star field — 80 stars at varying brightness, slow parallax drift
  3. Pulsing glow ring behind the logo (sine-wave breathe)
  4. Chromatic aberration logo: "RIFF" (blue) + "VISION" (cyan) with
     layered glow passes rendered into a PIL image each frame
  5. Sweeping laser scan line (electric blue, fades at edges)
  6. Particle spark trail — 30 glowing dots rising from the logo
  7. Subtitle tagline that fades in after 1.5 seconds

Animation runs at ~30 fps via tkinter after() loop.
Designed to be dropped into any CTkFrame as a child widget.
"""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass, field
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BANNER_H = 90          # pixel height of the banner
FPS      = 30          # target frames per second
MS       = 1000 // FPS # milliseconds per frame

# Palette
C_BG          = (10,  14,  26)    # #0a0e1a
C_PANEL       = (15,  21,  37)    # #0f1525
C_BLUE        = (30, 144, 255)    # #1e90ff  electric blue
C_CYAN        = (0,  212, 255)    # #00d4ff  cyan
C_PURPLE      = (123, 94, 167)    # #7b5ea7  purple
C_GLOW        = (77, 184, 255)    # #4db8ff
C_DIM         = (68,  85, 119)    # #445577
C_BORDER      = (30,  45,  77)    # #1e2d4d
C_WHITE       = (232, 240, 254)   # #e8f0fe

# Font paths — tried in order, first found wins
_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

_FONT_SUB_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(candidates: list[str], size: int) -> Optional[ImageFont.FreeTypeFont]:
    import os
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# Particle
# ---------------------------------------------------------------------------

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float      # 0.0 → 1.0, decreases each frame
    decay: float     # amount life drops per frame
    size: float
    color: tuple     # RGB
    phase: float = 0.0   # for wobble


# ---------------------------------------------------------------------------
# BannerCanvas
# ---------------------------------------------------------------------------

class BannerCanvas(tk.Canvas):
    """
    A tk.Canvas that renders the animated RiffVision banner.
    Drop it into any frame — it handles its own animation loop.
    """

    def __init__(self, parent, width: int, height: int = BANNER_H, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg="#0a0e1a",
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.W = width
        self.H = height
        self._running = False
        self._img_id: Optional[int] = None
        self._tk_img = None
        self._start_time = time.time()
        self._frame = 0

        if not _PIL_OK:
            # Fallback: static text
            self.create_text(
                width // 2, height // 2,
                text="RIFFVISION",
                fill="#1e90ff",
                font=("Impact", 32, "bold"),
            )
            return

        # ── Fonts ──────────────────────────────────────────────────────
        self._font_logo  = _load_font(_FONT_CANDIDATES,     52)
        self._font_sub   = _load_font(_FONT_SUB_CANDIDATES, 11)
        if self._font_logo is None:
            self._font_logo = ImageFont.load_default()
        if self._font_sub is None:
            self._font_sub = ImageFont.load_default()

        # ── Stars ──────────────────────────────────────────────────────
        rng = random.Random(42)   # fixed seed → consistent star field
        self._stars = [
            {
                "x": rng.uniform(0, width),
                "y": rng.uniform(0, height),
                "r": rng.uniform(0.5, 1.8),
                "brightness": rng.uniform(0.2, 1.0),
                "drift": rng.uniform(0.02, 0.08),
            }
            for _ in range(80)
        ]

        # ── Particles ──────────────────────────────────────────────────
        self._particles: list[Particle] = []
        self._next_spawn = 0.0

        # ── Fretboard grid: precompute vertical line x positions ───────
        # Evenly spaced like guitar frets, subtle
        self._fret_xs = [int(width * t) for t in [
            0.06, 0.12, 0.17, 0.22, 0.26, 0.30, 0.34, 0.38, 0.41, 0.44,
            0.47, 0.50, 0.53, 0.56, 0.59, 0.62, 0.65, 0.68, 0.71, 0.74,
            0.77, 0.80, 0.83, 0.86, 0.89, 0.92, 0.95,
        ]]
        # Horizontal string lines (5 strings)
        self._string_ys = [int(height * t) for t in [0.15, 0.30, 0.50, 0.70, 0.85]]

        # ── Logo text metrics ──────────────────────────────────────────
        # Pre-measure so we can center properly
        _probe = Image.new("RGB", (10, 10))
        _d = ImageDraw.Draw(_probe)
        try:
            bb_riff   = _d.textbbox((0, 0), "RIFF",   font=self._font_logo)
            bb_vision = _d.textbbox((0, 0), "VISION", font=self._font_logo)
            self._riff_w   = bb_riff[2]   - bb_riff[0]
            self._vision_w = bb_vision[2] - bb_vision[0]
            self._logo_h   = bb_riff[3]   - bb_riff[1]
        except AttributeError:
            # Older Pillow
            self._riff_w,   _ = _d.textsize("RIFF",   font=self._font_logo)
            self._vision_w, _ = _d.textsize("VISION", font=self._font_logo)
            _, self._logo_h   = _d.textsize("RIFF",   font=self._font_logo)

        self._logo_total_w = self._riff_w + self._vision_w
        self._logo_x = (width - self._logo_total_w) // 2
        self._logo_y = (height - self._logo_h) // 2 - 2

        # Bind resize
        self.bind("<Configure>", self._on_resize)

        # Start loop
        self._running = True
        self.after(100, self._tick)  # short delay so window is mapped

    # ------------------------------------------------------------------
    # Animation loop
    # ------------------------------------------------------------------

    def _tick(self):
        if not self._running:
            return
        t = time.time() - self._start_time
        self._render_frame(t)
        self._frame += 1
        self.after(MS, self._tick)

    def stop(self):
        self._running = False

    def _on_resize(self, event):
        self.W = event.width
        self._logo_x = (self.W - self._logo_total_w) // 2

    # ------------------------------------------------------------------
    # Frame rendering
    # ------------------------------------------------------------------

    def _render_frame(self, t: float):
        W, H = self.W, self.H
        img = Image.new("RGB", (W, H), C_BG)
        draw = ImageDraw.Draw(img, "RGBA")

        self._draw_fretboard(draw, W, H, t)
        self._draw_stars(draw, W, H, t)
        self._update_particles(t)
        self._draw_particles(draw, t)
        self._draw_glow_ring(img, draw, W, H, t)
        self._draw_laser(draw, W, H, t)
        self._draw_logo(img, draw, W, H, t)
        self._draw_tagline(draw, W, H, t)
        self._draw_border_lines(draw, W, H)

        # Convert to PhotoImage and display
        from PIL import ImageTk
        tk_img = ImageTk.PhotoImage(img)
        self._tk_img = tk_img   # hold reference

        if self._img_id is None:
            self._img_id = self.create_image(0, 0, anchor="nw", image=tk_img)
        else:
            self.itemconfig(self._img_id, image=tk_img)

    # ------------------------------------------------------------------
    # Drawing sub-routines
    # ------------------------------------------------------------------

    def _draw_fretboard(self, draw: ImageDraw.Draw, W: int, H: int, t: float):
        """Faint guitar neck grid in the background."""
        alpha = 18   # very subtle
        # Vertical fret lines
        for x in self._fret_xs:
            draw.line([(x, 0), (x, H)], fill=(*C_BORDER, alpha), width=1)
        # Horizontal string lines
        for y in self._string_ys:
            draw.line([(0, y), (W, y)], fill=(*C_BORDER, alpha + 6), width=1)

    def _draw_stars(self, draw: ImageDraw.Draw, W: int, H: int, t: float):
        """Slowly drifting star field."""
        for s in self._stars:
            # Drift right slowly, wrap around
            x = (s["x"] + t * s["drift"] * 10) % W
            y = s["y"]
            # Twinkle
            twinkle = 0.6 + 0.4 * math.sin(t * 2.3 + s["x"])
            brightness = int(s["brightness"] * twinkle * 180)
            r = s["r"]
            x0, y0, x1, y1 = x - r, y - r, x + r, y + r
            draw.ellipse([x0, y0, x1, y1],
                         fill=(brightness, brightness, min(255, brightness + 40)))

    def _draw_glow_ring(self, img: Image.Image, draw: ImageDraw.Draw,
                         W: int, H: int, t: float):
        """Pulsing elliptical glow behind the logo."""
        pulse = 0.55 + 0.45 * math.sin(t * 1.8)
        cx = W // 2
        cy = H // 2

        rx = int((self._logo_total_w // 2 + 60) * (0.9 + 0.1 * pulse))
        ry = int((H // 2 + 16) * (0.9 + 0.1 * pulse))

        # Draw multiple concentric ellipses to simulate glow falloff
        layers = [
            (rx + 30, ry + 12, int(pulse * 22),  C_BLUE),
            (rx + 15, ry + 6,  int(pulse * 35),  C_BLUE),
            (rx,      ry,      int(pulse * 50),  C_CYAN),
            (rx - 10, ry - 4,  int(pulse * 28),  C_PURPLE),
        ]
        glow_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)

        for erx, ery, alpha, color in layers:
            glow_draw.ellipse(
                [cx - erx, cy - ery, cx + erx, cy + ery],
                fill=(*color, alpha),
            )

        blurred = glow_img.filter(ImageFilter.GaussianBlur(radius=14))
        img.paste(blurred, (0, 0), blurred)

    def _draw_laser(self, draw: ImageDraw.Draw, W: int, H: int, t: float):
        """Horizontal laser scan line sweeping left to right, looping every 3s."""
        period = 3.0
        phase = (t % period) / period   # 0→1
        x = int(phase * (W + 80)) - 40

        # Gradient fade at edges using multiple vertical lines
        for dx, alpha in [(-8, 8), (-5, 18), (-2, 35), (0, 70), (2, 35), (5, 18), (8, 8)]:
            lx = x + dx
            if 0 <= lx <= W:
                draw.line([(lx, 0), (lx, H)], fill=(*C_BLUE, alpha), width=1)

        # Bright center line
        if 0 <= x <= W:
            draw.line([(x, 0), (x, H)], fill=(*C_CYAN, 90), width=2)

    def _update_particles(self, t: float):
        """Spawn and age spark particles rising from near the logo."""
        # Remove dead particles
        self._particles = [p for p in self._particles if p.life > 0]

        # Spawn new particles periodically
        if t >= self._next_spawn:
            self._next_spawn = t + random.uniform(0.04, 0.12)
            # Spawn from random point along the logo text
            lx = self._logo_x + random.randint(0, self._logo_total_w)
            ly = self._logo_y + self._logo_h

            # Alternate blue/cyan/purple
            color = random.choice([C_BLUE, C_CYAN, C_PURPLE, C_GLOW])

            self._particles.append(Particle(
                x=lx,
                y=ly,
                vx=random.uniform(-0.6, 0.6),
                vy=random.uniform(-1.4, -0.4),
                life=1.0,
                decay=random.uniform(0.015, 0.035),
                size=random.uniform(1.2, 2.8),
                color=color,
                phase=random.uniform(0, math.tau),
            ))

        for p in self._particles:
            p.x += p.vx + 0.3 * math.sin(t * 3 + p.phase)
            p.y += p.vy
            p.vy *= 0.98   # slight drag
            p.life -= p.decay

    def _draw_particles(self, draw: ImageDraw.Draw, t: float):
        for p in self._particles:
            alpha = int(p.life * 200)
            r = p.size * p.life
            x0, y0, x1, y1 = p.x - r, p.y - r, p.x + r, p.y + r
            draw.ellipse([x0, y0, x1, y1], fill=(*p.color, alpha))

    def _draw_logo(self, img: Image.Image, draw: ImageDraw.Draw,
                    W: int, H: int, t: float):
        """
        Multi-pass logo rendering:
          1. Blurred glow layers (blue, cyan) rendered to a temp image
          2. Chromatic aberration: blue slightly left, cyan slightly right
          3. Sharp white core text on top
        """
        lx = self._logo_x
        ly = self._logo_y
        pulse = 0.7 + 0.3 * math.sin(t * 2.1)

        # ── Glow passes ───────────────────────────────────────────────
        glow_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_img)

        # Blue glow (RIFF) — offset left by 3px for chroma effect
        gd.text((lx - 3, ly + 1), "RIFF",   font=self._font_logo,
                fill=(*C_BLUE, int(160 * pulse)))
        # Cyan glow (VISION) — offset right by 3px
        gd.text((lx + self._riff_w + 3, ly + 1), "VISION", font=self._font_logo,
                fill=(*C_CYAN, int(140 * pulse)))

        blurred = glow_img.filter(ImageFilter.GaussianBlur(radius=5))
        img.paste(blurred, (0, 0), blurred)

        # Wider outer glow
        glow2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd2 = ImageDraw.Draw(glow2)
        gd2.text((lx, ly), "RIFF",   font=self._font_logo,
                 fill=(*C_BLUE, int(60 * pulse)))
        gd2.text((lx + self._riff_w, ly), "VISION", font=self._font_logo,
                 fill=(*C_CYAN, int(55 * pulse)))
        blurred2 = glow2.filter(ImageFilter.GaussianBlur(radius=10))
        img.paste(blurred2, (0, 0), blurred2)

        # ── Sharp core text ───────────────────────────────────────────
        draw.text((lx, ly),                      "RIFF",   font=self._font_logo,
                  fill=(*C_BLUE,  240))
        draw.text((lx + self._riff_w, ly),       "VISION", font=self._font_logo,
                  fill=(*C_CYAN,  240))

        # White highlight pass (top-left 1px offset for depth)
        draw.text((lx - 1, ly - 1),              "RIFF",   font=self._font_logo,
                  fill=(*C_WHITE, 45))
        draw.text((lx + self._riff_w - 1, ly - 1), "VISION", font=self._font_logo,
                  fill=(*C_WHITE, 35))

    def _draw_tagline(self, draw: ImageDraw.Draw, W: int, H: int, t: float):
        """Fade-in tagline below the logo."""
        fade_start = 1.5
        fade_dur   = 1.2
        alpha_f = min(1.0, max(0.0, (t - fade_start) / fade_dur))
        alpha   = int(alpha_f * 160)
        if alpha <= 0:
            return

        text = "Clone Hero  ·  Video Manager"
        try:
            bb = draw.textbbox((0, 0), text, font=self._font_sub)
            tw = bb[2] - bb[0]
        except AttributeError:
            tw, _ = draw.textsize(text, font=self._font_sub)

        tx = (W - tw) // 2
        ty = self._logo_y + self._logo_h + 4

        # Subtle glow
        draw.text((tx, ty + 1), text, font=self._font_sub,
                  fill=(*C_BLUE, alpha // 3))
        draw.text((tx, ty), text, font=self._font_sub,
                  fill=(*C_DIM, alpha))

    def _draw_border_lines(self, draw: ImageDraw.Draw, W: int, H: int):
        """Top and bottom 1px border lines."""
        draw.line([(0, 0), (W, 0)],       fill=(*C_BLUE,   180), width=3)
        draw.line([(0, H - 1), (W, H - 1)], fill=(*C_BORDER, 255), width=1)
