"""app.py — Kronos Forecasting Dashboard (Streamlit).

A THIN client over forecast_engine + storage. No model/data logic lives here.

Design (SCOPE.md §5): minimalist black & white, monochrome, data-dense but not
cluttered. Uncertainty (the p10-p90 band) is the most visually prominent element.
A live theme switcher offers several grayscale themes. Honesty guardrails are
visible everywhere: no fabricated confidence score, distribution not point, the
model's blind spot is always shown, and accuracy is tracked over time.

Run:
    streamlit run app.py
    # GCP: streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

import forecast_engine as fe
import storage
import ui_theme
import news_context as nc
from instruments import all_instruments, get_instrument, INSTRUMENT_ORDER

st.set_page_config(
    page_title="Kronos Forecasting Dashboard",
    page_icon="◼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Defaults from env
# --------------------------------------------------------------------------- #
DEF_PRED_LEN = int(os.environ.get("DEFAULT_PRED_LEN", "30"))
DEF_N_SAMPLES = int(os.environ.get("DEFAULT_N_SAMPLES", "30"))
DEF_LOOKBACK = int(os.environ.get("DEFAULT_LOOKBACK", "400"))
DEVICE = os.environ.get("KRONOS_DEVICE", "cpu")


# --------------------------------------------------------------------------- #
# Cached resources
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Loading Kronos model (first run downloads weights)...")
def _get_predictor():
    return fe.load_predictor(device=DEVICE)


@st.cache_data(ttl=60 * 30, show_spinner=False)
def _cached_history(instrument_key: str, lookback_days: int) -> pd.DataFrame:
    df = fe.fetch_ohlcv(instrument_key, lookback_days=lookback_days)
    # carry attrs through the cache boundary
    df = df.copy()
    df["_ticker_used"] = df.attrs.get("ticker_used", "")
    df["_volume_reliable"] = df.attrs.get("volume_is_reliable", False)
    return df


def _run_and_log(instrument_key, lookback, pred_len, n_samples, T, top_p):
    """Run a forecast (expensive) and persist it. Cached per param-set + day."""
    res = fe.run_forecast(
        instrument_key,
        lookback=lookback,
        pred_len=pred_len,
        n_samples=n_samples,
        T=T,
        top_p=top_p,
        device=DEVICE,
        predictor=_get_predictor(),
    )
    try:
        storage.log_forecast(res)
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not log forecast: {exc}")
    return res


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def _cached_forecast_key(instrument_key, lookback, pred_len, n_samples, T, top_p, day_token):
    """Cache wrapper: a forecast is recomputed at most once per param-set per day.

    We cannot cache the ForecastResult (numpy/dataframe) trivially across reruns
    with full fidelity, so we store it in session_state keyed by these args and
    use this function only to gate recomputation via day_token.
    """
    return _run_and_log(instrument_key, lookback, pred_len, n_samples, T, top_p)


def get_forecast(instrument_key, lookback, pred_len, n_samples, T, top_p, force=False):
    day_token = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if force:
        _cached_forecast_key.clear()
    return _cached_forecast_key(instrument_key, lookback, pred_len, n_samples, T, top_p, day_token)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar():
    st.sidebar.markdown("## ◼ Kronos")
    st.sidebar.caption("Forecast distribution & calibration tool. Demo account.")

    theme_key = st.sidebar.selectbox(
        "Theme",
        options=ui_theme.THEME_ORDER,
        format_func=lambda k: ui_theme.get_theme(k).name,
        index=ui_theme.THEME_ORDER.index(st.session_state.get("theme", ui_theme.DEFAULT_THEME)),
    )
    st.session_state["theme"] = theme_key

    st.sidebar.divider()
    view = st.sidebar.radio("View", ["Single instrument", "All four at a glance"], index=0)

    inst_keys = INSTRUMENT_ORDER
    instrument_key = st.sidebar.selectbox(
        "Instrument",
        options=inst_keys,
        format_func=lambda k: get_instrument(k).display_name,
        index=0,
        disabled=(view != "Single instrument"),
    )

    st.sidebar.divider()
    st.sidebar.markdown("**Forecast settings**")
    lookback = st.sidebar.slider("Lookback (days, <=512)", 100, 512, DEF_LOOKBACK, step=20)
    pred_len = st.sidebar.slider("Forecast horizon (business days)", 5, 60, DEF_PRED_LEN, step=1)
    n_samples = st.sidebar.slider("Sample paths (distribution width)", 10, 80, DEF_N_SAMPLES, step=5)
    with st.sidebar.expander("Advanced sampling"):
        T = st.slider("Temperature (T)", 0.5, 1.5, 1.0, step=0.05)
        top_p = st.slider("top_p", 0.5, 1.0, 0.9, step=0.05)

    st.sidebar.divider()
    run_clicked = st.sidebar.button("Run forecast", use_container_width=True, type="primary")
    refresh_clicked = st.sidebar.button("Refresh actuals / accuracy", use_container_width=True)

    st.sidebar.divider()
    st.sidebar.caption("Honesty mode: bands not points, no confidence score, "
                       "the model sees price only.")

    return dict(view=view, instrument_key=instrument_key, lookback=lookback,
                pred_len=pred_len, n_samples=n_samples, T=T, top_p=top_p,
                run_clicked=run_clicked, refresh_clicked=refresh_clicked)


# --------------------------------------------------------------------------- #
# Components
# --------------------------------------------------------------------------- #
def header_strip(res, theme):
    inst = get_instrument(res.instrument_key)
    badges = []
    if not res.has_reliable_volume:
        badges.append(ui_theme.badge("LOW CONFIDENCE: no reliable volume", "warn"))
    if res.event_sensitive:
        badges.append(ui_theme.badge("EVENT-SENSITIVE: headlines not seen by model", "warn"))
    if res.used_volume_path:
        badges.append(ui_theme.badge("volume path", "line"))
    else:
        badges.append(ui_theme.badge("no-volume path", "soft"))

    st.markdown(f"## {res.display_name}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last close", f"{res.last_close:,.4f}")
    c2.metric("Ticker used", res.ticker_used)
    c3.metric("History as of", str(res.last_history_date.date()))
    c4.metric("Realized vol (ann.)", f"{res.realized_vol_annualized*100:,.1f}%")
    st.markdown(" ".join(badges), unsafe_allow_html=True)
    st.markdown(
        f'<div class="callout"><b>This is a forecast distribution, not a prediction.</b> '
        f'<span class="small">{inst.confidence_caveat} '
        f'The model sees past price candles only.</span></div>',
        unsafe_allow_html=True,
    )


def fan_chart(res, theme):
    """Recent history (line) + faint sample paths + p10-p90 band + median.

    The band is the most prominent element (filled), per the honesty brief.
    """
    fig = go.Figure()
    hist = res.history
    hist_x = pd.to_datetime(hist["timestamps"])
    fut_x = pd.to_datetime(pd.Series(res.future_timestamps))

    # p10-p90 band (most prominent): draw as filled area.
    fig.add_trace(go.Scatter(
        x=pd.concat([fut_x, fut_x[::-1]]),
        y=np.concatenate([res.p90, res.p10[::-1]]),
        fill="toself", fillcolor=theme.band, line=dict(color="rgba(0,0,0,0)"),
        name="p10-p90 band (80%)", hoverinfo="skip",
    ))
    # p25-p75 inner band
    fig.add_trace(go.Scatter(
        x=pd.concat([fut_x, fut_x[::-1]]),
        y=np.concatenate([res.p75, res.p25[::-1]]),
        fill="toself", fillcolor=theme.band_inner, line=dict(color="rgba(0,0,0,0)"),
        name="p25-p75 band (50%)", hoverinfo="skip",
    ))
    # Faint sample paths
    show_n = min(res.n_samples, 40)
    for i in range(show_n):
        fig.add_trace(go.Scatter(
            x=fut_x, y=res.sample_matrix[i],
            line=dict(color=theme.sample, width=1),
            showlegend=(i == 0), name="sample paths" if i == 0 else None,
            hoverinfo="skip",
        ))
    # Median (emphasis, dashed so it's clearly not "the answer")
    fig.add_trace(go.Scatter(
        x=fut_x, y=res.median, line=dict(color=theme.accent, width=2, dash="dash"),
        name="median (p50)",
    ))
    # History
    fig.add_trace(go.Scatter(
        x=hist_x, y=hist["close"], line=dict(color=theme.history, width=2),
        name="history (close)",
    ))
    # Last-close reference line
    fig.add_hline(y=res.last_close, line=dict(color=theme.muted, width=1, dash="dot"))

    layout = ui_theme.plotly_template(theme)["layout"].copy()
    layout.update(dict(
        height=460, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0),
        title=None,
    ))
    fig.update_layout(layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def horizon_table(res):
    df = res.horizon_table().copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.rename(columns={"date": "Date"})
    fmt = {c: "{:,.4f}" for c in df.columns if c != "Date"}
    st.markdown("**Daily forecast distribution** (NOT 'predicted price')")
    st.dataframe(df.style.format(fmt), use_container_width=True, hide_index=True)


def skew_panel(res, theme):
    sk = res.skew_metrics.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sk["horizon"], y=sk["downside"], name="downside (med - p10)",
        marker_color=theme.accent,
    ))
    fig.add_trace(go.Bar(
        x=sk["horizon"], y=sk["upside"], name="upside (p90 - med)",
        marker_color=theme.muted,
    ))
    layout = ui_theme.plotly_template(theme)["layout"].copy()
    layout.update(dict(height=260, barmode="group",
                       legend=dict(orientation="h", y=1.05),
                       xaxis_title="horizon (business days)"))
    fig.update_layout(layout)
    st.markdown("**Skew / downside-tail**")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown(f'<div class="callout">{res.skew_sentence()}</div>', unsafe_allow_html=True)


def prob_below_panel(res, theme):
    sk = res.skew_metrics.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sk["horizon"], y=sk["prob_below_last_close"] * 100,
        line=dict(color=theme.accent, width=2), name="% paths below current",
    ))
    fig.add_hline(y=50, line=dict(color=theme.muted, width=1, dash="dot"))
    layout = ui_theme.plotly_template(theme)["layout"].copy()
    layout.update(dict(height=260, yaxis_title="% below current price",
                       xaxis_title="horizon (business days)",
                       yaxis=dict(range=[0, 100], gridcolor=theme.grid)))
    fig.update_layout(layout)
    st.markdown("**Probability mass below current price**")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def news_panel(res):
    st.markdown("### Recent context the model did NOT see")
    st.caption("The model forecasts from price candles only. These are event types / "
               "headlines it cannot factor in. Shown for awareness, never as a forecast input.")
    ctx = nc.get_news_context(res.instrument_key, res.display_name)

    if ctx.blind_spots:
        chips = " ".join(ui_theme.badge(b, "soft") for b in ctx.blind_spots)
        st.markdown("**Blind spots for this instrument:** " + chips, unsafe_allow_html=True)

    if ctx.notice:
        st.info(ctx.notice)
    if ctx.items:
        for it in ctx.items:
            line = f"- [{it.title}]({it.url})" if it.url else f"- {it.title}"
            if it.source:
                line += f"  *({it.source})*"
            st.markdown(line)
    if ctx.tone_note:
        st.markdown(
            f'<div class="callout">LLM tone impression: <i>{ctx.tone_note}</i>'
            f'<br><span class="small">{nc.DISCLAIMER}</span></div>',
            unsafe_allow_html=True,
        )


def analysis_panel(res, accuracy):
    st.markdown("### Text analysis (bot)")
    text = nc.analyze_forecast_text(res, accuracy)
    st.markdown(text)
    narrative = nc.llm_narrative(res, accuracy)
    if narrative:
        with st.expander("LLM-phrased narrative (optional, unvalidated)"):
            st.markdown(narrative)


def accuracy_panel(res):
    st.markdown("### Accuracy so far")
    summary = storage.accuracy_summary(res.instrument_key)
    n = summary["n_reconciled"]
    if n == 0:
        st.info("No reconciled forecasts yet. Run forecasts daily, then use "
                "'Refresh actuals / accuracy' once target dates have passed.")
        return
    c1, c2, c3 = st.columns(3)
    hr = summary["band_hit_rate"]
    c1.metric("Band hit-rate (p10-p90)",
              f"{hr*100:,.0f}%" if hr is not None else "-",
              help="Headline calibration metric. Nominal target ~80%.")
    mae = summary["median_abs_error"]
    c2.metric("Median abs error", f"{mae:,.4f}" if mae is not None else "-")
    da = summary["directional_accuracy"]
    c3.metric("Directional accuracy", f"{da*100:,.0f}%" if da is not None else "-")
    st.markdown(f'<div class="callout">{summary["calibration_note"]}<br>'
                f'<span class="small">{n} reconciled forecast points so far. '
                f'Nominal band coverage is {summary["band_nominal"]*100:.0f}%.</span></div>',
                unsafe_allow_html=True)
    if summary["by_horizon"]:
        bh = pd.DataFrame(summary["by_horizon"])
        bh["hit_rate"] = (bh["hit_rate"] * 100).round(0)
        bh = bh.rename(columns={"horizon": "Horizon", "n": "N",
                                "hit_rate": "Hit-rate %",
                                "median_abs_error": "Median abs err"})
        with st.expander("Per-horizon calibration"):
            st.dataframe(bh, use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------- #
# Views
# --------------------------------------------------------------------------- #
def single_instrument_view(cfg, theme):
    key = cfg["instrument_key"]
    force = cfg["run_clicked"]
    try:
        res = get_forecast(key, cfg["lookback"], cfg["pred_len"], cfg["n_samples"],
                           cfg["T"], cfg["top_p"], force=force)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Forecast failed for {get_instrument(key).display_name}: {exc}")
        return

    accuracy = storage.accuracy_summary(key)

    header_strip(res, theme)
    st.divider()
    left, right = st.columns([2, 1])
    with left:
        fan_chart(res, theme)
    with right:
        horizon_table(res)
    st.divider()
    a, b = st.columns(2)
    with a:
        skew_panel(res, theme)
    with b:
        prob_below_panel(res, theme)
    st.divider()
    analysis_panel(res, accuracy)
    st.divider()
    news_panel(res)
    st.divider()
    accuracy_panel(res)


def glance_view(cfg, theme):
    st.markdown("## All four at a glance")
    st.caption("Scan each morning. Direction lean is the MEDIAN path only; the range is "
               "the real story. No confidence score is implied.")
    cols = st.columns(4)
    for col, inst in zip(cols, all_instruments()):
        with col:
            try:
                res = get_forecast(inst.key, cfg["lookback"], min(cfg["pred_len"], 7),
                                   cfg["n_samples"], cfg["T"], cfg["top_p"], force=False)
            except Exception as exc:  # noqa: BLE001
                st.markdown(f'<div class="glance-card"><div class="name">{inst.display_name}</div>'
                            f'<div class="sub">error: {exc}</div></div>', unsafe_allow_html=True)
                continue
            h = res.pred_len - 1
            lean = "flat"
            if res.median[h] > res.last_close * 1.001:
                lean = "lean up"
            elif res.median[h] < res.last_close * 0.999:
                lean = "lean down"
            flag = "LOW CONF" if not res.has_reliable_volume else (
                "EVENT" if res.event_sensitive else "OK")
            flag_kind = "warn" if flag != "OK" else "line"
            st.markdown(
                f'<div class="glance-card">'
                f'<div class="name">{res.display_name}</div>'
                f'<div class="sub">{res.ticker_used} · {ui_theme.badge(flag, flag_kind)}</div>'
                f'<div class="big">{res.last_close:,.4f}</div>'
                f'<div class="sub">1wk median ({lean})</div>'
                f'<div class="range">{res.median[h]:,.4f}</div>'
                f'<div class="sub">p10-p90 range</div>'
                f'<div class="range">{res.p10[h]:,.4f} &ndash; {res.p90[h]:,.4f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            spark = go.Figure()
            fut_x = list(range(1, res.pred_len + 1))
            spark.add_trace(go.Scatter(
                x=fut_x + fut_x[::-1],
                y=list(res.p90) + list(res.p10[::-1]),
                fill="toself", fillcolor=theme.band, line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip", showlegend=False))
            spark.add_trace(go.Scatter(x=fut_x, y=res.median,
                                       line=dict(color=theme.accent, width=2, dash="dash"),
                                       showlegend=False, hoverinfo="skip"))
            lay = ui_theme.plotly_template(theme)["layout"].copy()
            lay.update(dict(height=120, margin=dict(l=10, r=10, t=6, b=6),
                            xaxis=dict(visible=False), yaxis=dict(visible=False)))
            spark.update_layout(lay)
            st.plotly_chart(spark, use_container_width=True, config={"displayModeBar": False})


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    if "theme" not in st.session_state:
        st.session_state["theme"] = ui_theme.DEFAULT_THEME

    cfg = sidebar()
    theme = ui_theme.get_theme(st.session_state["theme"])
    st.markdown(ui_theme.css(theme), unsafe_allow_html=True)

    # Title row
    st.markdown("# ◼ Kronos Forecasting Dashboard")
    st.caption("Forecasting & forecast-quality measurement for a demo account. "
               "Honest about uncertainty by design.")

    if cfg["refresh_clicked"]:
        with st.spinner("Reconciling forecasts against realized actuals..."):
            n = storage.update_actuals()
        st.success(f"Reconciled {n} forecast point(s) against actuals.")

    if cfg["view"] == "All four at a glance":
        glance_view(cfg, theme)
    else:
        single_instrument_view(cfg, theme)


if __name__ == "__main__":
    main()
