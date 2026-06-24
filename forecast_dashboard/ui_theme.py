"""ui_theme.py — minimalist black & white theming for the dashboard.

The brief asks for a clean, honest, data-dense UI (SCOPE.md §5): restraint over
decoration, uncertainty visually prominent, no "trading terminal" gravitas.

We keep a strictly monochrome palette and offer a few theme variants the user can
switch between live. Each theme provides:
  - CSS variables + overrides injected into the Streamlit page
  - a matching Plotly template (paper/plot bg, font, gridlines)
  - semantic colors for the fan chart (history, samples, median, band)

All themes are grayscale only — color is never used to imply confidence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    bg: str            # page background
    panel: str         # secondary/panel background
    text: str          # primary text
    muted: str         # secondary text
    border: str        # hairlines / borders
    accent: str        # the single emphasis ink (median line, buttons)
    grid: str          # chart gridlines
    band: str          # p10-p90 fill (rgba)
    band_inner: str    # p25-p75 fill (rgba)
    sample: str        # individual sample paths (rgba, faint)
    history: str       # historical price line
    is_dark: bool


# A small set of monochrome themes. Black & white first, by design.
THEMES: dict[str, Theme] = {
    "paper": Theme(
        key="paper", name="Paper (white)",
        bg="#ffffff", panel="#f4f4f4", text="#111111", muted="#666666",
        border="#dddddd", accent="#000000", grid="#ececec",
        band="rgba(0,0,0,0.12)", band_inner="rgba(0,0,0,0.20)",
        sample="rgba(0,0,0,0.06)", history="#111111", is_dark=False,
    ),
    "ink": Theme(
        key="ink", name="Ink (black)",
        bg="#0b0b0b", panel="#161616", text="#f2f2f2", muted="#9a9a9a",
        border="#2a2a2a", accent="#ffffff", grid="#1f1f1f",
        band="rgba(255,255,255,0.12)", band_inner="rgba(255,255,255,0.22)",
        sample="rgba(255,255,255,0.06)", history="#f2f2f2", is_dark=True,
    ),
    "slate": Theme(
        key="slate", name="Slate (dim gray)",
        bg="#15171a", panel="#1d2024", text="#e6e8ea", muted="#8b9197",
        border="#2c3036", accent="#e6e8ea", grid="#23272c",
        band="rgba(230,232,234,0.10)", band_inner="rgba(230,232,234,0.20)",
        sample="rgba(230,232,234,0.06)", history="#e6e8ea", is_dark=True,
    ),
    "e-ink": Theme(
        key="e-ink", name="E-ink (warm white)",
        bg="#f7f5f0", panel="#efece4", text="#1a1a1a", muted="#5f5b53",
        border="#d8d3c8", accent="#1a1a1a", grid="#e4e0d6",
        band="rgba(26,26,26,0.12)", band_inner="rgba(26,26,26,0.20)",
        sample="rgba(26,26,26,0.06)", history="#1a1a1a", is_dark=False,
    ),
    "high-contrast": Theme(
        key="high-contrast", name="High contrast",
        bg="#ffffff", panel="#ffffff", text="#000000", muted="#333333",
        border="#000000", accent="#000000", grid="#bdbdbd",
        band="rgba(0,0,0,0.18)", band_inner="rgba(0,0,0,0.30)",
        sample="rgba(0,0,0,0.10)", history="#000000", is_dark=False,
    ),
}

THEME_ORDER = ["paper", "ink", "slate", "e-ink", "high-contrast"]
DEFAULT_THEME = "paper"


def get_theme(key: str) -> Theme:
    return THEMES.get(key, THEMES[DEFAULT_THEME])


def plotly_template(theme: Theme) -> dict:
    """A minimal Plotly layout template matching the theme (grayscale)."""
    return {
        "layout": {
            "paper_bgcolor": theme.bg,
            "plot_bgcolor": theme.bg,
            "font": {"color": theme.text, "family": "ui-monospace, SFMono-Regular, Menlo, monospace", "size": 12},
            "colorway": [theme.accent, theme.muted, theme.border],
            "xaxis": {
                "gridcolor": theme.grid, "zerolinecolor": theme.grid,
                "linecolor": theme.border, "tickcolor": theme.border,
                "showline": True,
            },
            "yaxis": {
                "gridcolor": theme.grid, "zerolinecolor": theme.grid,
                "linecolor": theme.border, "tickcolor": theme.border,
                "showline": True,
            },
            "legend": {"bgcolor": "rgba(0,0,0,0)", "bordercolor": theme.border},
            "margin": {"l": 50, "r": 20, "t": 30, "b": 40},
            "hoverlabel": {"font": {"family": "ui-monospace, monospace"}},
        }
    }


def css(theme: Theme) -> str:
    """Global CSS overriding Streamlit chrome for a minimalist monochrome look."""
    return f"""
    <style>
    :root {{
        --bg: {theme.bg};
        --panel: {theme.panel};
        --text: {theme.text};
        --muted: {theme.muted};
        --border: {theme.border};
        --accent: {theme.accent};
    }}
    .stApp, [data-testid="stAppViewContainer"] {{
        background: var(--bg);
        color: var(--text);
    }}
    [data-testid="stHeader"] {{ background: transparent; }}
    [data-testid="stSidebar"] {{
        background: var(--panel);
        border-right: 1px solid var(--border);
    }}
    html, body, [class*="css"] {{
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    h1, h2, h3, h4 {{ color: var(--text); letter-spacing: -0.01em; font-weight: 600; }}
    h1 {{ font-size: 1.5rem; }}
    p, li, span, label, div {{ color: var(--text); }}
    .stMarkdown, .stText {{ color: var(--text); }}

    /* Buttons: monochrome, flat */
    .stButton > button {{
        background: var(--accent);
        color: {theme.bg};
        border: 1px solid var(--accent);
        border-radius: 4px;
        font-family: inherit;
        font-weight: 600;
    }}
    .stButton > button:hover {{
        background: var(--bg);
        color: var(--accent);
        border: 1px solid var(--accent);
    }}

    /* Tables */
    [data-testid="stDataFrame"] {{ border: 1px solid var(--border); }}

    /* Metric cards */
    [data-testid="stMetric"] {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 10px 12px;
    }}
    [data-testid="stMetricLabel"] p {{ color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    [data-testid="stMetricValue"] {{ color: var(--text); }}

    /* Honesty badges */
    .badge {{
        display: inline-block;
        padding: 3px 9px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        border: 1px solid var(--border);
        margin: 2px 6px 2px 0;
        font-family: inherit;
    }}
    .badge-warn {{
        background: var(--text);
        color: var(--bg);
        border-color: var(--text);
    }}
    .badge-soft {{
        background: transparent;
        color: var(--muted);
        border: 1px dashed var(--border);
    }}
    .badge-line {{
        background: transparent;
        color: var(--text);
        border: 1px solid var(--text);
    }}

    /* Caveat / blind-spot callout */
    .callout {{
        background: var(--panel);
        border-left: 3px solid var(--accent);
        padding: 10px 14px;
        border-radius: 0 6px 6px 0;
        margin: 8px 0;
        color: var(--text);
    }}
    .callout .small {{ color: var(--muted); font-size: 0.8rem; }}

    /* Compact "at a glance" cards */
    .glance-card {{
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 14px;
        height: 100%;
    }}
    .glance-card .name {{ font-weight: 700; font-size: 0.95rem; }}
    .glance-card .sub {{ color: var(--muted); font-size: 0.74rem; }}
    .glance-card .big {{ font-size: 1.3rem; font-weight: 700; margin: 4px 0; }}
    .glance-card .range {{ color: var(--muted); font-size: 0.82rem; }}

    /* Section divider */
    hr {{ border-color: var(--border); }}

    /* Remove the default Streamlit footer/menu noise */
    #MainMenu {{ visibility: hidden; }}
    footer {{ visibility: hidden; }}
    </style>
    """


def badge(text: str, kind: str = "line") -> str:
    """Return an inline HTML badge. kind: warn | soft | line."""
    cls = {"warn": "badge-warn", "soft": "badge-soft", "line": "badge-line"}.get(kind, "badge-line")
    return f'<span class="badge {cls}">{text}</span>'
