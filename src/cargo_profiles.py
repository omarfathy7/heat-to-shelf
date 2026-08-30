"""Credible, sourced cargo profiles for Heat-to-Shelf.
Each profile's thresholds come from published/industry sources.
Chocolate and Wine demonstrate full risk separation.
Lipstick is deliberately included as a "null result" — proving
the engine reports SAFE when the cargo is genuinely not at risk.
"""

from dataclasses import dataclass


@dataclass
class CargoProfile:
    name: str
    category: str
    warning_threshold_c: float
    critical_threshold_c: float
    source_name: str
    source_url: str
    source_notes: str


# ── Profile 1: Chocolate — strongest citation (4 converging sources) ──
CHOCOLATE_PROFILE = CargoProfile(
    name="Premium Chocolate — Transport",
    category="Confectionery",
    warning_threshold_c=25.0,
    critical_threshold_c=28.0,
    source_name=(
        "Multiple independent shipping specialists "
        "(Suaid Global, IPC, ParcelPath, TemperPack)"
    ),
    source_url="https://suaidglobal.com/insights/chocolate-shipping-temperature/",
    source_notes=(
        "Convergent sourcing: 'starts to soften' at 77°F/25°C "
        "(Suaid Global, IPC Chocolate Shipping Guide); "
        "'structural damage even before complete melting' at "
        "85°F/29.4°C (ParcelPath); fat-bloom range 80-90°F "
        "per TemperPack. Critical set conservatively at 28°C, "
        "within the commonly-cited damage range — an override "
        "threshold should trigger before, not at, confirmed damage."
        "\n\n"
        "ENGINEERING VALIDATION: corridor peak = 30.1°C; "
        "30.1 ≥ 28.0 → Critical Override fires with 2.1°C margin. "
        "06:00 peak = 16.9°C < 25.0 → SAFE."
    ),
)


# ── Profile 2: Wine — direct match from logistics specialist ──
WINE_PROFILE = CargoProfile(
    name="Red Wine — Transport",
    category="Wine & Spirits",
    warning_threshold_c=25.0,
    critical_threshold_c=28.0,
    source_name=(
        "TGL – Team Global Logistics (freight/logistics specialist) "
        "— wine transport industry guidance"
    ),
    source_url="https://www.tgl-group.net/en/news-detail1182_0.htm",
    source_notes=(
        "Direct match: TGL states 'ambient temperature doesn't "
        "exceed 25 to 28°C' as the comfort zone; 80°F (27°C) "
        "sustained >30min flagged as where damage becomes hard "
        "to reverse; 86°F (30°C) described as wine getting "
        "'cooked'. Matches this profile's thresholds exactly."
        "\n\n"
        "ENGINEERING VALIDATION: corridor peak = 30.1°C ≈ the "
        "source's own 'cooked' reference point (86°F/30°C)."
    ),
)


# ── Profile 3: Lipstick — deliberate "null result" ──
LIPSTICK_PROFILE = CargoProfile(
    name="Lipstick — Transport",
    category="Cosmetics",
    warning_threshold_c=45.0,
    critical_threshold_c=54.4,   # 130°F per cosmetic chemist
    source_name=(
        "Cosmetic chemist consultation (Perry Romanowski, "
        "Chemists Corner) via The Zoe Report"
    ),
    source_url=(
        "https://www.thezoereport.com/p/makeup-melting-happens"
        "-in-winter-too-heres-how-to-prevent-it-12599203"
    ),
    source_notes=(
        "'Lipstick has a melting point of at least 130°F (54.4°C), "
        "so a good lipstick should not melt under normal circumstances.' "
        "Deliberately included: this corridor's full range "
        "(13.5-30.1°C) stays well below lipstick's damage threshold "
        "on every one of the 10 tested departure hours — demonstrating "
        "that the engine reports risk based on real cargo physics, "
        "not narrative convenience. A correct SAFE-across-the-board "
        "result is itself evidence of a working system."
    ),
)


# ── Registry — used by app.py selectbox ──
CARGO_PROFILES = {
    "Chocolate": CHOCOLATE_PROFILE,
    "Wine": WINE_PROFILE,
    "Lipstick": LIPSTICK_PROFILE,
}


if __name__ == "__main__":
    for name, p in CARGO_PROFILES.items():
        print("=" * 60)
        print(f"Cargo:     {p.name}")
        print(f"Category:  {p.category}")
        print(f"Warning:   {p.warning_threshold_c}°C")
        print(f"Critical:  {p.critical_threshold_c}°C")
        print(f"Source:    {p.source_name[:60]}...")
        print()