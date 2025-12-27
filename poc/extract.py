"""
Semantic fingerprint extraction module.
Extracts structured semantic representations from Fed speeches.
"""

import json
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import anthropic
import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
from io import BytesIO


class ThemeFingerprint(BaseModel):
    """Semantic fingerprint for a single theme."""
    stance: str
    trajectory: str
    emphasis_score: int = Field(ge=1, le=10)
    hedging_level: str
    key_hedges: list[str]
    confidence: str
    key_passages: list[str]


class PolicyImplications(BaseModel):
    """Policy implications extracted from speech."""
    direction: str
    intensity: int = Field(ge=1, le=10)
    conditionality: str


class SemanticFingerprint(BaseModel):
    """Complete semantic fingerprint of a speech."""
    speech_url: str
    speech_text: str
    run_id: int
    themes: Dict[str, ThemeFingerprint]
    policy_implications: PolicyImplications
    overall_tone: str
    raw_llm_response: str


def fetch_speech_text(url: str) -> str:
    """
    Fetch and clean text from a Fed speech URL (HTML or PDF).

    Args:
        url: URL of the Fed speech

    Returns:
        Cleaned speech text
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Check if it's a PDF
        if url.endswith('.pdf') or 'application/pdf' in response.headers.get('Content-Type', ''):
            # Extract text from PDF
            pdf_reader = PdfReader(BytesIO(response.content))
            text_parts = []
            for page in pdf_reader.pages:
                text_parts.append(page.extract_text())

            text = "\n\n".join(text_parts)

            # Clean up PDF text (remove excessive whitespace)
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            text = "\n\n".join(lines)

            return text

        # Otherwise treat as HTML
        soup = BeautifulSoup(response.content, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()

        # Get all text
        all_text = soup.get_text()

        # Split into lines and filter
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]

        # Find the actual speech content
        # Usually starts after location/date info and ends before "Last Update"
        content_lines = []
        in_content = False

        for i, line in enumerate(lines):
            # Speech typically starts after we see phrases like these
            if not in_content and ('Thank you' in line or 'Good morning' in line or
                                   'Good afternoon' in line or 'Good evening' in line or
                                   (i > 0 and len(line) > 100)):  # Long paragraphs likely content
                in_content = True

            # Stop at footer markers
            if in_content and ('Last Update' in line or 'Back to Top' in line or
                              'Return to text' in line):
                break

            # Collect content lines
            if in_content and len(line) > 20:  # Filter out short navigation items
                content_lines.append(line)

        text = "\n\n".join(content_lines)

        # If we didn't get enough content, fall back to all paragraphs
        if len(text) < 500:
            paragraphs = soup.find_all('p')
            text = "\n\n".join([p.get_text().strip() for p in paragraphs
                               if p.get_text().strip() and len(p.get_text().strip()) > 20])

        return text

    except Exception as e:
        raise Exception(f"Error fetching speech from {url}: {e}")


def extract_fingerprint(
    speech_url: str,
    run_id: int = 1,
    api_key: Optional[str] = None
) -> SemanticFingerprint:
    """
    Extract semantic fingerprint from a speech.

    Args:
        speech_url: URL of the speech to analyze
        run_id: Run identifier for consistency checking
        api_key: Anthropic API key (if not in environment)

    Returns:
        SemanticFingerprint object
    """
    # Fetch speech text
    print(f"[Run {run_id}] Fetching speech from {speech_url}...")
    speech_text = fetch_speech_text(speech_url)
    print(f"[Run {run_id}] Fetched {len(speech_text)} characters")

    # Load extraction prompt
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "prompts",
        "extraction_prompt.txt"
    )
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()

    prompt = prompt_template.format(speech_text=speech_text)

    # Call Claude API
    print(f"[Run {run_id}] Extracting semantic fingerprint...")
    client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4000,
        temperature=0,  # Maximum consistency
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    # Parse response
    raw_response = response.content[0].text
    print(f"[Run {run_id}] Received response, parsing...")

    # Extract JSON from response (handle markdown code blocks)
    json_str = raw_response
    if "```json" in raw_response:
        json_str = raw_response.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_response:
        json_str = raw_response.split("```")[1].split("```")[0].strip()

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        print(f"Raw response: {raw_response[:500]}...")
        raise

    # Convert to Pydantic model
    themes = {
        theme_name: ThemeFingerprint(**theme_data)
        for theme_name, theme_data in parsed.get("themes", {}).items()
    }

    policy_impl = PolicyImplications(**parsed["policy_implications"])

    fingerprint = SemanticFingerprint(
        speech_url=speech_url,
        speech_text=speech_text,
        run_id=run_id,
        themes=themes,
        policy_implications=policy_impl,
        overall_tone=parsed.get("overall_tone", ""),
        raw_llm_response=raw_response
    )

    print(f"[Run {run_id}] Extraction complete. Found {len(themes)} themes.")
    return fingerprint


def calculate_consistency(fp1: SemanticFingerprint, fp2: SemanticFingerprint) -> Dict[str, Any]:
    """
    Calculate consistency between two fingerprints of the same speech.

    Args:
        fp1: First fingerprint
        fp2: Second fingerprint

    Returns:
        Dictionary with consistency metrics
    """
    # Check theme overlap
    themes1 = set(fp1.themes.keys())
    themes2 = set(fp2.themes.keys())

    theme_overlap = len(themes1 & themes2) / max(len(themes1 | themes2), 1)

    # Check stance consistency for overlapping themes
    stance_matches = 0
    trajectory_matches = 0
    emphasis_diffs = []

    for theme in themes1 & themes2:
        t1 = fp1.themes[theme]
        t2 = fp2.themes[theme]

        if t1.stance == t2.stance:
            stance_matches += 1
        if t1.trajectory == t2.trajectory:
            trajectory_matches += 1
        emphasis_diffs.append(abs(t1.emphasis_score - t2.emphasis_score))

    overlap_count = len(themes1 & themes2)
    stance_consistency = stance_matches / max(overlap_count, 1)
    trajectory_consistency = trajectory_matches / max(overlap_count, 1)
    avg_emphasis_diff = sum(emphasis_diffs) / max(len(emphasis_diffs), 1)

    # Check policy implications consistency
    policy_match = fp1.policy_implications.direction == fp2.policy_implications.direction

    # Overall consistency score
    overall_consistency = (
        theme_overlap * 0.3 +
        stance_consistency * 0.3 +
        trajectory_consistency * 0.2 +
        (1 - avg_emphasis_diff / 10) * 0.1 +
        (1.0 if policy_match else 0.0) * 0.1
    )

    return {
        "overall_consistency": overall_consistency,
        "theme_overlap": theme_overlap,
        "stance_consistency": stance_consistency,
        "trajectory_consistency": trajectory_consistency,
        "avg_emphasis_diff": avg_emphasis_diff,
        "policy_direction_match": policy_match,
        "themes_run1": sorted(themes1),
        "themes_run2": sorted(themes2),
        "themes_both": sorted(themes1 & themes2),
        "themes_only_run1": sorted(themes1 - themes2),
        "themes_only_run2": sorted(themes2 - themes1)
    }


if __name__ == "__main__":
    # Test extraction
    test_url = "https://www.federalreserve.gov/newsevents/speech/jefferson20251107a.htm"

    print("Testing extraction module...")
    fp = extract_fingerprint(test_url, run_id=1)
    print(f"\nExtracted themes: {list(fp.themes.keys())}")
    print(f"Policy direction: {fp.policy_implications.direction}")
    print(f"Overall tone: {fp.overall_tone}")
