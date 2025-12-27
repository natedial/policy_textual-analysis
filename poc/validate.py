"""
Simple validation module for PoC.
Checks if evidence quotes actually exist in source texts.
"""

from typing import List, Dict, Any
from compare import Shift


def verify_quote(quote: str, source_text: str) -> bool:
    """Check if quote exists in source text."""
    # Simple substring check - good enough for PoC
    return quote.strip() in source_text


def verify_shift_evidence(
    shift: Shift,
    text_a: str,
    text_b: str
) -> Dict[str, Any]:
    """
    Verify evidence for a single shift.

    Returns:
        Dict with verification results
    """
    results = {
        "theme": shift.theme,
        "verified": True,
        "missing_quotes": []
    }

    # Check speech A quotes
    for quote in shift.evidence.speech_a_quotes:
        if not verify_quote(quote, text_a):
            results["verified"] = False
            results["missing_quotes"].append(("Speech A", quote))

    # Check speech B quotes
    for quote in shift.evidence.speech_b_quotes:
        if not verify_quote(quote, text_b):
            results["verified"] = False
            results["missing_quotes"].append(("Speech B", quote))

    return results


def verify_all_shifts(
    shifts: List[Shift],
    text_a: str,
    text_b: str
) -> Dict[str, Any]:
    """
    Verify evidence for all shifts.

    Returns:
        Summary of verification results
    """
    verified = 0
    failed = []

    for shift in shifts:
        result = verify_shift_evidence(shift, text_a, text_b)
        if result["verified"]:
            verified += 1
            shift.evidence.verified = True
        else:
            failed.append(result)

    return {
        "total": len(shifts),
        "verified": verified,
        "failed": len(failed),
        "failed_details": failed,
        "pass": len(failed) == 0
    }


def negative_control_test(extract_func, speech_url: str, api_key: str = None) -> Dict[str, Any]:
    """
    Compare speech to itself - should find zero shifts.
    """
    from compare import detect_shifts

    print("\n=== Negative Control: Comparing speech to itself ===")

    fp1 = extract_func(speech_url, run_id=1, api_key=api_key)
    fp2 = extract_func(speech_url, run_id=2, api_key=api_key)

    shifts = detect_shifts(fp1, fp2)
    high_significance = [s for s in shifts if s.significance == "HIGH"]

    passed = len(high_significance) == 0

    return {
        "passed": passed,
        "total_shifts": len(shifts),
        "high_significance_shifts": len(high_significance)
    }
