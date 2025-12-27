"""
PoC Orchestrator
Runs the complete proof of concept and generates validation report.
"""

import os
import sys
from html import escape as html_escape
from datetime import datetime
from extract import extract_fingerprint, calculate_consistency
from compare import detect_shifts
from validate import verify_all_shifts, negative_control_test


def generate_html_report(
    url_a: str,
    url_b: str,
    consistency: dict,
    shifts: list,
    verification: dict,
    negative_control: dict,
    output_path: str
):
    """Generate simple HTML report."""

    # Build shifts summary table
    shifts_table_rows = ""
    for shift in shifts:
        sig_color = {
            "HIGH": "#dc3545",
            "MEDIUM": "#ffc107",
            "LOW": "#6c757d"
        }.get(shift.significance, "#6c757d")

        # Build change description
        changes = []
        if shift.from_state and shift.to_state:
            if shift.from_state["stance"] != shift.to_state["stance"]:
                changes.append(f'{shift.from_state["stance"]} → {shift.to_state["stance"]}')
            if shift.from_state["trajectory"] != shift.to_state["trajectory"]:
                changes.append(f'Trajectory: {shift.from_state["trajectory"]} → {shift.to_state["trajectory"]}')

            emphasis_diff = shift.to_state["emphasis"] - shift.from_state["emphasis"]
            if emphasis_diff != 0:
                arrow = "↑" if emphasis_diff > 0 else "↓"
                color_class = "emphasis-up" if emphasis_diff > 0 else "emphasis-down"
                changes.append(f'<span class="{color_class}">Emphasis: {shift.from_state["emphasis"]} → {shift.to_state["emphasis"]} {arrow}</span>')
        elif shift.from_state:
            changes.append("Theme dropped")
        elif shift.to_state:
            changes.append(f'New theme (emphasis: {shift.to_state["emphasis"]}/10)')

        changes_html = "<br>".join(changes) if changes else "—"

        shifts_table_rows += f"""
        <tr>
            <td><strong>{html_escape(shift.theme)}</strong></td>
            <td>{html_escape(shift.shift_type)}</td>
            <td><span class="sig-badge-small" style="background-color: {sig_color}">{html_escape(shift.significance)}</span></td>
            <td>{changes_html}</td>
        </tr>
        """

    # Build shifts HTML (detailed cards)
    shifts_html = ""
    for shift in shifts:
        evidence_a = "<br>".join([f"<em>\"{html_escape(q)}\"</em>" for q in shift.evidence.speech_a_quotes])
        evidence_b = "<br>".join([f"<em>\"{html_escape(q)}\"</em>" for q in shift.evidence.speech_b_quotes])

        verified_badge = "✅" if shift.evidence.verified else "❌"

        significance_color = {
            "HIGH": "#dc3545",
            "MEDIUM": "#ffc107",
            "LOW": "#6c757d"
        }.get(shift.significance, "#6c757d")

        shifts_html += f"""
        <div class="shift-card">
            <h3>
                <span class="significance-badge" style="background-color: {significance_color}">
                    {html_escape(shift.significance)}
                </span>
                {html_escape(shift.shift_type)}: {html_escape(shift.theme)}
                {verified_badge}
            </h3>
            <p><strong>Interpretation:</strong> {html_escape(shift.interpretation)}</p>

            <div class="evidence-grid">
                <div class="evidence-col">
                    <h4>Earlier Speech</h4>
                    <div class="quote-box">
                        {evidence_a if evidence_a else "<em>No quotes (theme absent)</em>"}
                    </div>
                    {f'<p><small><strong>Stance:</strong> {shift.from_state["stance"]}, <strong>Trajectory:</strong> {shift.from_state["trajectory"]}, <strong>Emphasis:</strong> {shift.from_state["emphasis"]}/10</small></p>' if shift.from_state else ''}
                </div>
                <div class="evidence-col">
                    <h4>Later Speech</h4>
                    <div class="quote-box">
                        {evidence_b if evidence_b else "<em>No quotes (theme absent)</em>"}
                    </div>
                    {f'<p><small><strong>Stance:</strong> {shift.to_state["stance"]}, <strong>Trajectory:</strong> {shift.to_state["trajectory"]}, <strong>Emphasis:</strong> {shift.to_state["emphasis"]}/10</small></p>' if shift.to_state else ''}
                </div>
            </div>
        </div>
        """

    # Overall status
    all_pass = (
        consistency["overall_consistency"] >= 0.90 and
        verification["pass"] and
        negative_control["passed"]
    )

    status_color = "#28a745" if all_pass else "#dc3545"
    status_text = "✅ ALL CHECKS PASSED" if all_pass else "⚠️ SOME CHECKS FAILED"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>PoC Validation Report</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
                   margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px;
                         border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
            h2 {{ color: #555; margin-top: 30px; }}
            .status-banner {{ padding: 20px; margin: 20px 0; border-radius: 5px;
                             background-color: {status_color}; color: white; font-size: 18px;
                             font-weight: bold; text-align: center; }}
            .validation-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;
                               margin: 20px 0; }}
            .validation-card {{ padding: 15px; border: 2px solid #ddd; border-radius: 5px;
                               text-align: center; }}
            .validation-card.pass {{ border-color: #28a745; background: #f0f9f4; }}
            .validation-card.fail {{ border-color: #dc3545; background: #fef0f0; }}
            .shift-card {{ margin: 20px 0; padding: 20px; border: 1px solid #ddd;
                          border-radius: 5px; background: #fafafa; }}
            .significance-badge {{ display: inline-block; padding: 4px 12px; border-radius: 3px;
                                  color: white; font-size: 12px; font-weight: bold; }}
            .evidence-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
                             margin-top: 15px; }}
            .evidence-col {{ }}
            .quote-box {{ background: white; padding: 15px; border-left: 4px solid #007bff;
                         margin: 10px 0; font-size: 14px; line-height: 1.6; }}
            .metric {{ font-size: 32px; font-weight: bold; color: #007bff; }}
            .metric-label {{ font-size: 14px; color: #666; margin-top: 5px; }}
            .url-link {{ font-size: 12px; color: #666; word-break: break-all; }}
            .shifts-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .shifts-table th {{ background: #f8f9fa; padding: 12px; text-align: left;
                               border-bottom: 2px solid #dee2e6; font-weight: 600; }}
            .shifts-table td {{ padding: 10px; border-bottom: 1px solid #dee2e6; }}
            .shifts-table tr:hover {{ background: #f8f9fa; }}
            .sig-badge-small {{ display: inline-block; padding: 2px 8px; border-radius: 3px;
                               color: white; font-size: 11px; font-weight: bold; }}
            .change-arrow {{ color: #666; margin: 0 5px; }}
            .emphasis-change {{ font-size: 12px; color: #666; }}
            .emphasis-up {{ color: #28a745; }}
            .emphasis-down {{ color: #dc3545; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Fed Textual Change Tracker - PoC Validation Report</h1>
            <p><em>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</em></p>

            <div class="status-banner">{status_text}</div>

            <h2>Test Configuration</h2>
            <p><strong>Speech A:</strong><br><span class="url-link">{url_a}</span></p>
            <p><strong>Speech B:</strong><br><span class="url-link">{url_b}</span></p>

            <h2>Validation Results</h2>
            <div class="validation-grid">
                <div class="validation-card {'pass' if consistency['overall_consistency'] >= 0.90 else 'fail'}">
                    <div class="metric">{consistency['overall_consistency']:.1%}</div>
                    <div class="metric-label">Extraction Consistency</div>
                    <p style="font-size: 12px; margin-top: 10px;">
                        Target: ≥90%<br>
                        {'✅ Pass' if consistency['overall_consistency'] >= 0.90 else '❌ Fail'}
                    </p>
                </div>

                <div class="validation-card {'pass' if verification['pass'] else 'fail'}">
                    <div class="metric">{verification['verified']}/{verification['total']}</div>
                    <div class="metric-label">Evidence Verified</div>
                    <p style="font-size: 12px; margin-top: 10px;">
                        Target: 100%<br>
                        {'✅ Pass' if verification['pass'] else '❌ Fail'}
                    </p>
                </div>

                <div class="validation-card {'pass' if negative_control['passed'] else 'fail'}">
                    <div class="metric">{negative_control['high_significance_shifts']}</div>
                    <div class="metric-label">Spurious Shifts</div>
                    <p style="font-size: 12px; margin-top: 10px;">
                        Target: 0<br>
                        {'✅ Pass' if negative_control['passed'] else '❌ Fail'}
                    </p>
                </div>
            </div>

            <h2>Shifts Overview</h2>
            <table class="shifts-table">
                <thead>
                    <tr>
                        <th>Theme</th>
                        <th>Shift Type</th>
                        <th>Significance</th>
                        <th>Key Changes</th>
                    </tr>
                </thead>
                <tbody>
                    {shifts_table_rows if shifts_table_rows else '<tr><td colspan="4"><em>No shifts detected</em></td></tr>'}
                </tbody>
            </table>

            <h2>Consistency Details</h2>
            <p><strong>Themes identified (Run 1):</strong> {', '.join(consistency['themes_run1'])}</p>
            <p><strong>Themes identified (Run 2):</strong> {', '.join(consistency['themes_run2'])}</p>
            <p><strong>Theme overlap:</strong> {consistency['theme_overlap']:.1%}</p>
            <p><strong>Stance consistency:</strong> {consistency['stance_consistency']:.1%}</p>
            <p><strong>Trajectory consistency:</strong> {consistency['trajectory_consistency']:.1%}</p>

            <h2>Detected Shifts ({len(shifts)} found)</h2>
            {shifts_html if shifts_html else '<p><em>No significant shifts detected.</em></p>'}

            <h2>Summary</h2>
            <p><strong>Total shifts detected:</strong> {len(shifts)}</p>
            <p><strong>HIGH significance:</strong> {sum(1 for s in shifts if s.significance == 'HIGH')}</p>
            <p><strong>MEDIUM significance:</strong> {sum(1 for s in shifts if s.significance == 'MEDIUM')}</p>
            <p><strong>LOW significance:</strong> {sum(1 for s in shifts if s.significance == 'LOW')}</p>
        </div>
    </body>
    </html>
    """

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ Report generated: {output_path}")


def main():
    """Run the PoC."""

    # Configuration
    # Powell: Jackson Hole (Aug 22) vs FOMC Press Conference (Sep 17)
    SPEECH_A_URL = "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20251029.pdf"
    SPEECH_B_URL = "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20251210.pdf"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    print("="*60)
    print("Fed Textual Change Tracker - Proof of Concept")
    print("="*60)

    # Step 1: Extract fingerprints with consistency check
    print("\n[1/5] Extracting semantic fingerprints (with consistency check)...")
    fp_a_run1 = extract_fingerprint(SPEECH_A_URL, run_id=1, api_key=api_key)
    fp_a_run2 = extract_fingerprint(SPEECH_A_URL, run_id=2, api_key=api_key)
    fp_b = extract_fingerprint(SPEECH_B_URL, run_id=1, api_key=api_key)

    # Step 2: Calculate consistency
    print("\n[2/5] Calculating extraction consistency...")
    consistency = calculate_consistency(fp_a_run1, fp_a_run2)
    print(f"   Overall consistency: {consistency['overall_consistency']:.1%}")

    # Step 3: Detect shifts
    print("\n[3/5] Detecting shifts...")
    shifts = detect_shifts(fp_a_run1, fp_b)
    print(f"   Found {len(shifts)} shifts")

    # Step 4: Verify evidence
    print("\n[4/5] Verifying evidence...")
    verification = verify_all_shifts(shifts, fp_a_run1.speech_text, fp_b.speech_text)
    print(f"   Verified: {verification['verified']}/{verification['total']}")

    # Step 5: Negative control
    print("\n[5/5] Running negative control test...")
    negative_control = negative_control_test(extract_fingerprint, SPEECH_A_URL, api_key)
    print(f"   Spurious shifts: {negative_control['high_significance_shifts']}")

    # Generate report
    print("\n" + "="*60)
    print("Generating validation report...")
    output_path = os.path.join(os.path.dirname(__file__), "poc_report.html")
    generate_html_report(
        SPEECH_A_URL,
        SPEECH_B_URL,
        consistency,
        shifts,
        verification,
        negative_control,
        output_path
    )

    # Print summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"Extraction Consistency: {consistency['overall_consistency']:.1%} {'✅' if consistency['overall_consistency'] >= 0.90 else '❌'}")
    print(f"Evidence Verification:  {verification['verified']}/{verification['total']} {'✅' if verification['pass'] else '❌'}")
    print(f"Negative Control:       {negative_control['high_significance_shifts']} spurious shifts {'✅' if negative_control['passed'] else '❌'}")
    print(f"\nDetected {len(shifts)} shifts:")
    for shift in shifts[:5]:  # Show first 5
        print(f"  [{shift.significance}] {shift.shift_type}: {shift.theme}")
    if len(shifts) > 5:
        print(f"  ... and {len(shifts) - 5} more")

    print(f"\n📄 Full report: {output_path}")


if __name__ == "__main__":
    main()
