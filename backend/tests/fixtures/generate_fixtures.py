"""Generate 3 synthetic vendor-DPA PDFs at test time (no binaries committed).

All three read as agreements between a fictional Indian SaaS company,
"NovaHealth Technologies Pvt Ltd", and a fictional cloud/data-processing vendor,
"Meghdoot Cloud Services Pvt Ltd". INR amounts, Indian-style naming.

    contract_a_conflict.pdf     -> MSA liability cap (p1) overridden by SOW addendum (p2)
    contract_b_regulation_gap.pdf -> vague consent clause, fails DPDP s9 + GDPR Art 8
    contract_c_clean.pdf        -> fully compliant, no planted issues
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

FIXTURES_DIR = Path(__file__).parent
GENERATED_DIR = FIXTURES_DIR / "generated"

_STYLES = getSampleStyleSheet()
_BODY = _STYLES["BodyText"]
_H = _STYLES["Heading2"]


def _pages_to_pdf(path: Path, pages: list[list[str]]) -> None:
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )
    flow = []
    for i, blocks in enumerate(pages):
        for block in blocks:
            if block.startswith("# "):
                flow.append(Paragraph(block[2:], _H))
            else:
                flow.append(Paragraph(block, _BODY))
            flow.append(Spacer(1, 4 * mm))
        if i != len(pages) - 1:
            flow.append(PageBreak())
    doc.build(flow)


# --------------------------------------------------------------------------- #
CONTRACT_A_PAGES = [
    [
        "# Master Services Agreement",
        "This Master Services Agreement (\"MSA\") is entered into between "
        "NovaHealth Technologies Pvt Ltd (\"Company\") and Meghdoot Cloud Services "
        "Pvt Ltd (\"Vendor\") for the provision of cloud hosting and data-processing services.",
        "# Section 8. Limitation of Liability",
        "8.2 (a) Except for the indemnification obligations, the total aggregate "
        "liability of either party arising out of or related to this Agreement, whether "
        "in contract, tort or otherwise, shall not exceed Rupees 80,00,000 "
        "(Rupees Eighty Lakh only).",
        "# Section 12. Governing Law",
        "This Agreement shall be governed by and construed in accordance with the laws "
        "of India, and the courts at Bengaluru shall have exclusive jurisdiction.",
    ],
    [
        "# Statement of Work Addendum No. 1",
        "This SOW Addendum is issued under and forms part of the MSA between the "
        "Company and the Vendor.",
        "# 4. Data-Breach Liability",
        "4.1 Notwithstanding Section 8.2(a) of the MSA, the parties agree that "
        "liability for data-breach events, security incidents, and unauthorised "
        "disclosure of personal data under this SOW shall not exceed Rupees "
        "4,00,00,000 (Rupees Four Crore only). For the avoidance of doubt, this "
        "provision supersedes the general liability cap in the MSA in respect of "
        "data-breach events only.",
        "# 5. Term",
        "This SOW Addendum is effective from the Effective Date and continues for the "
        "duration of the MSA unless terminated earlier.",
    ],
]

CONTRACT_B_PAGES = [
    [
        "# Data Processing Agreement",
        "This Data Processing Agreement (\"DPA\") is entered into between NovaHealth "
        "Technologies Pvt Ltd (\"Data Fiduciary\") and Meghdoot Cloud Services Pvt Ltd "
        "(\"Data Processor\") and governs the processing of personal data by the "
        "Processor on behalf of the Fiduciary.",
        "# 2. Purpose and Scope",
        "2.1 The Processor shall process personal data solely to provide the hosting, "
        "storage and analytics services described in the applicable order form.",
        "# 3. Consent",
        "3.1 The Vendor shall obtain appropriate consents for the processing of "
        "personal data as required under applicable law. The Vendor shall maintain "
        "records of such consents and make them available to the Company on request.",
    ],
    [
        "# 6. Security and Breach Notification",
        "6.1 The Processor shall implement reasonable technical and organisational "
        "measures and shall notify the Fiduciary of any personal-data breach without "
        "undue delay and in any event within 72 hours of becoming aware of it.",
        "# 7. Sub-processing",
        "7.1 The Processor shall not engage any sub-processor without the prior "
        "written authorisation of the Fiduciary and shall impose equivalent "
        "obligations on any approved sub-processor.",
        "# 8. Data Deletion",
        "8.1 On termination the Processor shall delete or return all personal data "
        "within 30 days and certify such deletion in writing.",
    ],
]

CONTRACT_C_PAGES = [
    [
        "# Data Processing Agreement",
        "This Data Processing Agreement (\"DPA\") is entered into between NovaHealth "
        "Technologies Pvt Ltd (\"Data Fiduciary\") and Meghdoot Cloud Services Pvt Ltd "
        "(\"Data Processor\").",
        "# 1. Governing Law",
        "1.1 This DPA is governed by the laws of India, including the Digital Personal "
        "Data Protection Act, 2023, and the courts at Mumbai shall have jurisdiction.",
        "# 2. Purpose, Data Categories and Retention",
        "2.1 The Processor processes contact details and service-usage records of the "
        "Fiduciary's adult enterprise users solely to deliver the contracted services. "
        "2.2 Personal data is retained for the term of the agreement plus 90 days, after "
        "which it is deleted.",
        "# 3. Children's Data",
        "3.1 The Services are not directed to children. The Processor shall not "
        "knowingly process the personal data of any individual under 18 years of age, "
        "and shall not carry out behavioural tracking or targeted advertising directed "
        "at children.",
    ],
    [
        "# 4. Limitation of Liability",
        "4.1 The aggregate liability of the Processor for data-breach and "
        "confidentiality events shall not exceed the greater of (a) twelve months' "
        "fees paid under the agreement or (b) Rupees 5,00,00,000 (Rupees Five Crore "
        "only). Any change to this cap must be agreed in a signed written amendment "
        "that expressly references this Section 4.1.",
        "# 5. Breach Notification",
        "5.1 The Processor shall notify the Fiduciary and, where required, the Data "
        "Protection Board of India of any personal-data breach without undue delay and "
        "within 72 hours of becoming aware of it.",
        "# 6. Cross-Border Transfer and Localisation",
        "6.1 Personal data is stored and processed within India. The Processor shall "
        "not transfer personal data outside India except to jurisdictions not "
        "restricted by the Central Government and subject to appropriate safeguards.",
        "# 7. Audit Rights",
        "7.1 The Fiduciary may audit the Processor's data-processing practices, "
        "directly or through an independent auditor, once per year and following any "
        "personal-data breach.",
        "# 8. Sub-processors",
        "8.1 The Processor shall obtain the Fiduciary's prior written approval before "
        "engaging a sub-processor and shall flow down equivalent obligations.",
    ],
]

_FIXTURES = {
    "contract_a_conflict.pdf": CONTRACT_A_PAGES,
    "contract_b_regulation_gap.pdf": CONTRACT_B_PAGES,
    "contract_c_clean.pdf": CONTRACT_C_PAGES,
}


def generate_all(force: bool = False) -> dict[str, Path]:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}
    for name, pages in _FIXTURES.items():
        path = GENERATED_DIR / name
        if force or not path.exists():
            _pages_to_pdf(path, pages)
        out[name] = path
    return out


if __name__ == "__main__":
    for name, path in generate_all(force=True).items():
        print(f"wrote {path} ({path.stat().st_size} bytes)")
