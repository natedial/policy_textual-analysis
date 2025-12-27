# Fed Textual Change Tracker

A tool for tracking semantic shifts in Federal Reserve communications over time.

## Proof of Concept

The `/poc` directory contains a proof of concept that validates the semantic extraction approach:

### Setup

1. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your API key:
```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
# OR export it directly:
export ANTHROPIC_API_KEY=your_key_here
```

4. Run the PoC:
```bash
cd poc
python run_poc.py
```

This will:
- Extract semantic fingerprints from two Jefferson speeches
- Run consistency checks (same speech analyzed twice)
- Detect shifts between the speeches
- Verify evidence quotes
- Run negative control test
- Generate an HTML validation report

### What It Tests

**Extraction Consistency**: Does the same speech produce consistent semantic fingerprints across multiple runs?

**Evidence Verification**: Do all quoted passages actually exist in the source texts?

**Negative Control**: When comparing a speech to itself, are zero shifts detected?

**Shift Detection**: Can the tool identify meaningful semantic shifts (stance changes, emphasis shifts, orphaned concepts)?

### Output

The PoC generates `poc_report.html` with:
- Validation metrics
- All detected shifts with evidence
- Side-by-side comparison of theme changes
- Overall pass/fail status

## Current Status

✅ PoC implementation complete
⏳ Full pipeline (TBD)
⏳ Database integration (TBD)
⏳ Automated scraping (TBD)
