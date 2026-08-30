# ═══════════════════════════════════════════════════
# 10 — Hero Chart: one route, three key departures
# Plus 10-scenario summary table
# Save as: outputs/hero_chart.html
# ═══════════════════════════════════════════════════

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.risk_engine import RiskEngine, CargoProfile
from src.cargo_profiles import WINE_PROFILE
from src.loader import load_scenario, build_observations

CACHE = PROJECT_ROOT / "cache"
STUDY_DATE = "2026-08-19"

# 3 key lines for the chart (clarity)
HOURS = ["06:00", "12:00", "16:00"]

# All 10 for the summary table
ALL_10 = ["04:00", "06:00", "08:00", "10:00", "12:00",
          "14:00", "16:00", "18:00", "20:00", "22:00"]

engine = RiskEngine(CargoProfile(
    name=WINE_PROFILE.name,
    warning_threshold_c=WINE_PROFILE.warning_threshold_c,
    critical_threshold_c=WINE_PROFILE.critical_threshold_c,
    source_name=WINE_PROFILE.source_name,
    source_url=WINE_PROFILE.source_url,
))

WARN = WINE_PROFILE.warning_threshold_c
CRIT = WINE_PROFILE.critical_threshold_c
colors = {"06:00": "#2983ba", "12:00": "#f59f00", "16:00": "#c92a2a"}

# ── Load the 3 key scenarios ──
scenarios = {}
for hour in HOURS:
    payload = load_scenario(CACHE, STUDY_DATE, hour)
    obs = build_observations(payload)
    scenarios[hour] = {"obs": obs, "assess": engine.assess(obs)}

# ── Load all 10 for summary ──
all_results = {}
for hour in ALL_10:
    try:
        payload = load_scenario(CACHE, STUDY_DATE, hour)
        obs = build_observations(payload)
        all_results[hour] = engine.assess(obs)
    except FileNotFoundError:
        all_results[hour] = None

# ═══════════════════════════════════════════════════
# Main figure — 3 key lines + danger zones
# ═══════════════════════════════════════════════════
fig = go.Figure()

# Danger zones
fig.add_hrect(y0=CRIT, y1=33, fillcolor="rgba(201,42,42,0.15)",
              line_width=0, annotation_text=f"⚠️ CRITICAL ZONE (≥{CRIT}°C)",
              annotation_position="top right",
              annotation_font=dict(color="#c92a2a", size=11))
fig.add_hrect(y0=WARN, y1=CRIT, fillcolor="rgba(245,159,0,0.15)",
              line_width=0, annotation_text=f"Warning zone ({WARN}-{CRIT}°C)",
              annotation_position="top right",
              annotation_font=dict(color="#b8860b", size=10))

# Three key lines
for hour in HOURS:
    s = scenarios[hour]
    a = s["assess"]
    label = (f"{hour} — Risk {a.risk_score} ({a.risk_level.value})"
             + (" 🚨" if a.critical_override_triggered else ""))
    fig.add_trace(go.Scatter(
        x=[o.distance_km for o in s["obs"]],
        y=[o.temperature_c for o in s["obs"]],
        mode="lines",
        line=dict(color=colors[hour], width=3),
        name=label,
        hovertemplate=(
            f"<b>{hour}</b><br>Distance: %{{x:.0f}} km<br>"
            f"Temp: %{{y:.1f}}°C<extra></extra>"
        ),
    ))

# Title — NO placeholder
fig.update_layout(
    title=dict(
        text=(
            "One route, three departure hours — the decision is the data<br>"
            f"<sup>San Jose → San Francisco · {STUDY_DATE} · "
            f"Cargo: {WINE_PROFILE.name} · "
            f"Thresholds: warning {WARN}°C / critical {CRIT}°C · "
            f"Source: FDA FSMA + wine industry standards</sup>"
        ),
        font=dict(size=16),
    ),
    xaxis_title="Distance along route (km)",
    yaxis_title="Temperature (°C)",
    yaxis_range=[13, 33],
    height=520,
    template="plotly_white",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.2),
    margin=dict(l=60, r=30, t=110, b=50),
)

# ── Add 10-scenario summary as annotation ──
summary_lines = ["<b>Full-day sweep (10 hours):</b>"]
for hour in ALL_10:
    a = all_results[hour]
    if a:
        icon = "🚨" if a.critical_override_triggered else ""
        summary_lines.append(
            f"{hour} → {a.risk_score} {a.risk_level.value} "
            f"({a.exposure_hours*60:.0f}min) {icon}"
        )
    else:
        summary_lines.append(f"{hour} → not cached")

summary_text = "<br>".join(summary_lines)
fig.add_annotation(
    text=summary_text,
    xref="paper", yref="paper",
    x=0.99, y=0.01,
    xanchor="right", yanchor="bottom",
    showarrow=False,
    font=dict(size=9, color="#666"),
    align="right",
    bgcolor="rgba(255,255,255,0.85)",
    bordercolor="#ccc",
    borderwidth=1,
    borderpad=4,
)

out_html = PROJECT_ROOT / "outputs" / "hero_chart.html"
out_html.parent.mkdir(exist_ok=True)
fig.write_html(str(out_html))
try:
    fig.write_image(str(PROJECT_ROOT / "outputs" / "hero_chart.png"),
                    scale=2, width=1200, height=520)
except Exception as e:
    print(f"(png export needs kaleido: {e}) — html is fine")

print(f"Saved -> {out_html}")

# Print story
print("\n── Three key scenarios ──")
for hour in HOURS:
    a = scenarios[hour]["assess"]
    print(f"{hour}: score {a.risk_score:>5} {a.risk_level.value:<9} "
          f"exposure {a.exposure_hours*60:>4.1f} min  "
          f"{'🚨 OVERRIDE' if a.critical_override_triggered else ''}")

print("\n── Full 10-hour sweep ──")
for hour in ALL_10:
    a = all_results[hour]
    if a:
        print(f"{hour}: score {a.risk_score:>5} {a.risk_level.value:<9} "
              f"exposure {a.exposure_hours*60:>4.1f} min  "
              f"{'🚨' if a.critical_override_triggered else ''}")
    else:
        print(f"{hour}: NOT CACHED")