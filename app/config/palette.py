"""Jetons de couleur des thèmes : une seule source pour le QSS et les widgets dessinés au QPainter.

Les deux palettes portent exactement les mêmes clés : `base.qss` est un gabarit
`$jeton` rempli avec l'une ou l'autre, et les widgets custom (waveform, vignettes)
lisent les mêmes clés via `Theme.palette`.
"""

DARK_PALETTE: dict[str, str] = {
    # Fonds, du plus profond au plus proche de l'utilisateur.
    "bg": "#14171b",
    "titlebar": "#1a1e24",
    "surface": "#1b1f25",
    "card": "#21262e",
    "field": "#272d36",
    "field_hover": "#2e3540",
    "border": "#2c323b",
    "border_strong": "#3a424e",
    # Texte.
    "text": "#e4e7ec",
    "text_muted": "#8a929e",
    "text_faint": "#6b7380",
    "text_on_accent": "#ffffff",
    # Accent (actions principales) et états.
    "accent": "#e2622c",
    "accent_hover": "#ef7038",
    "accent_pressed": "#c9531f",
    "accent_soft": "#3a2418",
    "success": "#4aa877",
    "success_soft": "#1d3328",
    "warning": "#e0a83a",
    "warning_soft": "#2e2718",
    # Waveform et règle temporelle.
    "wave_bg": "#191d23",
    "wave_bar": "#94a3b2",
    "wave_grid": "#2a303a",
    "wave_text": "#8a929e",
    "playhead": "#ffffff",
    "region_fill": "#1f3a2e",
    "region_border": "#3f7d5f",
    "region_fill_active": "#3a2418",
    "region_border_active": "#e2622c",
    "selection_fill": "#e2622c",
    "overview_window": "#e2622c",
    "marker": "#55a8e0",
}

LIGHT_PALETTE: dict[str, str] = {
    "bg": "#eef1f5",
    "titlebar": "#ffffff",
    "surface": "#ffffff",
    "card": "#f7f9fb",
    "field": "#ffffff",
    "field_hover": "#f0f3f7",
    "border": "#dde3ea",
    "border_strong": "#c2cbd6",
    "text": "#1c2127",
    "text_muted": "#5d6673",
    "text_faint": "#828c99",
    "text_on_accent": "#ffffff",
    "accent": "#d9541f",
    "accent_hover": "#e66430",
    "accent_pressed": "#bd4715",
    "accent_soft": "#fdeee6",
    "success": "#1f8a4c",
    "success_soft": "#e5f4ea",
    "warning": "#a8741c",
    "warning_soft": "#fdf3e0",
    "wave_bg": "#ffffff",
    "wave_bar": "#6b7a8c",
    "wave_grid": "#e4e9ef",
    "wave_text": "#5d6673",
    "playhead": "#1c2127",
    "region_fill": "#e3f3e9",
    "region_border": "#4aa877",
    "region_fill_active": "#fdeee6",
    "region_border_active": "#d9541f",
    "selection_fill": "#d9541f",
    "overview_window": "#d9541f",
    "marker": "#1f6fa8",
}

assert set(DARK_PALETTE) == set(LIGHT_PALETTE), "les deux palettes doivent porter les mêmes jetons"
