"""
Chart helpers for the BrBaLab notebook.

One restrained palette: gray carries context, a single accent carries the thing
being pointed at, and red is reserved for relegation risk. Every static figure is
rendered twice (light and dark) so the README can swap them with <picture>.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

THEMES = {
    "light": {
        "surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e",
        "grid": "#e6e5e1", "context": "#c9c8c3",
        "series": ["#2a78d6", "#eb6834", "#1baf7a"], "critical": "#d03b3b",
    },
    "dark": {
        "surface": "#1a1a19", "text": "#ffffff", "muted": "#c3c2b7",
        "grid": "#33332f", "context": "#55544f",
        "series": ["#3987e5", "#d95926", "#199e70"], "critical": "#d03b3b",
    },
}
ACCENT = THEMES["light"]["series"][0]


def _style(ax, t):
    ax.set_facecolor(t["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(t["grid"])
    ax.tick_params(colors=t["muted"], labelsize=10)
    ax.grid(axis="y", color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def team_rating_history(games):
    """Long table (date, team, rating) from the processed games: one row per team per match."""
    home = games[["date", "home_team", "home_rating"]].set_axis(["date", "team", "rating"], axis=1)
    away = games[["date", "away_team", "away_rating"]].set_axis(["date", "team", "rating"], axis=1)
    out = pd.concat([home, away], ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values("date", kind="stable").reset_index(drop=True)


def fifa_ratings_figure(history, highlight, context_n=20, mode="light", start="2019-01-01"):
    """Rating evolution: the top `context_n` teams in gray, `highlight` teams in color."""
    t = THEMES[mode]
    history = history[history["date"] >= start]
    latest = history.groupby("team").tail(1).sort_values("rating", ascending=False)
    context = latest["team"].head(context_n).tolist()

    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=150)
    fig.patch.set_facecolor(t["surface"])
    _style(ax, t)
    for team in context:
        if team in highlight:
            continue
        h = history[history["team"] == team]
        ax.plot(h["date"], h["rating"], color=t["context"], linewidth=1, alpha=0.9)
    ends = []
    for i, team in enumerate(highlight):
        h = history[history["team"] == team]
        ax.plot(h["date"], h["rating"], color=t["series"][i], linewidth=2)
        ends.append([h["rating"].iloc[-1], team, h["date"].iloc[-1]])
    # Direct labels at the line ends, nudged apart so they never overlap
    ymin, ymax = ax.get_ylim()
    gap = (ymax - ymin) * 0.045
    ends.sort(reverse=True)
    for k in range(1, len(ends)):
        ends[k][0] = min(ends[k][0], ends[k - 1][0] - gap)
    for y, team, x in ends:
        ax.annotate(team, (x, y), xytext=(8, 0), textcoords="offset points", va="center",
                    color=t["text"], fontsize=10, fontweight="bold", annotation_clip=False)
    ax.set_title(f"National-team ratings since 2019 — top {context_n} teams in gray",
                 loc="left", color=t["text"], fontsize=13, pad=22)
    ax.text(0, 1.015, "2018 is left out: every team starts at 1000 and the filter needs a few months to settle.",
            transform=ax.transAxes, color=t["muted"], fontsize=9)
    ax.set_ylabel("Rating", color=t["muted"])
    fig.tight_layout()
    return fig


def season_simulation_figure(current, gameweek, last_played, mode="light"):
    """
    The table the simulation starts from (points, in gray) next to three small multiples:
    P(champion), P(top 4), P(relegation). Teams in table order.
    """
    t = THEMES[mode]
    table = current.sort_values("league_rating")
    teams = table["team"].tolist()[::-1]
    by_team = table.set_index("team").loc[teams]
    panels = [("points", "Points", t["context"]),
              ("champion", "Champion", t["series"][0]),
              ("champions_league", "Top 4", t["series"][0]),
              ("relegation_to_EFL", "Relegation", t["critical"])]

    fig, axes = plt.subplots(1, 4, figsize=(13, 6.6), dpi=150, sharey=True,
                             gridspec_kw={"width_ratios": [0.8, 1, 1, 1]})
    fig.patch.set_facecolor(t["surface"])
    for ax, (col, label, color) in zip(axes, panels):
        _style(ax, t)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=t["grid"], linewidth=0.8)
        values = by_team[col]
        ax.barh(teams, values, color=color, height=0.7)
        if col == "points":
            for y, (v, rec) in enumerate(zip(values, by_team["record"])):
                ax.text(v + 0.2, y, f"{v:.0f}  ({rec})", va="center", fontsize=8, color=t["muted"])
            ax.set_xlim(0, values.max() + 4)
            ax.set_title(f"{label} after GW{gameweek}", loc="left", color=t["text"], fontsize=11)
        else:
            for y, v in enumerate(values):
                if v >= 1:
                    ax.text(v + 1.5, y, f"{v:.0f}%", va="center", fontsize=8, color=t["muted"])
            ax.set_xlim(0, 105)
            ax.set_title(label, loc="left", color=t["text"], fontsize=11)
        ax.tick_params(axis="y", labelcolor=t["text"])
    fig.suptitle(f"Premier League 2025-26 — table after gameweek {gameweek} (games up to {last_played:%d %b %Y}) "
                 "and 1,000 simulated seasons from it",
                 x=0.01, ha="left", color=t["text"], fontsize=13)
    fig.tight_layout()
    return fig


def save_light_dark(make_figure, name, out_dir="assets"):
    """Render `make_figure(mode)` in both themes to assets/<name>_{light,dark}.png."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for mode in ("light", "dark"):
        fig = make_figure(mode)
        path = out / f"{name}_{mode}.png"
        fig.savefig(path, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths


def fifa_ratings_plotly(history, teams):
    """Interactive version of the rating chart for the explorer (Colab/Jupyter only)."""
    import plotly.graph_objects as go

    t = THEMES["light"]
    fig = go.Figure()
    for i, team in enumerate(teams):
        h = history[history["team"] == team]
        color = t["series"][i] if i < len(t["series"]) else t["context"]
        fig.add_trace(go.Scatter(x=h["date"], y=h["rating"], name=team, mode="lines",
                                 line=dict(width=2, color=color),
                                 hovertemplate="%{x|%d %b %Y}<br>%{y:.0f}<extra>" + team + "</extra>"))
    fig.update_layout(template="simple_white", height=420, hovermode="x unified",
                      margin=dict(l=40, r=20, t=40, b=40),
                      title="Rating evolution", yaxis_title="Rating")
    return fig
