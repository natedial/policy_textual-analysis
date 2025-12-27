import requests
from bs4 import BeautifulSoup
import spacy
from collections import Counter
import difflib
import pandas as pd
from sentence_transformers import SentenceTransformer, util

# Load Spacy model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None

# Load Sentence Transformer model
try:
    model = SentenceTransformer('all-MiniLM-L6-v2')
except Exception:
    model = None

def fetch_text(url):
    """Fetches and parses text from a Fed URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # This is a heuristic for Fed pages. Might need adjustment.
        # Usually content is in a specific div.
        # For now, let's grab all paragraphs.
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        return text.strip()
    except Exception as e:
        return f"Error fetching URL: {e}"

def process_text(text):
    """Tokenizes and analyzes text using Spacy."""
    if not nlp:
        return None
    # Increase max length just in case
    nlp.max_length = 2000000
    doc = nlp(text)
    return doc

def get_pos_counts(doc):
    """Extracts counts of adjectives and verbs."""
    if not doc:
        return {}
    
    adjs = [token.text.lower() for token in doc if token.pos_ == "ADJ"]
    verbs = [token.text.lower() for token in doc if token.pos_ == "VERB"]
    
    return {
        "adjectives": Counter(adjs),
        "verbs": Counter(verbs)
    }

def detect_shifts(doc1, doc2):
    """Identifies changes in adjectives and verbs between two docs."""
    if not doc1 or not doc2:
        return pd.DataFrame()

    counts1 = get_pos_counts(doc1)
    counts2 = get_pos_counts(doc2)
    
    shifts = []
    
    # Compare Adjectives
    all_adjs = set(counts1["adjectives"].keys()) | set(counts2["adjectives"].keys())
    for adj in all_adjs:
        c1 = counts1["adjectives"].get(adj, 0)
        c2 = counts2["adjectives"].get(adj, 0)
        if c1 != c2:
            shifts.append({"Type": "Adjective", "Word": adj, "Doc1 Count": c1, "Doc2 Count": c2, "Diff": c2 - c1})
            
    # Compare Verbs
    all_verbs = set(counts1["verbs"].keys()) | set(counts2["verbs"].keys())
    for verb in all_verbs:
        c1 = counts1["verbs"].get(verb, 0)
        c2 = counts2["verbs"].get(verb, 0)
        if c1 != c2:
            shifts.append({"Type": "Verb", "Word": verb, "Doc1 Count": c1, "Doc2 Count": c2, "Diff": c2 - c1})
            
    df = pd.DataFrame(shifts)
    if not df.empty:
        df = df.sort_values(by="Diff", key=abs, ascending=False)
    return df

def align_sentences(text1, text2):
    """
    Aligns sentences for comparison using semantic similarity.
    Returns a list of tuples (sent1, sent2, tag).
    Tags: Equal, Rephrased, Added, Removed
    """
    if not nlp or not model:
        # Fallback to simple diff if models aren't loaded
        return align_sentences_simple(text1, text2)
        
    doc1 = nlp(text1)
    doc2 = nlp(text2)
    
    sents1 = [s.text for s in doc1.sents if s.text.strip()]
    sents2 = [s.text for s in doc2.sents if s.text.strip()]
    
    if not sents1 or not sents2:
        return []

    # Compute embeddings
    embeddings1 = model.encode(sents1, convert_to_tensor=True)
    embeddings2 = model.encode(sents2, convert_to_tensor=True)
    
    # Compute cosine similarity
    cosine_scores = util.cos_sim(embeddings1, embeddings2)
    
    alignment = []
    used_j = set()
    
    for i, s1 in enumerate(sents1):
        best_score = -1
        best_j = -1
        
        for j, s2 in enumerate(sents2):
            if j in used_j:
                continue
            
            score = cosine_scores[i][j].item()
            if score > best_score:
                best_score = score
                best_j = j
        
        # Thresholds
        if best_score > 0.95: # Almost exact match
             alignment.append((s1, sents2[best_j], "Equal"))
             used_j.add(best_j)
        elif best_score > 0.75: # Rephrased
             alignment.append((s1, sents2[best_j], "Rephrased"))
             used_j.add(best_j)
        else:
             alignment.append((s1, None, "Removed"))
             
    # Check for added sentences (indices in sents2 not in used_j)
    # We need to insert them in roughly the right place, but for now appending or simple logic
    # A better approach is to iterate through both lists.
    # Let's try a different approach: align based on best matches sequentially?
    # For a simple PoC, let's just list the added ones at the end or try to interleave?
    # Interleaving is hard without a sequence alignment algo that uses similarity.
    # Let's stick to the simple greedy matching for now, but we need to handle "Added" better.
    
    # Actually, let's use the simple alignment as a base and then check similarity for "Changed" blocks?
    # No, the user wants semantic comparison.
    
    # Let's do a second pass for "Added"
    added_indices = [j for j in range(len(sents2)) if j not in used_j]
    for j in added_indices:
        alignment.append((None, sents2[j], "Added"))
        
    return alignment

def align_sentences_simple(text1, text2):
    """Original simple alignment based on difflib."""
    if not nlp:
        return []
    doc1 = nlp(text1)
    doc2 = nlp(text2)
    sents1 = [s.text for s in doc1.sents]
    sents2 = [s.text for s in doc2.sents]
    matcher = difflib.SequenceMatcher(None, sents1, sents2)
    alignment = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                alignment.append((sents1[i1+k], sents2[j1+k], "Equal"))
        elif tag == 'replace':
            len1 = i2 - i1
            len2 = j2 - j1
            min_len = min(len1, len2)
            for k in range(min_len):
                alignment.append((sents1[i1+k], sents2[j1+k], "Changed"))
            if len1 > len2:
                for k in range(min_len, len1):
                    alignment.append((sents1[i1+k], None, "Removed"))
            elif len2 > len1:
                for k in range(min_len, len2):
                    alignment.append((None, sents2[j1+k], "Added"))
        elif tag == 'delete':
            for k in range(i2 - i1):
                alignment.append((sents1[i1+k], None, "Removed"))
        elif tag == 'insert':
            for k in range(j2 - j1):
                alignment.append((None, sents2[j1+k], "Added"))
    return alignment

def group_alignment(alignment):
    """
    Groups contiguous alignment tuples with the same tag.
    Returns a list of (tag, list_of_tuples).
    """
    if not alignment:
        return []
    
    grouped = []
    current_tag = alignment[0][2]
    current_group = [alignment[0]]
    
    for item in alignment[1:]:
        tag = item[2]
        if tag == current_tag:
            current_group.append(item)
        else:
            grouped.append((current_tag, current_group))
            current_tag = tag
            current_group = [item]
            
    grouped.append((current_tag, current_group))
    return grouped
