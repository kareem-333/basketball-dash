"""
nba/court_svg.py — NBA court SVG generator (brief v5, Section 10).

Produces two variants:
  court_svg_desktop()  →  94 × 50 viewBox (horizontal, landscape)
  court_svg_mobile()   →  50 × 94 viewBox (vertical, portrait, rotated 90°)

Geometry follows real NBA specs scaled to the viewBox:
  - Court: 94 ft × 50 ft  →  viewBox 94 × 50 (1 unit = 1 ft)
  - Paint: 16 ft wide × 19 ft deep (centered on each baseline)
  - Free throw line: 19 ft from baseline
  - Free throw circle: 12 ft diameter, centered on FT line
      dashed half (inside paint) / solid half (outside paint)
  - Three-point arc: 23.75 ft radius, with 14 ft straight corner segments
      at y = 3 and y = 47 (3 ft from each sideline)
  - Restricted area: 4 ft radius half-circle in front of basket
  - Basket: small circle at x=4.75 (left) / x=89.25 (right), y=25
  - Center line at x=47, center circle r=6, inner circle r=3
  - All measurements in feet = SVG units

Color: #EB6E1F  Opacity: 75%  Stroke-width: 2
"""

from __future__ import annotations

CORAL   = "#EB6E1F"
OPACITY = "0.75"
SW      = "2"        # main stroke width
SW_THIN = "1.5"     # thin lines (restricted area, inner circle)

# ── Court constants (feet / SVG units) ───────────────────────────────────────
W, H      = 94, 50         # court width, height
MX        = W / 2          # midcourt x = 47
MY        = H / 2          # midcourt y = 25

# Paint
PAINT_DEPTH = 19           # ft from baseline
PAINT_WIDTH = 16           # ft (8 each side of center y)
PAINT_Y1    = MY - PAINT_WIDTH / 2   # 17
PAINT_Y2    = MY + PAINT_WIDTH / 2   # 33

# Basket
BASKET_X    = 4.75         # ft from baseline (left basket)
BASKET_R    = 0.75         # display radius

# FT circle
FT_CIRCLE_R = 6            # ft (12 ft diameter)
FT_X        = PAINT_DEPTH  # x of free throw line (19 ft)

# 3-point arc
ARC_R       = 23.75        # ft radius from basket center
ARC_CORNER_Y1 = 3.0        # ft from top sideline (y=0)
ARC_CORNER_Y2 = H - 3.0   # ft from bottom sideline
CORNER_LEN  = 14.0         # length of straight corner segment (from baseline)

# Restricted area
RA_R        = 4.0

# Center circle
CC_R        = 6
CC_R_INNER  = 3


# ── SVG helpers ───────────────────────────────────────────────────────────────

def _line(x1, y1, x2, y2, **kw) -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" {extra}/>'


def _rect(x, y, w, h, **kw) -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {extra}/>'


def _circle(cx, cy, r, **kw) -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" {extra}/>'


def _path(d, **kw) -> str:
    extra = " ".join(f'{k}="{v}"' for k, v in kw.items())
    return f'<path d="{d}" {extra}/>'


def _base_style(**extra_kw) -> dict:
    return {
        "fill":           "none",
        "stroke":         CORAL,
        "stroke-width":   SW,
        "stroke-linecap": "round",
        **extra_kw,
    }


def _kw(**kw) -> str:
    return " ".join(f'{k}="{v}"' for k, v in kw.items())


# ── Half-court geometry builders ─────────────────────────────────────────────

def _half_court_elements(
    flip: bool = False,    # True = right half (mirror x)
    vw: float = W,
    vh: float = H,
    scale: float = 1.0,    # for mobile (rotated) version
) -> list[str]:
    """
    Return SVG element strings for one half of a horizontal court.
    flip=False → left half (basket at x=BASKET_X)
    flip=True  → right half (basket at x=VW-BASKET_X), mirrored
    """
    els: list[str] = []
    s = _base_style()

    bx = BASKET_X if not flip else vw - BASKET_X
    # Direction factor: +1 goes toward midcourt from left, -1 from right
    d  = +1 if not flip else -1

    ft_x  = BASKET_X + PAINT_DEPTH if not flip else (vw - BASKET_X) - PAINT_DEPTH

    # ── Paint rectangle ───────────────────────────────────────────────────
    px = 0 if not flip else vw - PAINT_DEPTH
    els.append(_rect(px, PAINT_Y1, PAINT_DEPTH, PAINT_WIDTH, **s))

    # ── Free throw line (already the top edge of paint, but draw explicitly) ─
    els.append(_line(ft_x, PAINT_Y1, ft_x, PAINT_Y2, **s))

    # ── Free throw circle ─────────────────────────────────────────────────
    # Solid half: outside the paint (toward midcourt)
    # Left half:  right semicircle of circle centered at (ft_x, MY)
    # Path: top point (ft_x, MY-6) → clockwise → bottom point (ft_x, MY+6) [rightward]
    if not flip:
        # Solid (right/midcourt half)
        d_solid = (
            f"M {ft_x},{MY - FT_CIRCLE_R} "
            f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 1 {ft_x},{MY + FT_CIRCLE_R}"
        )
        # Dashed (left/paint half)
        d_dashed = (
            f"M {ft_x},{MY - FT_CIRCLE_R} "
            f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 0 {ft_x},{MY + FT_CIRCLE_R}"
        )
    else:
        # Right half: solid is leftward (toward midcourt = decreasing x)
        d_solid = (
            f"M {ft_x},{MY + FT_CIRCLE_R} "
            f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 1 {ft_x},{MY - FT_CIRCLE_R}"
        )
        d_dashed = (
            f"M {ft_x},{MY + FT_CIRCLE_R} "
            f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 0 {ft_x},{MY - FT_CIRCLE_R}"
        )

    els.append(_path(d_solid,  fill="none", stroke=CORAL, **{"stroke-width": SW}))
    els.append(_path(d_dashed, fill="none", stroke=CORAL,
                     **{"stroke-width": SW, "stroke-dasharray": "3 3"}))

    # ── Three-point arc ───────────────────────────────────────────────────
    # Corner straight segments: from baseline for CORNER_LEN ft
    # Left half: from (0, ARC_CORNER_Y1) to (CORNER_LEN, ARC_CORNER_Y1)
    if not flip:
        cx1, cy1 = 0,  ARC_CORNER_Y1
        cx2, cy2 = 0,  ARC_CORNER_Y2
        ce1      = (CORNER_LEN, ARC_CORNER_Y1)
        ce2      = (CORNER_LEN, ARC_CORNER_Y2)
        # Arc: from ce1 → ce2, sweeping clockwise (rightward bulge)
        arc_d = (
            f"M {CORNER_LEN},{ARC_CORNER_Y1} "
            f"A {ARC_R},{ARC_R} 0 0 1 {CORNER_LEN},{ARC_CORNER_Y2}"
        )
    else:
        # Mirror: corner lines from right baseline inward
        cx1, cy1 = vw, ARC_CORNER_Y1
        cx2, cy2 = vw, ARC_CORNER_Y2
        ce1      = (vw - CORNER_LEN, ARC_CORNER_Y1)
        ce2      = (vw - CORNER_LEN, ARC_CORNER_Y2)
        arc_d = (
            f"M {vw - CORNER_LEN},{ARC_CORNER_Y2} "
            f"A {ARC_R},{ARC_R} 0 0 1 {vw - CORNER_LEN},{ARC_CORNER_Y1}"
        )

    els.append(_line(cx1, cy1, ce1[0], ce1[1], **s))
    els.append(_line(cx2, cy2, ce2[0], ce2[1], **s))
    els.append(_path(arc_d, fill="none", stroke=CORAL, **{"stroke-width": SW}))

    # ── Restricted area (4 ft radius half-circle) ─────────────────────────
    if not flip:
        ra_d = (
            f"M {bx},{MY - RA_R} "
            f"A {RA_R},{RA_R} 0 0 1 {bx},{MY + RA_R}"
        )
    else:
        ra_d = (
            f"M {bx},{MY + RA_R} "
            f"A {RA_R},{RA_R} 0 0 1 {bx},{MY - RA_R}"
        )
    els.append(_path(ra_d, fill="none", stroke=CORAL,
                     **{"stroke-width": SW_THIN}))

    # ── Basket ────────────────────────────────────────────────────────────
    els.append(_circle(bx, MY, BASKET_R,
                       fill="none", stroke=CORAL, **{"stroke-width": SW_THIN}))

    return els


def _court_outer(vw: float = W, vh: float = H) -> list[str]:
    """Outer rectangle + sidelines."""
    s = _base_style()
    return [_rect(0, 0, vw, vh, **s)]


def _midcourt_elements(vw: float = W, vh: float = H) -> list[str]:
    """Center line, center circle, inner circle."""
    s  = _base_style()
    st = _base_style(**{"stroke-width": SW_THIN})
    mx = vw / 2
    my = vh / 2
    return [
        _line(mx, 0, mx, vh, **s),
        _circle(mx, my, CC_R,       **s),
        _circle(mx, my, CC_R_INNER, **st),
    ]


# ── Public API ────────────────────────────────────────────────────────────────

def court_svg_desktop(
    width_px: int = 940,
    card_slots: dict | None = None,
) -> str:
    """
    Return SVG markup for a horizontal (landscape) basketball court.
    viewBox="0 0 94 50" with 75% opacity coral lines.
    `card_slots` is unused here (cards are positioned via CSS, not SVG).
    """
    vw, vh = W, H
    els: list[str] = []
    els += _court_outer(vw, vh)
    els += _half_court_elements(flip=False, vw=vw, vh=vh)
    els += _half_court_elements(flip=True,  vw=vw, vh=vh)
    els += _midcourt_elements(vw, vh)

    inner = "\n  ".join(els)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vw} {vh}" '
        f'style="width:100%;height:100%;opacity:{OPACITY};" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'\n  {inner}\n</svg>'
    )


def court_svg_mobile() -> str:
    """
    Return SVG markup for a vertical (portrait) basketball court.
    viewBox="0 0 50 94" — court rotated 90°; center line is now horizontal.
    Each half stacks vertically (top = home, bottom = away).
    """
    # For portrait we swap dimensions and rotate geometry.
    # viewBox is 50 wide × 94 tall.
    # We redraw with X↔Y swapped:
    #   x_desktop → y_portrait
    #   y_desktop → x_portrait
    # All measurements remain the same in feet.

    vw, vh = H, W          # 50 × 94

    def _r(x, y):
        """Rotate desktop (x,y) to portrait (x',y') = (y, x)."""
        return y, x

    els: list[str] = []
    s  = _base_style()
    st = _base_style(**{"stroke-width": SW_THIN})

    # Outer rectangle
    els.append(_rect(0, 0, vw, vh, **s))

    # For each half: top half = y in [0, 47], bottom half = y in [47, 94]
    # In portrait orientation the "baseline" is the top edge (y=0) for home
    # and bottom edge (y=94) for away.  We generate elements per half:

    def _port_half(flip: bool) -> list[str]:
        """
        flip=False → top half (basket near y=0)
        flip=True  → bottom half (basket near y=94)
        """
        pes: list[str] = []
        # Midpoint of the court in portrait x-direction = 25
        pmx = vw / 2   # 25

        bx_port = BASKET_X if not flip else vh - BASKET_X  # y in portrait
        ft_y_port = PAINT_DEPTH if not flip else vh - PAINT_DEPTH

        # Paint rect (portrait): width=PAINT_WIDTH, height=PAINT_DEPTH
        py1 = pmx - PAINT_WIDTH / 2   # x start of paint = 9
        if not flip:
            pes.append(_rect(py1, 0, PAINT_WIDTH, PAINT_DEPTH, **s))
        else:
            pes.append(_rect(py1, vh - PAINT_DEPTH, PAINT_WIDTH, PAINT_DEPTH, **s))

        # Free throw line (horizontal in portrait)
        pes.append(_line(py1, ft_y_port, py1 + PAINT_WIDTH, ft_y_port, **s))

        # FT circle (centered at (pmx, ft_y_port))
        if not flip:
            d_solid = (
                f"M {pmx - FT_CIRCLE_R},{ft_y_port} "
                f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 0 {pmx + FT_CIRCLE_R},{ft_y_port}"
            )
            d_dashed = (
                f"M {pmx - FT_CIRCLE_R},{ft_y_port} "
                f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 1 {pmx + FT_CIRCLE_R},{ft_y_port}"
            )
        else:
            d_solid = (
                f"M {pmx + FT_CIRCLE_R},{ft_y_port} "
                f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 0 {pmx - FT_CIRCLE_R},{ft_y_port}"
            )
            d_dashed = (
                f"M {pmx + FT_CIRCLE_R},{ft_y_port} "
                f"A {FT_CIRCLE_R},{FT_CIRCLE_R} 0 0 1 {pmx - FT_CIRCLE_R},{ft_y_port}"
            )

        pes.append(_path(d_solid,  fill="none", stroke=CORAL, **{"stroke-width": SW}))
        pes.append(_path(d_dashed, fill="none", stroke=CORAL,
                         **{"stroke-width": SW, "stroke-dasharray": "3 3"}))

        # 3-point arc (portrait): corners are at x=3 and x=47 (3 ft from each sideline)
        cx_1 = ARC_CORNER_Y1   # 3
        cx_2 = vw - ARC_CORNER_Y1  # 47
        if not flip:
            # Corner lines from y=0 downward for CORNER_LEN
            pes.append(_line(cx_1, 0, cx_1, CORNER_LEN, **s))
            pes.append(_line(cx_2, 0, cx_2, CORNER_LEN, **s))
            # Arc from (cx_1, CORNER_LEN) → (cx_2, CORNER_LEN) bulging downward
            arc_d = (
                f"M {cx_1},{CORNER_LEN} "
                f"A {ARC_R},{ARC_R} 0 0 0 {cx_2},{CORNER_LEN}"
            )
        else:
            pes.append(_line(cx_1, vh, cx_1, vh - CORNER_LEN, **s))
            pes.append(_line(cx_2, vh, cx_2, vh - CORNER_LEN, **s))
            arc_d = (
                f"M {cx_2},{vh - CORNER_LEN} "
                f"A {ARC_R},{ARC_R} 0 0 0 {cx_1},{vh - CORNER_LEN}"
            )
        pes.append(_path(arc_d, fill="none", stroke=CORAL, **{"stroke-width": SW}))

        # Restricted area
        if not flip:
            ra_d = (
                f"M {pmx - RA_R},{bx_port} "
                f"A {RA_R},{RA_R} 0 0 0 {pmx + RA_R},{bx_port}"
            )
        else:
            ra_d = (
                f"M {pmx + RA_R},{bx_port} "
                f"A {RA_R},{RA_R} 0 0 0 {pmx - RA_R},{bx_port}"
            )
        pes.append(_path(ra_d, fill="none", stroke=CORAL, **{"stroke-width": SW_THIN}))

        # Basket
        pes.append(_circle(pmx, bx_port, BASKET_R,
                           fill="none", stroke=CORAL, **{"stroke-width": SW_THIN}))

        return pes

    els += _port_half(flip=False)
    els += _port_half(flip=True)

    # Center line (horizontal in portrait) at y=47
    els.append(_line(0, vh / 2, vw, vh / 2, **s))
    # Center circle and inner circle
    els.append(_circle(vw / 2, vh / 2, CC_R,       **s))
    els.append(_circle(vw / 2, vh / 2, CC_R_INNER, **st))

    inner = "\n  ".join(els)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {vw} {vh}" '
        f'style="width:100%;height:100%;opacity:{OPACITY};" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'\n  {inner}\n</svg>'
    )


# ── Card slot coordinates ─────────────────────────────────────────────────────
# These are used by app.py to position player cards in CSS (percent of container).
# Values are (left%, top%) for each slot in the desktop horizontal layout.

DESKTOP_SLOTS: dict[str, dict[str, tuple[float, float]]] = {
    # Home (left half) — positions as % of SVG viewBox (94 × 50)
    "home": {
        "PF": (1.0,   5.0),    # top-left corner, above paint
        "C":  (1.0,  70.0),    # bottom-left corner, below paint
        "SG": (16.0,  5.0),    # upper wing, above 3pt arc
        "SF": (16.0, 70.0),    # lower wing, below 3pt arc
        "PG": (25.5, 40.0),    # arc apex — left edge at ~28% across
    },
    # Away (right half) — mirrored
    "away": {
        "PF": (91.0,  5.0),
        "C":  (91.0, 70.0),
        "SG": (76.0,  5.0),
        "SF": (76.0, 70.0),
        "PG": (66.5, 40.0),    # right edge at ~72% across
    },
}

MOBILE_SLOTS: dict[str, dict[str, tuple[float, float]]] = {
    # Home (top half) — positions as % of 50 × 94 viewBox
    "home": {
        "PF": ( 3.0,  2.0),
        "C":  (70.0,  2.0),
        "SG": ( 3.0, 20.0),
        "SF": (70.0, 20.0),
        "PG": (35.0, 32.0),    # bottom edge at arc apex
    },
    # Away (bottom half) — mirrored vertically
    "away": {
        "PF": ( 3.0, 88.0),
        "C":  (70.0, 88.0),
        "SG": ( 3.0, 72.0),
        "SF": (70.0, 72.0),
        "PG": (35.0, 60.0),
    },
}
