"""Minimal Streamlit dashboard for hawk–dove rankings, trends, and coverage."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from hawk_dove.aggregation import (
    DEFAULT_HALF_LIFE_DAYS,
    DEFAULT_WINDOW_DAYS,
    aggregate_committee,
    ranked_officials,
)
from hawk_dove.discovery import discover_new_urls
from hawk_dove.officials import OfficialsDirectory
from hawk_dove.pipeline import HawkDovePipeline
from hawk_dove.scoring import HeuristicHawkDoveScorer

st.set_page_config(layout="wide", page_title="Fed Hawk–Dove Tracker")

st.title("Fed Hawk–Dove Tracker")
st.caption(
    "Independent research estimates on a 0–10 hawk–dove scale. "
    "Not affiliated with Deutsche Bank or the Federal Reserve. Not investment advice."
)

officials = OfficialsDirectory()
pipeline = HawkDovePipeline(scorer=HeuristicHawkDoveScorer(), officials=officials)

with st.sidebar:
    st.header("Score inputs")
    mode = st.radio("Input", ["Curated validation set", "Markdown paste", "Discover URLs"])
    as_of = st.date_input("As-of date", value=date.today())
    window_days = st.slider("Window (days)", min_value=30, max_value=180, value=DEFAULT_WINDOW_DAYS)
    half_life = st.slider("EWMA half-life (days)", min_value=7, max_value=60, value=int(DEFAULT_HALF_LIFE_DAYS))
    run = st.button("Run")

observations = []

if run:
    if mode == "Curated validation set":
        manifest = json.loads(Path("examples/hawk_dove/validation_set.json").read_text())
        for item in manifest["items"]:
            text = Path(item["path"]).read_text()
            scored = pipeline.score_markdown(text, metadata=item.get("metadata") or {})
            observations.append(scored.observation)
    elif mode == "Markdown paste":
        text = st.session_state.get("paste_text") or ""
        meta_raw = st.session_state.get("paste_meta") or "{}"
        metadata = json.loads(meta_raw) if meta_raw else {}
        if text.strip():
            observations.append(pipeline.score_markdown(text, metadata=metadata).observation)
    else:
        discovered = discover_new_urls(source_families=["board", "nyfed"])
        st.write(f"Discovered {len(discovered)} candidate URLs (Board + NY Fed). Scoring first 3 for demo.")
        for item in discovered[:3]:
            try:
                observations.append(pipeline.score_url(item.url).observation)
            except Exception as exc:  # network may fail in restricted envs
                st.warning(f"Could not score {item.url}: {exc}")

if mode == "Markdown paste":
    st.text_area("Communication text", key="paste_text", height=220)
    st.text_input(
        "Metadata JSON",
        key="paste_meta",
        value='{"speaker_name": "Jerome H. Powell", "speech_date": "2025-06-18", "document_type": "speech"}',
    )

if observations:
    ranks = ranked_officials(
        observations,
        as_of_date=as_of,
        window_days=window_days,
        half_life_days=float(half_life),
        officials=officials,
    )
    all_participants = aggregate_committee(
        observations,
        as_of_date=as_of,
        cohort="all_participants",
        window_days=window_days,
        half_life_days=float(half_life),
        officials=officials,
    )
    voters = aggregate_committee(
        observations,
        as_of_date=as_of,
        cohort="voters",
        window_days=window_days,
        half_life_days=float(half_life),
        officials=officials,
    )
    prior = aggregate_committee(
        observations,
        as_of_date=as_of - timedelta(days=45),
        cohort="voters",
        window_days=window_days,
        half_life_days=float(half_life),
        officials=officials,
    )
    delta = None
    if voters.overall_score is not None and prior.overall_score is not None:
        delta = round(voters.overall_score - prior.overall_score, 3)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Committee average", all_participants.overall_score if all_participants.overall_score is not None else "n/a")
    c2.metric("Voting-member average", voters.overall_score if voters.overall_score is not None else "n/a")
    c3.metric("Change vs prior window mid-point", delta if delta is not None else "n/a")
    c4.metric(
        "Coverage",
        f"{all_participants.official_count} officials / {all_participants.communication_count} docs",
    )

    if all_participants.coverage_notes.get("officials_missing_scores"):
        st.warning(
            f"Missing scores for {all_participants.coverage_notes['officials_missing_scores']} expected participants "
            "in the selected window."
        )

    st.subheader("Ranked officials")
    rank_df = pd.DataFrame(
        [
            {
                "official": row.speaker_name,
                "score": row.overall_score,
                "communications": row.communication_count,
                "voter": row.was_voter,
                "inflation": row.inflation_score,
                "labor": row.labor_score,
                "growth": row.growth_score,
                "policy_action": row.policy_action_score,
            }
            for row in ranks
            if row.overall_score is not None
        ]
    )
    if not rank_df.empty:
        st.dataframe(rank_df, use_container_width=True)
        st.bar_chart(rank_df.set_index("official")["score"])
    else:
        st.info("No qualifying scored officials in the selected window.")

    st.subheader("Recent communications")
    obs_df = pd.DataFrame(
        [
            {
                "speaker": obs.speaker_name,
                "date": obs.speech_date,
                "overall": None if obs.score.insufficient_policy_content else obs.score.overall_score,
                "confidence": obs.score.confidence,
                "insufficient": obs.score.insufficient_policy_content,
                "rationale": obs.score.rationale,
                "source": obs.source_url,
            }
            for obs in observations
        ]
    )
    st.dataframe(obs_df, use_container_width=True)

    st.subheader("Evidence and rationale")
    for obs in observations:
        label = f"{obs.speaker_name or 'Unknown'} — {obs.speech_date or 'undated'}"
        with st.expander(label):
            st.write(obs.score.rationale)
            st.json(obs.score.model_dump(mode="json"))
else:
    st.info("Configure inputs in the sidebar and click Run.")
