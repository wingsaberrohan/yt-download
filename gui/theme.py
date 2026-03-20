"""Color tokens and CTk widget style factories for the glassmorphism theme."""

COLORS = {
    "base":           "#0e0f14",
    "surface":        "#13151c",
    "glass":          "#16171d",
    "glass-border":   "#252730",
    "accent":         "#7c6af7",
    "accent-hover":   "#2a2560",
    "accent-active":  "#6355d4",
    "success":        "#4ade80",
    "error":          "#f87171",
    "scheduled":      "#fbbf24",
    "text-primary":   "#f0f0f5",
    "text-secondary": "#8b8fa8",
    # elevation layers
    "layer-0": "#0e0f14",
    "layer-1": "#13151c",
    "layer-2": "#16171d",
    "layer-3": "#1c1e28",
}

_STRIPE_COLORS = {
    "pending":     "#8b8fa8",
    "downloading": "#7c6af7",
    "converting":  "#a78bfa",
    "done":        "#4ade80",
    "failed":      "#f87171",
    "scheduled":   "#fbbf24",
}


def glass_frame() -> dict:
    return dict(fg_color=COLORS["glass"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=10)


def surface_frame() -> dict:
    return dict(fg_color=COLORS["surface"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=10)


def accent_button() -> dict:
    return dict(fg_color=COLORS["accent"], hover_color=COLORS["accent-active"],
                text_color=COLORS["text-primary"], corner_radius=8)


def ghost_button() -> dict:
    return dict(fg_color="transparent", hover_color=COLORS["accent-hover"],
                text_color=COLORS["text-secondary"], border_width=1,
                border_color=COLORS["glass-border"], corner_radius=8)


def pill_entry() -> dict:
    return dict(fg_color=COLORS["glass"], border_color=COLORS["glass-border"],
                corner_radius=22, text_color=COLORS["text-primary"])


def status_stripe(state: str) -> dict:
    color = _STRIPE_COLORS.get(state, _STRIPE_COLORS["pending"])
    return dict(fg_color=color, width=4, corner_radius=2)


def label_style(size: int = 13, secondary: bool = False) -> dict:
    color = COLORS["text-secondary"] if secondary else COLORS["text-primary"]
    return dict(text_color=color, font=("Segoe UI Variable", size))
