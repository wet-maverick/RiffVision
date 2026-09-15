"""
banner.py
---------
Animated RiffVision banner — aggressive, asymmetric, high energy.

Visual design:
  - Deep space background with dense star field
  - Animated EQ/visualizer bar columns across the full width
  - Logo slammed hard-left with multi-layer glow + chromatic split
  - Electric arc flicker on the right side (random jagged lightning)
  - Particle spark storm rising from the logo
  - Horizontal speed lines sweeping right (motion blur feel)
  - Scanline overlay for a slight CRT / hologram texture
  - Pulsing border: top 4px electric blue glow line
  - ALL elements tied to a shared beat clock so they feel in sync
"""

from __future__ import annotations

import math
import random
import time
import tkinter as tk
from dataclasses import dataclass
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BANNER_H = 100
FPS      = 30
MS       = 1000 // FPS

C_BG      = (8,   11,  22)
C_PANEL   = (13,  19,  35)
C_BLUE    = (30, 144, 255)
C_CYAN    = (0,  212, 255)
C_PURPLE  = (123, 94, 167)
C_MAGENTA = (180,  60, 220)
C_GLOW    = (77,  184, 255)
C_DIM     = (50,   65,  100)
C_BORDER  = (25,   40,   70)
C_WHITE   = (232, 240, 254)
C_ARC     = (160, 220, 255)

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
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

def _load_font(candidates, size):
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
    x: float; y: float
    vx: float; vy: float
    life: float; decay: float
    size: float; color: tuple
    phase: float = 0.0


# ---------------------------------------------------------------------------
# BannerCanvas
# ---------------------------------------------------------------------------

class BannerCanvas(tk.Canvas):
    """Animated banner canvas. Drop into any frame."""

    def __init__(self, parent, width: int, height: int = BANNER_H, **kwargs):
        super().__init__(
            parent, width=width, height=height,
            bg="#08090b", highlightthickness=0, bd=0, **kwargs,
        )
        self.W = width
        self.H = height
        self._running  = False
        self._img_id   = None
        self._tk_img   = None
        self._start    = time.time()
        self._frame    = 0

        if not _PIL_OK:
            self.create_text(width // 2, height // 2, text="RIFFVISION",
                             fill="#1e90ff", font=("Impact", 32, "bold"))
            return

        # Fonts
        self._font_logo = _load_font(_FONT_CANDIDATES, 56)
        self._font_sub  = _load_font(_FONT_SUB_CANDIDATES, 10)
        if self._font_logo is None:
            self._font_logo = ImageFont.load_default()

        # Pre-measure logo
        probe = Image.new("RGB", (10, 10))
        pd    = ImageDraw.Draw(probe)
        try:
            br = pd.textbbox((0, 0), "RIFF",   font=self._font_logo)
            bv = pd.textbbox((0, 0), "VISION", font=self._font_logo)
            self._riff_w   = br[2] - br[0]
            self._vision_w = bv[2] - bv[0]
            self._logo_h   = br[3] - br[1]
        except AttributeError:
            self._riff_w,  _ = pd.textsize("RIFF",   font=self._font_logo)
            self._vision_w, _ = pd.textsize("VISION", font=self._font_logo)
            _, self._logo_h   = pd.textsize("RIFF",   font=self._font_logo)

        self._logo_total_w = self._riff_w + self._vision_w

        # Fixed left margin for logo
        self._logo_x = 28
        self._logo_y = (height - self._logo_h) // 2 - 2

        # Stars — seeded so they're consistent
        rng = random.Random(7)
        self._stars = [
            {"x": rng.uniform(0, width), "y": rng.uniform(0, height),
             "r": rng.uniform(0.4, 1.6), "b": rng.uniform(0.15, 0.9),
             "sp": rng.uniform(0.01, 0.06), "ph": rng.uniform(0, math.tau)}
            for _ in range(120)
        ]

        # EQ bars setup — fill right half of banner
        self._eq_count  = 48
        self._eq_phases = [random.uniform(0, math.tau) for _ in range(self._eq_count)]
        self._eq_speeds = [random.uniform(2.5, 7.0)    for _ in range(self._eq_count)]
        self._eq_amps   = [random.uniform(0.3, 1.0)    for _ in range(self._eq_count)]

        # Particles
        self._particles: list[Particle] = []
        self._next_spawn = 0.0

        # Arc state — jagged lightning on the right edge area
        self._arc_pts: list[tuple] = []
        self._arc_next = 0.0
        self._arc_life = 0.0

        # Speed lines (horizontal streaks)
        rng2 = random.Random(13)
        self._speed_lines = [
            {"y": rng2.uniform(0, height), "speed": rng2.uniform(180, 480),
             "length": rng2.uniform(40, 160), "alpha": rng2.uniform(0.04, 0.14),
             "x": rng2.uniform(0, width)}
            for _ in range(18)
        ]

        self.bind("<Configure>", self._on_resize)
        self._running = True
        self.after(120, self._tick)

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    def _tick(self):
        if not self._running:
            return
        t = time.time() - self._start
        self._render(t)
        self._frame += 1
        self.after(MS, self._tick)

    def stop(self):
        self._running = False

    def _on_resize(self, event):
        self.W = event.width

    # ------------------------------------------------------------------
    # Master render
    # ------------------------------------------------------------------

    def _render(self, t: float):
        W, H = self.W, self.H

        # Beat clock: 120 BPM = 2 beats/sec
        beat = (t * 2.0) % 1.0          # 0→1 per beat
        beat_pulse = math.pow(max(0, 1 - beat * 3), 2)  # sharp attack, fast decay

        img  = Image.new("RGB", (W, H), C_BG)
        draw = ImageDraw.Draw(img, "RGBA")

        self._draw_stars(draw, W, H, t)
        self._draw_speed_lines(draw, W, H, t)
        self._draw_eq_bars(draw, img, W, H, t, beat_pulse)
        self._draw_arc(draw, W, H, t)
        self._update_particles(t)
        self._draw_particles(draw)
        self._draw_logo_glow(img, W, H, t, beat_pulse)
        self._draw_logo_text(draw, W, H, t, beat_pulse)
        self._draw_tagline(draw, W, H, t)
        self._draw_scanlines(draw, W, H)
        self._draw_borders(draw, W, H, t, beat_pulse)

        from PIL import ImageTk
        tk_img = ImageTk.PhotoImage(img)
        self._tk_img = tk_img
        if self._img_id is None:
            self._img_id = self.create_image(0, 0, anchor="nw", image=tk_img)
        else:
            self.itemconfig(self._img_id, image=tk_img)

    # ------------------------------------------------------------------
    # Drawing routines
    # ------------------------------------------------------------------

    def _draw_stars(self, draw, W, H, t):
        for s in self._stars:
            x = (s["x"] + t * s["sp"] * 15) % W
            tw = 0.5 + 0.5 * math.sin(t * 1.8 + s["ph"])
            b  = int(s["b"] * tw * 190)
            r  = s["r"]
            draw.ellipse([x-r, s["y"]-r, x+r, s["y"]+r],
                         fill=(b, b, min(255, b + 50), 255))

    def _draw_speed_lines(self, draw, W, H, t):
        """Fast horizontal streaks — motion blur feel."""
        for sl in self._speed_lines:
            sl["x"] = (sl["x"] + sl["speed"] * (1.0 / FPS)) % (W + sl["length"])
            x0 = sl["x"] - sl["length"]
            x1 = sl["x"]
            y  = sl["y"]
            a  = int(sl["alpha"] * 255)
            # Gradient from transparent to blue — simulate using 3 lines
            draw.line([(x0, y), (x1, y)], fill=(*C_CYAN, a // 3), width=1)
            draw.line([(x0 + sl["length"] * 0.4, y), (x1, y)],
                      fill=(*C_BLUE, a), width=1)

    def _draw_eq_bars(self, draw, img, W, H, t, beat_pulse):
        """
        Visualizer EQ columns across the right 60% of the banner.
        Each bar is a tall column of gradient-colored segments.
        """
        eq_zone_x = int(W * 0.36)   # EQ starts here (gives logo room)
        eq_w      = W - eq_zone_x
        bar_w     = max(2, eq_w // self._eq_count - 1)
        gap       = max(1, (eq_w - bar_w * self._eq_count) // self._eq_count)

        glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd         = ImageDraw.Draw(glow_layer)

        for i in range(self._eq_count):
            # Height driven by multiple sine waves + beat
            h_frac = (
                self._eq_amps[i] * (
                    0.45 * math.sin(t * self._eq_speeds[i] + self._eq_phases[i])
                    + 0.30 * math.sin(t * self._eq_speeds[i] * 1.7 + self._eq_phases[i] * 0.6)
                    + 0.25 * math.sin(t * 1.3 + i * 0.4)
                ) + 0.5 + 0.15 * beat_pulse
            )
            h_frac = max(0.04, min(0.97, h_frac))
            bar_h  = int(h_frac * H * 0.88)

            x0 = eq_zone_x + i * (bar_w + gap)
            x1 = x0 + bar_w
            y0 = H - bar_h
            y1 = H

            # Color gradient: purple at bottom → blue mid → cyan top
            frac_top = h_frac
            if frac_top > 0.75:
                color = C_CYAN
            elif frac_top > 0.45:
                color = C_BLUE
            else:
                color = C_PURPLE

            alpha = int(140 + 80 * h_frac)
            draw.rectangle([x0, y0, x1, y1], fill=(*color, alpha))

            # Top cap — brighter white-hot pixel
            if bar_h > 4:
                draw.rectangle([x0, y0, x1, y0 + 2],
                               fill=(*C_CYAN, min(255, alpha + 80)))

            # Glow around tall bars
            if h_frac > 0.6:
                gd.rectangle([x0 - 1, y0 - 2, x1 + 1, y1],
                              fill=(*color, int(40 * h_frac)))

        blurred = glow_layer.filter(ImageFilter.GaussianBlur(3))
        img.paste(blurred, (0, 0), blurred)

    def _draw_arc(self, draw, W, H, t):
        """
        Jagged electric arc that fires randomly in the right-edge area.
        Simulates an electrical discharge.
        """
        if t >= self._arc_next:
            # Decide whether to fire a new arc
            if random.random() < 0.35:
                # Generate zigzag points from top to bottom on right side
                ax = random.randint(int(W * 0.82), W - 8)
                pts = []
                y = 0
                while y < H:
                    pts.append((ax + random.randint(-12, 12), y))
                    y += random.randint(6, 16)
                pts.append((ax + random.randint(-8, 8), H))
                self._arc_pts  = pts
                self._arc_life = random.uniform(0.06, 0.16)
            self._arc_next = t + random.uniform(0.08, 0.35)

        if self._arc_life > 0 and len(self._arc_pts) > 1:
            alpha = int((self._arc_life / 0.16) * 180)
            # Draw the arc with a glow pass
            for i in range(len(self._arc_pts) - 1):
                p1, p2 = self._arc_pts[i], self._arc_pts[i + 1]
                draw.line([p1, p2], fill=(*C_ARC, alpha // 3), width=4)
                draw.line([p1, p2], fill=(*C_CYAN, alpha),     width=1)
            self._arc_life -= 1.0 / FPS

    def _update_particles(self, t: float):
        self._particles = [p for p in self._particles if p.life > 0]
        if t >= self._next_spawn:
            self._next_spawn = t + random.uniform(0.02, 0.07)
            # Spawn from right edge of logo text
            spawn_x = self._logo_x + self._logo_total_w
            spawn_y = self._logo_y + self._logo_h * random.uniform(0.2, 0.9)
            color = random.choice([C_BLUE, C_CYAN, C_PURPLE, C_MAGENTA, C_GLOW])
            self._particles.append(Particle(
                x=spawn_x + random.uniform(-8, 20),
                y=spawn_y,
                vx=random.uniform(0.2, 1.8),    # drift RIGHT for energy
                vy=random.uniform(-1.8, -0.2),
                life=1.0,
                decay=random.uniform(0.018, 0.040),
                size=random.uniform(1.0, 3.2),
                color=color,
                phase=random.uniform(0, math.tau),
            ))

        for p in self._particles:
            p.x  += p.vx + 0.4 * math.sin(time.time() * 4 + p.phase)
            p.y  += p.vy
            p.vy *= 0.97
            p.life -= p.decay

    def _draw_particles(self, draw):
        for p in self._particles:
            a = int(p.life * 220)
            r = p.size * p.life
            draw.ellipse([p.x - r, p.y - r, p.x + r, p.y + r],
                         fill=(*p.color, a))

    def _draw_logo_glow(self, img, W, H, t, beat_pulse):
        """Multi-pass blurred glow behind logo text."""
        pulse = 0.72 + 0.28 * math.sin(t * 1.9) + 0.12 * beat_pulse
        lx, ly = self._logo_x, self._logo_y

        # Wide outer glow
        g1 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d1 = ImageDraw.Draw(g1)
        d1.text((lx,              ly), "RIFF",   font=self._font_logo,
                fill=(*C_BLUE,   int(55 * pulse)))
        d1.text((lx + self._riff_w, ly), "VISION", font=self._font_logo,
                fill=(*C_CYAN,   int(50 * pulse)))
        img.paste(g1.filter(ImageFilter.GaussianBlur(12)), (0, 0),
                  g1.filter(ImageFilter.GaussianBlur(12)))

        # Tight inner glow with chroma shift
        g2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(g2)
        d2.text((lx - 4, ly + 2), "RIFF",   font=self._font_logo,
                fill=(*C_BLUE,   int(150 * pulse)))
        d2.text((lx + self._riff_w + 4, ly + 2), "VISION", font=self._font_logo,
                fill=(*C_CYAN,   int(130 * pulse)))
        img.paste(g2.filter(ImageFilter.GaussianBlur(5)), (0, 0),
                  g2.filter(ImageFilter.GaussianBlur(5)))

        # Beat flash — extra bright pulse on the beat
        if beat_pulse > 0.4:
            g3 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d3 = ImageDraw.Draw(g3)
            d3.text((lx, ly), "RIFF",              font=self._font_logo,
                    fill=(*C_WHITE, int(80 * beat_pulse)))
            d3.text((lx + self._riff_w, ly), "VISION", font=self._font_logo,
                    fill=(*C_WHITE, int(70 * beat_pulse)))
            img.paste(g3.filter(ImageFilter.GaussianBlur(7)), (0, 0),
                      g3.filter(ImageFilter.GaussianBlur(7)))

    def _draw_logo_text(self, draw, W, H, t, beat_pulse):
        """Sharp logo text with chromatic aberration and white highlight."""
        lx, ly = self._logo_x, self._logo_y

        # Chromatic shadow — blue left, cyan right, slightly offset
        draw.text((lx + 2, ly + 2), "RIFF",              font=self._font_logo,
                  fill=(*C_PURPLE, 90))
        draw.text((lx + self._riff_w + 2, ly + 2), "VISION", font=self._font_logo,
                  fill=(*C_PURPLE, 80))

        # Main sharp text
        draw.text((lx,              ly), "RIFF",   font=self._font_logo,
                  fill=(*C_BLUE,  245))
        draw.text((lx + self._riff_w, ly), "VISION", font=self._font_logo,
                  fill=(*C_CYAN,  245))

        # White top-left highlight for 3D depth
        draw.text((lx - 1, ly - 1), "RIFF",              font=self._font_logo,
                  fill=(*C_WHITE, 55))
        draw.text((lx + self._riff_w - 1, ly - 1), "VISION", font=self._font_logo,
                  fill=(*C_WHITE, 40))

    def _draw_tagline(self, draw, W, H, t):
        if self._font_sub is None:
            return
        fade = min(1.0, max(0.0, (t - 1.2) / 0.8))
        if fade <= 0:
            return
        text = "CLONE HERO  ·  VIDEO MANAGER"
        try:
            bb = draw.textbbox((0, 0), text, font=self._font_sub)
            tw = bb[2] - bb[0]
        except AttributeError:
            tw, _ = draw.textsize(text, font=self._font_sub)

        tx = self._logo_x + 2
        ty = self._logo_y + self._logo_h + 3
        draw.text((tx, ty), text, font=self._font_sub,
                  fill=(*C_GLOW, int(fade * 150)))

    def _draw_scanlines(self, draw, W, H):
        """Subtle horizontal scanline overlay — CRT/hologram feel."""
        for y in range(0, H, 4):
            draw.line([(0, y), (W, y)], fill=(0, 0, 0, 28), width=1)

    def _draw_borders(self, draw, W, H, t, beat_pulse):
        """Pulsing top border + static bottom separator."""
        # Top: thick glow line that pulses blue→cyan on beat
        pulse = 0.6 + 0.4 * math.sin(t * 1.9)
        r = int(C_BLUE[0] * (1 - pulse) + C_CYAN[0] * pulse)
        g = int(C_BLUE[1] * (1 - pulse) + C_CYAN[1] * pulse)
        b = int(C_BLUE[2] * (1 - pulse) + C_CYAN[2] * pulse)
        bright = min(255, int((180 + 75 * beat_pulse)))
        draw.line([(0, 0), (W, 0)], fill=(r, g, b, bright), width=4)
        draw.line([(0, 1), (W, 1)], fill=(r, g, b, bright // 2), width=2)
        # Bottom separator
        draw.line([(0, H - 1), (W, H - 1)], fill=(*C_BORDER, 255), width=1)
