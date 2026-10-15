import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fastf1
import fastf1.plotting

# Page Configuration
st.set_page_config(
    page_title="F1 Race & Telemetry Replay",
    page_icon="🏎️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 800;
        color: #E10600;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #888888;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #1e1e24;
        border-radius: 8px;
        padding: 12px;
        border-left: 4px solid #E10600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Enable caching for FastF1
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".fastf1-cache")
os.makedirs(CACHE_DIR, exist_ok=True)
try:
    fastf1.Cache.enable_cache(CACHE_DIR)
except Exception:
    pass


@st.cache_data(show_spinner=False)
def get_schedule(year: int):
    """Fetch event schedule for given year."""
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        # Filter completed or scheduled rounds
        schedule = schedule[schedule["RoundNumber"] > 0]
        return schedule
    except Exception as e:
        st.error(f"Failed to load schedule for {year}: {e}")
        return pd.DataFrame()


@st.cache_data(show_spinner=True)
def load_session_data(year: int, round_number: int, session_type: str):
    """Load and prepare a FastF1 session."""
    session = fastf1.get_session(year, round_number, session_type)
    session.load(telemetry=True, laps=True, weather=True)
    return session


def format_timedelta(td):
    if pd.isna(td):
        return "-"
    total_seconds = td.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:06.3f}"


# --- Header ---
st.markdown('<div class="main-title">🏎️ Formula 1 Race & Telemetry Dashboard</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Interactive Lap Telemetry, Track Analysis & Race Results powered by FastF1</div>',
    unsafe_allow_html=True,
)

# --- Sidebar Controls ---
st.sidebar.header("🏁 Race Selection")

current_year = 2024
years = list(range(current_year, 2017, -1))
selected_year = st.sidebar.selectbox("Year / Season", years, index=0)

schedule = get_schedule(selected_year)

if not schedule.empty:
    event_names = schedule["EventName"].tolist()
    default_round = min(len(event_names) - 1, 0)
    selected_event_name = st.sidebar.selectbox("Grand Prix", event_names, index=default_round)
    event_row = schedule[schedule["EventName"] == selected_event_name].iloc[0]
    round_number = int(event_row["RoundNumber"])
else:
    selected_event_name = "Default GP"
    round_number = 1

session_options = {
    "Race": "R",
    "Qualifying": "Q",
    "Sprint": "S",
    "Sprint Qualifying / Shootout": "SQ",
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
}

selected_session_label = st.sidebar.selectbox("Session", list(session_options.keys()), index=0)
session_code = session_options[selected_session_label]

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Tip:** First-time load for a session downloads telemetry from FastF1 and caches it for fast future access."
)

# --- Main App ---
try:
    with st.spinner(f"Loading {selected_year} {selected_event_name} - {selected_session_label}..."):
        session = load_session_data(selected_year, round_number, session_code)
except Exception as e:
    st.error(f"Could not load telemetry for this session: {e}")
    st.info("Try selecting a different session or year (some upcoming or very early sessions may not have full telemetry).")
    st.stop()

# Basic Session Info banner
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Round", f"Round {round_number}")
with col2:
    st.metric("Circuit", session.event.get("Location", selected_event_name))
with col3:
    event_date = session.event.get("EventDate")
    st.metric("Date", event_date.strftime("%Y-%m-%d") if pd.notna(event_date) else "-")
with col4:
    st.metric("Session Type", selected_session_label)

st.markdown("---")

tab_results, tab_telemetry, tab_track, tab_lap_chart = st.tabs([
    "🏆 Session Results",
    "⚡ Telemetry Comparison",
    "🗺️ Track Map & Speeds",
    "⏱️ Lap Time Pace",
])

# ==========================================
# TAB 1: SESSION RESULTS
# ==========================================
with tab_results:
    st.subheader(f"🏁 {selected_session_label} Classification")
    try:
        results = session.results
        if results is not None and not results.empty:
            df_display = pd.DataFrame()
            df_display["Pos"] = results["Position"].astype(str).replace("nan", "-")
            df_display["No."] = results["DriverNumber"]
            df_display["Driver"] = results["FullName"]
            df_display["Code"] = results["Abbreviation"]
            df_display["Team"] = results["TeamName"]
            
            if "Time" in results.columns:
                df_display["Time / Gap"] = results["Time"].apply(format_timedelta)
            if "Status" in results.columns:
                df_display["Status"] = results["Status"]
            if "Points" in results.columns:
                df_display["Points"] = results["Points"]

            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.warning("No classification results found for this session.")
    except Exception as err:
        st.error(f"Error displaying session results: {err}")

# ==========================================
# TAB 2: TELEMETRY COMPARISON
# ==========================================
with tab_telemetry:
    st.subheader("⚡ Head-to-Head Fastest Lap Telemetry")
    
    laps = session.laps
    if laps is not None and not laps.empty:
        drivers = sorted([d for d in laps["Driver"].unique() if pd.notna(d)])
        
        c1, c2 = st.columns(2)
        with c1:
            driver1 = st.selectbox("Driver 1", drivers, index=0, key="d1")
        with c2:
            default_d2_idx = 1 if len(drivers) > 1 else 0
            driver2 = st.selectbox("Driver 2", drivers, index=default_d2_idx, key="d2")

        lap_d1 = laps.pick_driver(driver1).pick_fastest()
        lap_d2 = laps.pick_driver(driver2).pick_fastest()

        if lap_d1 is not None and lap_d2 is not None:
            time_d1 = format_timedelta(lap_d1["LapTime"])
            time_d2 = format_timedelta(lap_d2["LapTime"])
            delta_sec = (lap_d1["LapTime"] - lap_d2["LapTime"]).total_seconds()

            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric(f"{driver1} Fastest Lap", time_d1)
            with m2:
                st.metric(f"{driver2} Fastest Lap", time_d2)
            with m3:
                delta_str = f"{delta_sec:+.3f}s"
                st.metric("Delta (D1 vs D2)", delta_str)

            try:
                tel_d1 = lap_d1.get_car_data().add_distance()
                tel_d2 = lap_d2.get_car_data().add_distance()

                # Get driver colors
                try:
                    color_d1 = fastf1.plotting.driver_color(driver1)
                except Exception:
                    color_d1 = "#00D2BE"

                try:
                    color_d2 = fastf1.plotting.driver_color(driver2)
                except Exception:
                    color_d2 = "#FF1801"

                fig = make_subplots(
                    rows=3,
                    cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.06,
                    subplot_titles=["Speed (km/h)", "Throttle (%) & Brake", "Gear"],
                )

                # Speed
                fig.add_trace(
                    go.Scatter(x=tel_d1["Distance"], y=tel_d1["Speed"], name=driver1, line=dict(color=color_d1, width=2)),
                    row=1, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=tel_d2["Distance"], y=tel_d2["Speed"], name=driver2, line=dict(color=color_d2, width=2)),
                    row=1, col=1,
                )

                # Throttle
                fig.add_trace(
                    go.Scatter(x=tel_d1["Distance"], y=tel_d1["Throttle"], name=f"{driver1} Throttle", line=dict(color=color_d1, width=1.5)),
                    row=2, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=tel_d2["Distance"], y=tel_d2["Throttle"], name=f"{driver2} Throttle", line=dict(color=color_d2, width=1.5)),
                    row=2, col=1,
                )

                # Brake (0/1 or percentage)
                fig.add_trace(
                    go.Scatter(x=tel_d1["Distance"], y=tel_d1["Brake"] * 100, name=f"{driver1} Brake", line=dict(color=color_d1, dash="dot")),
                    row=2, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=tel_d2["Distance"], y=tel_d2["Brake"] * 100, name=f"{driver2} Brake", line=dict(color=color_d2, dash="dot")),
                    row=2, col=1,
                )

                # Gear
                fig.add_trace(
                    go.Scatter(x=tel_d1["Distance"], y=tel_d1["nGear"], name=f"{driver1} Gear", line=dict(color=color_d1, width=1.5)),
                    row=3, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=tel_d2["Distance"], y=tel_d2["nGear"], name=f"{driver2} Gear", line=dict(color=color_d2, width=1.5)),
                    row=3, col=1,
                )

                fig.update_layout(
                    height=750,
                    template="plotly_dark",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=20, r=20, t=50, b=20),
                )
                fig.update_xaxes(title_text="Track Distance (meters)", row=3, col=1)

                st.plotly_chart(fig, use_container_width=True)

            except Exception as e:
                st.warning(f"Could not load detailed telemetry channels for these drivers: {e}")
        else:
            st.warning("Fastest lap telemetry unavailable for selected drivers.")
    else:
        st.warning("No lap telemetry available for this session.")

# ==========================================
# TAB 3: TRACK MAP & SPEEDS
# ==========================================
with tab_track:
    st.subheader("🗺️ Circuit Layout & Speed Heatmap")
    try:
        fastest_overall_lap = session.laps.pick_fastest()
        if fastest_overall_lap is not None:
            pos_data = fastest_overall_lap.get_pos_data()
            car_data = fastest_overall_lap.get_car_data()

            merged = pd.merge_asof(pos_data.sort_values("Time"), car_data.sort_values("Time"), on="Time")

            fig_map = go.Figure()
            fig_map.add_trace(
                go.Scatter(
                    x=merged["X"],
                    y=merged["Y"],
                    mode="markers",
                    marker=dict(
                        size=4,
                        color=merged["Speed"],
                        colorscale="Viridis",
                        colorbar=dict(title="Speed (km/h)"),
                        showscale=True,
                    ),
                    text=merged["Speed"].apply(lambda s: f"{s:.0f} km/h"),
                    hoverinfo="text",
                    name="Track",
                )
            )

            fig_map.update_layout(
                title=f"Track Map - {session.event.get('Location', 'Circuit')} (Fastest Lap by {fastest_overall_lap['Driver']})",
                template="plotly_dark",
                height=650,
                xaxis=dict(showgrid=False, zeroline=False, visible=False),
                yaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
                margin=dict(l=20, r=20, t=50, b=20),
            )

            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("No position data found for circuit mapping.")
    except Exception as e:
        st.warning(f"Track layout could not be rendered: {e}")

# ==========================================
# TAB 4: LAP TIME EVOLUTION
# ==========================================
with tab_lap_chart:
    st.subheader("⏱️ Lap Time Pace Across Session")
    try:
        valid_laps = session.laps.pick_quicklaps()
        if not valid_laps.empty:
            drivers_list = sorted(valid_laps["Driver"].unique())
            selected_drivers = st.multiselect(
                "Select Drivers to Compare",
                drivers_list,
                default=drivers_list[:min(4, len(drivers_list))],
            )

            if selected_drivers:
                fig_pace = go.Figure()
                for drv in selected_drivers:
                    drv_laps = valid_laps.pick_driver(drv)
                    try:
                        c = fastf1.plotting.driver_color(drv)
                    except Exception:
                        c = None

                    fig_pace.add_trace(
                        go.Scatter(
                            x=drv_laps["LapNumber"],
                            y=drv_laps["LapTime"].dt.total_seconds(),
                            mode="lines+markers",
                            name=drv,
                            line=dict(color=c, width=2) if c else dict(width=2),
                            marker=dict(size=5),
                        )
                    )

                fig_pace.update_layout(
                    title="Lap Time by Lap Number",
                    xaxis_title="Lap Number",
                    yaxis_title="Lap Time (Seconds)",
                    template="plotly_dark",
                    height=550,
                    hovermode="x unified",
                )
                st.plotly_chart(fig_pace, use_container_width=True)
            else:
                st.info("Please select at least one driver to plot lap times.")
        else:
            st.info("No quick laps recorded for pace analysis.")
    except Exception as e:
        st.warning(f"Could not render lap pace chart: {e}")

# --- Footer ---
st.markdown("---")
st.markdown(
    "<small style='color: grey;'>Built with FastF1 & Streamlit. Data is provided by Formula 1 via FastF1 API.</small>",
    unsafe_allow_html=True,
)
