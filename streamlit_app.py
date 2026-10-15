import os
import tempfile
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import fastf1
import fastf1.plotting

# Page Configuration
st.set_page_config(
    page_title="F1 Race & Telemetry Dashboard",
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
    </style>
    """,
    unsafe_allow_html=True,
)

# Robust Cache directory setup using OS temp directory (works cleanly on Streamlit Cloud)
CACHE_DIR = os.path.join(tempfile.gettempdir(), "fastf1_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
    fastf1.Cache.enable_cache(CACHE_DIR)
except Exception:
    pass


@st.cache_data(show_spinner=False)
def get_schedule(year: int):
    """Fetch event schedule for given year."""
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        schedule = schedule[schedule["RoundNumber"] > 0]
        return schedule
    except Exception as e:
        st.error(f"Failed to load schedule for {year}: {e}")
        return pd.DataFrame()


@st.cache_resource(show_spinner=True)
def load_session_data(year: int, round_number: int, session_name: str):
    """Load and prepare a FastF1 session in-memory without pickle serialization."""
    session = fastf1.get_session(year, round_number, session_name)
    try:
        session.load(telemetry=True, laps=True, weather=True)
    except Exception:
        try:
            session.load(telemetry=False, laps=True, weather=False)
        except Exception:
            try:
                session.load(telemetry=False, laps=False, weather=False)
            except Exception:
                pass
    return session


def safe_get_laps(session):
    """Safely retrieve session laps without throwing DataNotLoadedError."""
    try:
        laps = session.laps
        if laps is not None and not laps.empty:
            return laps
    except Exception:
        pass
    return None


def safe_get_results(session):
    """Safely retrieve session results without throwing DataNotLoadedError."""
    try:
        results = session.results
        if results is not None and not results.empty:
            return results
    except Exception:
        pass
    return None


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
    selected_event_name = st.sidebar.selectbox("Grand Prix", event_names, index=0)
    event_row = schedule[schedule["EventName"] == selected_event_name].iloc[0]
    round_number = int(event_row["RoundNumber"])

    # Extract actual available sessions for this specific Grand Prix
    available_sessions = []
    for i in range(1, 6):
        col_name = f"Session{i}"
        if col_name in event_row and pd.notna(event_row[col_name]) and str(event_row[col_name]).strip():
            available_sessions.append(str(event_row[col_name]).strip())

    if not available_sessions:
        available_sessions = ["Race", "Qualifying", "Practice 1"]

    # Default to 'Race' if present, otherwise the last session
    default_session_idx = available_sessions.index("Race") if "Race" in available_sessions else len(available_sessions) - 1
    selected_session = st.sidebar.selectbox("Session", available_sessions, index=default_session_idx)
else:
    selected_event_name = "Bahrain Grand Prix"
    round_number = 1
    selected_session = "Race"

st.sidebar.markdown("---")
st.sidebar.info("💡 **Tip:** Session data is loaded from the FastF1 API and cached in memory for quick navigation.")

# --- Load Session ---
try:
    with st.spinner(f"Loading {selected_year} {selected_event_name} - {selected_session}..."):
        session = load_session_data(selected_year, round_number, selected_session)
except Exception as e:
    st.error(f"Could not load session data: {e}")
    st.info("Try selecting a different completed session or year.")
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
    st.metric("Session", selected_session)

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
    st.subheader(f"🏁 {selected_session} Classification")
    results = safe_get_results(session)
    if results is not None:
        try:
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
        except Exception as err:
            st.error(f"Error rendering results table: {err}")
    else:
        st.warning("No classification results found for this session.")

# ==========================================
# TAB 2: TELEMETRY COMPARISON
# ==========================================
with tab_telemetry:
    st.subheader("⚡ Head-to-Head Fastest Lap Telemetry")
    laps = safe_get_laps(session)
    if laps is not None:
        drivers = sorted([d for d in laps["Driver"].unique() if pd.notna(d)])
        if drivers:
            c1, c2 = st.columns(2)
            with c1:
                driver1 = st.selectbox("Driver 1", drivers, index=0, key="d1")
            with c2:
                default_d2_idx = 1 if len(drivers) > 1 else 0
                driver2 = st.selectbox("Driver 2", drivers, index=default_d2_idx, key="d2")

            try:
                lap_d1 = laps.pick_driver(driver1).pick_fastest()
                lap_d2 = laps.pick_driver(driver2).pick_fastest()
            except Exception:
                lap_d1, lap_d2 = None, None

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

                    # Brake
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
                    st.warning(f"Could not load detailed telemetry channels: {e}")
            else:
                st.info("Fastest lap telemetry is unavailable for one or both selected drivers.")
        else:
            st.info("No drivers found in lap data for this session.")
    else:
        st.warning("⚠️ Lap telemetry is not available for this session. Please select a completed session.")

# ==========================================
# TAB 3: TRACK MAP & SPEEDS
# ==========================================
with tab_track:
    st.subheader("🗺️ Circuit Layout & Speed Heatmap")
    laps = safe_get_laps(session)
    if laps is not None:
        try:
            fastest_overall_lap = laps.pick_fastest()
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
                    title=f"Track Map - {session.event.get('Location', 'Circuit')} (Fastest Lap: {fastest_overall_lap['Driver']})",
                    template="plotly_dark",
                    height=650,
                    xaxis=dict(showgrid=False, zeroline=False, visible=False),
                    yaxis=dict(showgrid=False, zeroline=False, visible=False, scaleanchor="x", scaleratio=1),
                    margin=dict(l=20, r=20, t=50, b=20),
                )

                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.info("No fastest lap recorded for track mapping.")
        except Exception as e:
            st.warning(f"Track layout could not be rendered: {e}")
    else:
        st.warning("⚠️ Track mapping requires lap telemetry data which is not available for this session.")

# ==========================================
# TAB 4: LAP TIME EVOLUTION
# ==========================================
with tab_lap_chart:
    st.subheader("⏱️ Lap Time Pace Across Session")
    laps = safe_get_laps(session)
    if laps is not None:
        try:
            valid_laps = laps.pick_quicklaps()
            if not valid_laps.empty:
                drivers_list = sorted([d for d in valid_laps["Driver"].unique() if pd.notna(d)])
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
    else:
        st.warning("⚠️ Lap pace analysis requires lap timing data which is not available for this session.")

# --- Footer ---
st.markdown("---")
st.markdown(
    "<small style='color: grey;'>Built with FastF1 & Streamlit. Data is provided by Formula 1 via FastF1 API.</small>",
    unsafe_allow_html=True,
)
