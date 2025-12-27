import streamlit as st
import utils
import pandas as pd

st.set_page_config(layout="wide", page_title="Fed Textual Comparison Tool")

st.title("Fed Textual Comparison Tool (PoC)")
st.markdown("Compare two Federal Reserve documents to detect linguistic shifts.")

# Sidebar for inputs
with st.sidebar:
    st.header("Configuration")
    url1 = st.text_input("URL 1", value="https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20251029.pdf")
    url2 = st.text_input("URL 2", value="https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20251210.pdf")
    
    if st.button("Compare"):
        with st.spinner("Fetching and processing..."):
            text1 = utils.fetch_text(url1)
            text2 = utils.fetch_text(url2)
            
            if "Error" in text1 or "Error" in text2:
                st.error("Error fetching URLs. Please check them.")
            else:
                st.session_state.text1 = text1
                st.session_state.text2 = text2
                st.session_state.processed = True

if st.session_state.get("processed"):
    doc1 = utils.process_text(st.session_state.text1)
    doc2 = utils.process_text(st.session_state.text2)
    
    # Linguistic Shifts
    st.header("Linguistic Shifts")
    shifts_df = utils.detect_shifts(doc1, doc2)
    if not shifts_df.empty:
        st.dataframe(shifts_df, use_container_width=True)
    else:
        st.info("No significant shifts detected or model not loaded.")
        
    # Text Comparison
    st.header("Text Comparison")
    
    # Align sentences
    alignment = utils.align_sentences(st.session_state.text1, st.session_state.text2)
    
    col1, col2 = st.columns(2)
    
    # Group alignment
    grouped_alignment = utils.group_alignment(alignment)
    
    with col1:
        st.subheader("Document 1")
        for tag, group in grouped_alignment:
            if tag == "Equal":
                for s1, s2, _ in group:
                    st.write(s1)
            else:
                with st.expander(f"{tag} ({len(group)} sentences)"):
                    for s1, s2, _ in group:
                        if s1:
                            if tag == "Removed":
                                st.markdown(f"<span style='background-color: #ffcccc; padding: 2px;'>{s1}</span>", unsafe_allow_html=True)
                            elif tag == "Changed":
                                st.markdown(f"<span style='background-color: #fff5cc; padding: 2px;'>{s1}</span>", unsafe_allow_html=True)
                            elif tag == "Rephrased":
                                st.markdown(f"<span style='background-color: #cce5ff; padding: 2px;'>{s1}</span>", unsafe_allow_html=True)
                            else:
                                st.write(s1)
                    
    with col2:
        st.subheader("Document 2")
        for tag, group in grouped_alignment:
            if tag == "Equal":
                for s1, s2, _ in group:
                    st.write(s2)
            else:
                with st.expander(f"{tag} ({len(group)} sentences)"):
                    for s1, s2, _ in group:
                        if s2:
                            if tag == "Added":
                                st.markdown(f"<span style='background-color: #ccffcc; padding: 2px;'>{s2}</span>", unsafe_allow_html=True)
                            elif tag == "Changed":
                                st.markdown(f"<span style='background-color: #fff5cc; padding: 2px;'>{s2}</span>", unsafe_allow_html=True)
                            elif tag == "Rephrased":
                                st.markdown(f"<span style='background-color: #cce5ff; padding: 2px;'>{s2}</span>", unsafe_allow_html=True)
                            else:
                                st.write(s2)

