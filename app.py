import streamlit as st

import utils
from fed_tracker.query import QueryService
from fed_tracker.models import ComparisonType

st.set_page_config(layout="wide", page_title="Fed Textual Change Tracker")

st.title("Fed Textual Change Tracker")
st.markdown("Agent-first semantic comparison debug UI.")
st.caption(f"Extractor: {utils.extractor_label()}")
st.caption(f"Persistence: {'enabled' if utils.persistence_enabled() else 'disabled'}")

with st.sidebar:
    st.header("Compare URLs")
    base_url = st.text_input(
        "Baseline URL (t-1)",
        value="https://www.federalreserve.gov/newsevents/speech/powell20250107a.htm",
    )
    target_url = st.text_input(
        "Target URL (newest)",
        value="https://www.federalreserve.gov/newsevents/speech/powell20250129a.htm",
    )
    historical_urls_raw = st.text_area(
        "Historical context URLs (optional, one per line)",
        value="",
        help="Use this to simulate speaker context until stored history is available.",
        height=140,
    )
    persist_results = st.checkbox(
        "Persist analysis if DB is configured",
        value=utils.persistence_enabled(),
        disabled=not utils.persistence_enabled(),
    )
    run = st.button("Analyze")

if run:
    historical_urls = [line.strip() for line in historical_urls_raw.splitlines() if line.strip()]
    pipeline = utils.build_pipeline()
    with st.spinner("Fetching, normalizing, extracting, and comparing..."):
        try:
            base_bundle = pipeline.analyze_url(base_url)
            target_bundle = pipeline.analyze_url(
                target_url,
                historical_documents=[base_bundle.document],
            )
            manual_history = [base_bundle]
            for historical_url in historical_urls:
                manual_history.append(pipeline.analyze_url(historical_url))
            comparison = pipeline.compare_bundles(
                base_bundle=base_bundle,
                target_bundle=target_bundle,
                context_bundles=manual_history,
                comparison_type=ComparisonType.T_MINUS_1,
            )
            stored_result = None
            if persist_results and pipeline.database:
                stored_result = pipeline.store_bundle_with_comparisons(target_bundle)
        except Exception as exc:
            st.exception(exc)
        else:
            meta_col1, meta_col2 = st.columns(2)
            with meta_col1:
                st.subheader("Baseline Document")
                st.json(base_bundle.document.model_dump(mode="json"))
            with meta_col2:
                st.subheader("Target Document")
                st.json(target_bundle.document.model_dump(mode="json"))

            st.header("Comparison Summary")
            st.write(comparison.summary)
            if comparison.uncertainty_notes:
                st.info(" | ".join(comparison.uncertainty_notes))

            if stored_result and stored_result.persisted:
                st.success(
                    f"Stored target document {stored_result.persisted.document_id}, fingerprint {stored_result.persisted.fingerprint_id}, run {stored_result.persisted.analysis_run_id}."
                )
                if stored_result.context_summaries:
                    st.subheader("Stored Context Summaries")
                    st.json(stored_result.context_summaries)

            shift_df = utils.theme_changes_to_dataframe(comparison)
            if not shift_df.empty:
                st.subheader("Theme Changes")
                st.dataframe(shift_df, use_container_width=True)
            else:
                st.info("No theme changes detected.")

            context_col1, context_col2 = st.columns(2)
            with context_col1:
                st.subheader("Baseline Fingerprint")
                base_fp_df = utils.fingerprint_to_dataframe(base_bundle)
                if not base_fp_df.empty:
                    st.dataframe(base_fp_df, use_container_width=True)
                else:
                    st.info("No baseline themes extracted.")
            with context_col2:
                st.subheader("Target Fingerprint")
                target_fp_df = utils.fingerprint_to_dataframe(target_bundle)
                if not target_fp_df.empty:
                    st.dataframe(target_fp_df, use_container_width=True)
                else:
                    st.info("No target themes extracted.")

            st.subheader("Target Phrase Anomalies")
            phrase_df = utils.phrase_signals_to_dataframe(target_bundle)
            if not phrase_df.empty:
                st.dataframe(phrase_df, use_container_width=True)
            else:
                st.info("No phrase anomalies surfaced.")

            st.subheader("Structured Comparison Artifact")
            st.json(comparison.model_dump(mode="json"))

            if stored_result and stored_result.comparisons:
                st.subheader("Stored Comparison Artifacts")
                st.json({key: value.model_dump(mode="json") for key, value in stored_result.comparisons.items()})
                if pipeline.database and target_bundle.document.speaker_name:
                    st.subheader("Stored Speaker Brief")
                    brief = QueryService(database=pipeline.database).speaker_brief(target_bundle.document.speaker_name)
                    st.json(brief)
else:
    st.info("Provide a baseline and target URL to inspect the semantic pipeline.")
