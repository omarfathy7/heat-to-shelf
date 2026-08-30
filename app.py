"""
Heat-to-Shelf — Thermal Decision Intelligence for Heat-Sensitive Cargo
Hackathon MVP — runs entirely from cached data, zero API calls.

Run: streamlit run app.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import folium_static
import geopandas as gpd
from shapely.geometry import LineString

# ── Path setup ──
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.risk_engine import RiskEngine, CargoProfile, RiskLevel
from src.loader import load_scenario, build_observations
from src.cargo_profiles import CARGO_PROFILES

# ═══════════════════════════════════════════════════
# Page config
# ═══════════════════════════════════════════════════
st.set_page_config(
    page_title="Heat-to-Shelf",
    page_icon="🌡️",
    layout="wide",
)

CACHE = PROJECT_ROOT / "cache"
STUDY_DATE = "2026-08-19"
SCENARIO_HOURS = [
    "04:00", "06:00", "08:00", "10:00", "12:00",
    "14:00", "16:00", "18:00", "20:00", "22:00"
]

ORIGIN = (-121.8863, 37.3382)
DESTINATION = (-122.4194, 37.7749)

LEVEL_COLORS = {
    RiskLevel.SAFE: "#2b8a3e",
    RiskLevel.WARNING: "#f59f00",
    RiskLevel.HIGH: "#e8590c",
    RiskLevel.CRITICAL: "#c92a2a",
}

# ═══════════════════════════════════════════════════
# Cached functions (cargo-independent)
# ═══════════════════════════════════════════════════
@st.cache_data
def fetch_route() -> dict:
    url = (
        "https://router.project-osrm.org/route/v1/driving/"
        f"{ORIGIN[0]},{ORIGIN[1]};{DESTINATION[0]},{DESTINATION[1]}"
        "?overview=full&geometries=geojson"
    )
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()["routes"][0]

@st.cache_data
def build_route_samples(n_samples: int) -> pd.DataFrame:
    route = fetch_route()
    line = LineString(route["geometry"]["coordinates"])
    gdf = gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326")
    line_m = gdf.to_crs("EPSG:26910").geometry.iloc[0]
    dists = np.linspace(0, line_m.length, n_samples)
    pts = [line_m.interpolate(d) for d in dists]
    samples = (
        gpd.GeoDataFrame(
            {"segment_id": range(n_samples), "distance_m": dists},
            geometry=pts, crs="EPSG:26910",
        ).to_crs("EPSG:4326")
    )
    samples["lat"] = samples.geometry.y
    samples["lon"] = samples.geometry.x
    return samples.drop(columns="geometry")

@st.cache_data
def assess_all_scenarios(cargo_name: str) -> dict:
    """Load + assess all scenarios. Re-assesses when cargo changes."""
    cargo = CARGO_PROFILES[cargo_name]
    engine = RiskEngine(CargoProfile(
        name=cargo.name,
        warning_threshold_c=cargo.warning_threshold_c,
        critical_threshold_c=cargo.critical_threshold_c,
        source_name=cargo.source_name,
        source_url=cargo.source_url,
    ))
    out = {}
    for hour in SCENARIO_HOURS:
        payload = load_scenario(CACHE, STUDY_DATE, hour)
        obs = build_observations(payload)
        assessment = engine.assess(obs)
        out[hour] = {
            "payload": payload,
            "observations": obs,
            "assessment": assessment,
        }
    return out

# ═══════════════════════════════════════════════════
# Sidebar — cargo selection (MUST be first in execution order)
# ═══════════════════════════════════════════════════
with st.sidebar:
    st.header("📦 Shipment")
    selected_cargo_name = st.selectbox(
        "Select cargo type:",
        list(CARGO_PROFILES.keys()),
    )
    selected_cargo = CARGO_PROFILES[selected_cargo_name]

    try:
        scenarios = assess_all_scenarios(selected_cargo_name)
    except FileNotFoundError as e:
        st.error(f"Cache missing: {e}. Run notebook 07 first.")
        st.stop()

    engine = RiskEngine(CargoProfile(
        name=selected_cargo.name,
        warning_threshold_c=selected_cargo.warning_threshold_c,
        critical_threshold_c=selected_cargo.critical_threshold_c,
        source_name=selected_cargo.source_name,
        source_url=selected_cargo.source_url,
    ))

    st.markdown(f"**Cargo:** {engine.cargo.name}")
    st.markdown(f"⚠️ **Warning:** {engine.cargo.warning_threshold_c}°C")
    st.markdown(f"🚨 **Critical:** {engine.cargo.critical_threshold_c}°C")
    st.caption(f"Source: {engine.cargo.source_name[:60]}...")

    st.divider()
    st.header("🕐 Departure Scenario")
    selected_hour = st.radio(
        "Select departure time:",
        SCENARIO_HOURS,
        format_func=lambda h: (
            f"{h} — {scenarios[h]['assessment'].risk_level.value}"
        ),
    )

    st.divider()
    st.caption("Methodology v0.1 · Severity + Duration · Critical Override")
    st.caption("Data: FortyGuard Temperature API (cached)")

# ═══════════════════════════════════════════════════
# Route data (cargo-independent)
# ═══════════════════════════════════════════════════
route = fetch_route()
route_km = route["distance"] / 1000
route_min = route["duration"] / 60
samples = build_route_samples(150)

# ═══════════════════════════════════════════════════
# Header (selected_cargo is available now)
# ═══════════════════════════════════════════════════
st.title("🌡️ Heat-to-Shelf")
st.markdown(
    "**Thermal Decision Intelligence for Heat-Sensitive Cargo** — "
    "*When should this shipment leave?*"
)

meta1, meta2, meta3, meta4 = st.columns(4)
with meta1:
    st.caption("Route")
    st.write("**San Jose → San Francisco**")
with meta2:
    st.caption("Distance")
    st.write(f"**{route_km:.1f} km**")
with meta3:
    st.caption("Transit Time")
    st.write(f"**{route_min:.0f} min**")
with meta4:
    st.caption("Analysis Date")
    st.write(f"**{STUDY_DATE}**")

st.info(
    f"**Cargo:** {selected_cargo.name} — "
    f"warning {selected_cargo.warning_threshold_c}°C / "
    f"critical {selected_cargo.critical_threshold_c}°C. "
    f"Source: {selected_cargo.source_name[:50]}...",
    icon="📦",
)

st.divider()

# ═══════════════════════════════════════════════════
# Selected scenario — risk display
# ═══════════════════════════════════════════════════
current = scenarios[selected_hour]
a = current["assessment"]
level_color = LEVEL_COLORS[a.risk_level]

st.markdown(
    f"<h2 style='color:{level_color};margin-bottom:0;'>"
    f"Risk: {a.risk_score} / 100 — {a.risk_level.value}</h2>",
    unsafe_allow_html=True,
)

if a.critical_override_triggered:
    n_crit = len(a.critical_segments)
    st.error(
        f"🚨 **CRITICAL OVERRIDE TRIGGERED** — {n_crit} segments "
        f"exceeded the critical threshold "
        f"({engine.cargo.critical_threshold_c}°C). "
        f"This shipment should NOT depart at {selected_hour} "
        f"under this cargo profile.",
        icon="🚨",
    )

c1, c2, c3, c4 = st.columns(4)
with c1:
    peak = max(s.temperature_c for s in current["observations"]
               if s.temperature_c is not None)
    st.metric("Peak Temperature", f"{peak:.1f}°C")
with c2:
    st.metric("Exposure Above Warning", f"{a.exposure_hours * 60:.1f} min")
with c3:
    st.metric("Segments at Risk", f"{a.segments_above_warning} / 150")
with c4:
    st.metric("Longest Continuous Run", f"{a.longest_run_hours * 60:.1f} min")

with st.expander("📊 Risk Score Breakdown"):
    st.markdown(
        f"**Weighted formula:** `0.55 × Severity + 0.45 × Duration`\n\n"
        f"- Severity (peak temp normalized): `{a.severity_component}`\n"
        f"- Duration (exposure fraction): `{a.duration_component}`\n"
        f"- **Score:** `{a.risk_score} / 100`\n\n"
        f"*Persistence tracked as context, not in v0.1 score "
        f"(per methodology decision).*"
    )

# ═══════════════════════════════════════════════════
# Thermal Journey chart
# ═══════════════════════════════════════════════════
st.subheader(f"🌡️ Thermal Journey — Departure {selected_hour}")

import plotly.graph_objects as go

fig = go.Figure()
temps = [s.temperature_c for s in current["observations"]]
dists = [s.distance_km for s in current["observations"]]

fig.add_trace(go.Scatter(
    x=dists, y=temps, mode="lines+markers",
    marker=dict(size=4), line=dict(color="#f3854e", width=2.5),
    name=f"Temperature ({selected_hour})",
    hovertemplate="Distance: %{x:.1f} km<br>Temp: %{y:.1f}°C<extra></extra>",
))

fig.add_hline(y=engine.cargo.warning_threshold_c,
              line_dash="dash", line_color="#f59f00",
              annotation_text=f"Warning {engine.cargo.warning_threshold_c}°C")
fig.add_hline(y=engine.cargo.critical_threshold_c,
              line_dash="dash", line_color="#c92a2a",
              annotation_text=f"Critical {engine.cargo.critical_threshold_c}°C")

fig.add_hrect(y0=engine.cargo.warning_threshold_c, y1=max(temps) + 1,
              fillcolor="rgba(201,42,42,0.08)", line_width=0)

fig.update_layout(
    xaxis_title="Distance along route (km)", yaxis_title="Temperature (°C)",
    height=420, margin=dict(l=20, r=20, t=40, b=20),
    showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig, use_container_width=True)

# ═══════════════════════════════════════════════════
# Map
# ═══════════════════════════════════════════════════
st.subheader("🗺️ Route Thermal Map")

map_df = samples.merge(
    pd.DataFrame([
        {"segment_id": s.segment_id, "temperature_c": s.temperature_c}
        for s in current["observations"]
    ]),
    on="segment_id", how="left",
)

def temp_color_fixed(t, warning_c, critical_c):
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return "#868e96"
    if t >= critical_c:
        return "#c92a2a"
    if t >= warning_c:
        return "#f59f00"
    frac = max(0.0, min(1.0, t / warning_c))
    r = int(41 + 40 * frac)
    g = int(128 + 30 * frac)
    b = int(200 - 60 * frac)
    return f"#{r:02x}{g:02x}{b:02x}"

fmap = folium.Map(location=[37.55, -122.15], zoom_start=9, tiles="cartodbpositron")

for i in range(len(map_df) - 1):
    row_a, row_b = map_df.iloc[i], map_df.iloc[i + 1]
    temp = row_a.temperature_c
    folium.PolyLine(
        locations=[[row_a.lat, row_a.lon], [row_b.lat, row_b.lon]],
        color=temp_color_fixed(temp, engine.cargo.warning_threshold_c,
                                engine.cargo.critical_threshold_c),
        weight=5, opacity=0.9,
        tooltip=f"{temp:.1f}°C @ {row_a.distance_m/1000:.1f} km"
        if temp is not None else "No data",
    ).add_to(fmap)

folium.Marker([ORIGIN[1], ORIGIN[0]], popup="Origin: San Jose",
              icon=folium.Icon(color="green", icon="play")).add_to(fmap)
folium.Marker([DESTINATION[1], DESTINATION[0]], popup="Destination: San Francisco",
              icon=folium.Icon(color="red", icon="stop")).add_to(fmap)

legend_html = (
    '<div style="position:fixed;bottom:30px;left:30px;z-index:9999;'
    'background:white;padding:10px 14px;border:1px solid #888;'
    'font:12px sans-serif;box-shadow:0 2px 6px rgba(0,0,0,.15);">'
    '<b>Route Temperature</b><br>'
    f'<span style="color:#666;">anchored to cargo thresholds</span>'
    '<table style="margin-top:6px;border-collapse:collapse;">'
    f'<tr><td style="background:#c92a2a;width:20px;height:12px;border:1px solid #888;"></td>'
    f'<td style="padding-left:8px;">≥ {engine.cargo.critical_threshold_c}°C (critical)</td></tr>'
    f'<tr><td style="background:#f59f00;width:20px;height:12px;border:1px solid #888;"></td>'
    f'<td style="padding-left:8px;">≥ {engine.cargo.warning_threshold_c}°C (warning)</td></tr>'
    f'<tr><td style="background:#2983ba;width:20px;height:12px;border:1px solid #888;"></td>'
    f'<td style="padding-left:8px;">&lt; {engine.cargo.warning_threshold_c}°C (safe)</td></tr>'
    '</table></div>'
)
fmap.get_root().html.add_child(folium.Element(legend_html))

folium_static(fmap, height=450)

# ═══════════════════════════════════════════════════
# Scenario comparison
# ═══════════════════════════════════════════════════
st.subheader("⚖️ Scenario Comparison — What-if Analysis")

comp_rows = []
for h in SCENARIO_HOURS:
    aa = scenarios[h]["assessment"]
    comp_rows.append({
        "Departure": h,
        "Risk Score": aa.risk_score,
        "Risk Level": aa.risk_level.value,
        "Override": "🚨 FIRED" if aa.critical_override_triggered else "—",
        "Exposure (min)": round(aa.exposure_hours * 60, 1),
        "Longest Run (min)": round(aa.longest_run_hours * 60, 1),
        "Segments at Risk": f"{aa.segments_above_warning} / 150",
    })
st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════
# Recommendation
# ═══════════════════════════════════════════════════
best_hour = min(SCENARIO_HOURS,
                key=lambda h: scenarios[h]["assessment"].risk_score)
best_a = scenarios[best_hour]["assessment"]
worst_a = max((scenarios[h]["assessment"] for h in SCENARIO_HOURS),
              key=lambda a: a.risk_score)
exp_delta = (worst_a.exposure_hours - best_a.exposure_hours) * 60

st.success(
    f"**Recommended departure: {best_hour}** — "
    f"lowest modeled thermal exposure.\n\n"
    f"- Risk score: **{best_a.risk_score}** ({best_a.risk_level.value})\n"
    f"- Exposure: **{best_a.exposure_hours * 60:.1f} min**\n"
    f"- vs. worst ({worst_a.risk_score} {worst_a.risk_level.value}): "
    f"**{exp_delta:.1f} fewer exposure-minutes**",
    icon="✅",
)

# ═══════════════════════════════════════════════════
# Footer
# ═══════════════════════════════════════════════════
st.divider()
st.caption("**Heat-to-Shelf** · FortyGuard Global AI Hackathon 2026 · Track 3: Industrial & Enterprise")
st.caption("Endpoints: Create Heatmap (tcm, single-hour × 10 scenarios) · spatial join via GeoPandas · Risk methodology v0.1")