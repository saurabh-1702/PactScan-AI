"""The benchmark's source material: base contracts, topic clauses and the rules
that decide each correct answer.

A benchmark contract = one base contract (a fictional Indian company and its
vendor) in which AT MOST ONE topic clause is changed. Every requirement the
system checks (8 playbook rules + 5 regulation clauses, taken verbatim from
``app/agents/detect/seed_data.py``) belongs to exactly one topic, so the
correct answer for every (contract, requirement) pair follows mechanically
from which topic was changed and how — see ``gold_label``.

Correct answers ("gold labels"):
  NONE      nothing is wrong — the system should raise nothing for this rule
  VIOLATES  a clause goes against the rule — the system should flag it
  GAP       the rule is mandatory and nothing in the contract addresses it —
            the system should report it (once)

Every text below is written so that the base contract complies with all 13
requirements. These labels are the foundation of every number in the paper:
check them by hand (``check_benchmark.py`` writes a review sheet).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Topics: which requirements each topic clause is responsible for
# --------------------------------------------------------------------------- #
# mandatory=True  -> if the topic is entirely absent, the correct answer is GAP
# mandatory=False -> if absent, nothing is wrong (NONE); the rationale says why
TOPICS: dict[str, dict] = {
    "breach_notification": {
        "requirements": ["pb_breach_notification_window", "dpdp_s8"],
        "clause_type": "BREACH_NOTIFICATION",
        "section": "Security and Breach Notification",
        "mandatory": True,
        "rationale": "DPDP s8 and the playbook both require breach notice; a DPA silent on it leaves the Company unable to meet its own duty to notify the Board.",
    },
    "liability_cap": {
        "requirements": ["pb_liability_cap_data_breach"],
        "clause_type": "LIMITATION_OF_LIABILITY",
        "section": "Limitation of Liability",
        "mandatory": False,
        "rationale": "The rule forbids a cap that is too LOW. With no liability clause the vendor's liability is uncapped, which is more protective for the Company, so silence breaks nothing.",
    },
    "dpa_fields": {
        "requirements": ["pb_mandatory_dpa_fields"],
        "clause_type": "DATA_PROCESSING",
        "section": "Details of Processing",
        "mandatory": True,
        "rationale": "The playbook says the DPA MUST state purpose, data categories and retention; omitting them is itself the problem.",
    },
    "children_data": {
        "requirements": ["pb_verifiable_parental_consent", "dpdp_s9", "gdpr_art8"],
        "clause_type": "DATA_PROCESSING",
        "section": "Children's Personal Data",
        "mandatory": True,
        "rationale": "PactScan's playbook (and its Detect agent since Phase 1) requires the DPA to address children's data explicitly; silence leaves s9 / Art 8 processing unconstrained.",
    },
    "subprocessors": {
        "requirements": ["pb_subprocessor_approval"],
        "clause_type": "SUBPROCESSOR_OBLIGATIONS",
        "section": "Sub-processors",
        "mandatory": True,
        "rationale": "The playbook requires prior written approval for sub-processors; without a clause nothing stops the vendor engaging any.",
    },
    "cross_border": {
        "requirements": ["pb_data_localization_transfer"],
        "clause_type": "DATA_LOCALIZATION_CROSS_BORDER_TRANSFER",
        "section": "Data Location and Transfers",
        "mandatory": True,
        "rationale": "The playbook requires the agreement to identify storage locations and limit transfers; silence identifies none.",
    },
    "deletion": {
        "requirements": ["pb_deletion_return_on_termination"],
        "clause_type": "TERMINATION",
        "section": "Return and Deletion of Data",
        "mandatory": True,
        "rationale": "The playbook requires deletion/return and certification on termination; silence means no such duty exists.",
    },
    "audit": {
        "requirements": ["pb_audit_rights"],
        "clause_type": "AUDIT_RIGHTS",
        "section": "Audit Rights",
        "mandatory": True,
        "rationale": "The playbook requires the Company to have an audit right; without a clause it has none.",
    },
    "lawful_basis": {
        "requirements": ["dpdp_s4", "gdpr_art6"],
        "clause_type": "DATA_PROCESSING",
        "section": "Instructions and Lawful Basis",
        "mandatory": False,
        "rationale": "Having a lawful ground (DPDP s4 / GDPR Art 6) is the Data Fiduciary's own statutory duty, not a term a processor contract must restate; silence breaks nothing, while a clause letting the vendor process for its own purposes without consent does.",
    },
}

# Clauses present in every contract that belong to no topic. Several are
# deliberately "near" a topic (confidentiality, indemnity) so a checker that
# treats silence as violation has something to wrongly flag.
FILLERS = ["services", "confidentiality", "indemnification", "governing_law"]

FILLER_META = {
    "services": ("OTHER", "Scope of Services"),
    "confidentiality": ("CONFIDENTIALITY", "Confidentiality"),
    "indemnification": ("INDEMNIFICATION", "Indemnification"),
    "governing_law": ("GOVERNING_LAW", "Governing Law and Jurisdiction"),
}

# Order clauses appear in, and the page each sits on.
LAYOUT: list[tuple[str, int]] = [
    ("services", 1),
    ("dpa_fields", 1),
    ("lawful_basis", 1),
    ("children_data", 1),
    ("breach_notification", 2),
    ("subprocessors", 2),
    ("cross_border", 2),
    ("confidentiality", 2),
    ("liability_cap", 2),
    ("indemnification", 2),
    ("deletion", 3),
    ("audit", 3),
    ("governing_law", 3),
]

# --------------------------------------------------------------------------- #
# Base contracts — six fictional Indian companies in different sectors
# --------------------------------------------------------------------------- #
BASES: list[dict] = [
    {
        "id": "b1", "style": 0, "sector": "health-tech",
        "C": "NovaHealth", "CF": "NovaHealth Technologies Pvt Ltd",
        "V": "CloudVault", "VF": "CloudVault Data Services Pvt Ltd",
        "service": "cloud hosting, managed backup and disaster recovery for the Company's patient-engagement platform",
        "purpose": "hosting and backing up the Company's patient-engagement platform",
        "data": "names, contact details, appointment history and health-programme enrolment records",
        "principals": "the Company's patients and employees",
        "cities": ("Mumbai", "Chennai"), "court": "Bengaluru",
        "hours": "seventy-two (72) hours", "floor": "₹5,00,00,000 (five crore rupees)",
        "children": "excluded",
    },
    {
        "id": "b2", "style": 1, "sector": "retail",
        "C": "Kiranmart", "CF": "Kiranmart Retail Pvt Ltd",
        "V": "DataNest", "VF": "DataNest Analytics LLP",
        "service": "customer-analytics dashboards and loyalty-programme data processing",
        "purpose": "operating the Company's loyalty programme and producing sales analytics for the Company",
        "data": "names, mobile numbers, purchase history and loyalty-point balances",
        "principals": "members of the Company's loyalty programme",
        "cities": ("Hyderabad", "Pune"), "court": "Hyderabad",
        "hours": "forty-eight (48) hours", "floor": "₹2,00,00,000 (two crore rupees)",
        "children": "excluded",
    },
    {
        "id": "b3", "style": 2, "sector": "ed-tech",
        "C": "EduSpark", "CF": "EduSpark Learning Pvt Ltd",
        "V": "StackPeak", "VF": "StackPeak Cloud Solutions Pvt Ltd",
        "service": "hosting of the Company's online learning platform and its student-progress database",
        "purpose": "hosting the Company's learning platform and storing student progress records",
        "data": "student names, class, guardian contact details and assessment scores",
        "principals": "students (including students under 18) and their parents or guardians",
        "cities": ("Bengaluru", "Delhi NCR"), "court": "Bengaluru",
        "hours": "twenty-four (24) hours", "floor": "₹3,00,00,000 (three crore rupees)",
        "children": "processed",
    },
    {
        "id": "b4", "style": 0, "sector": "fintech",
        "C": "PaySetu", "CF": "PaySetu Fintech Pvt Ltd",
        "V": "LedgerGrid", "VF": "LedgerGrid Infrastructure Pvt Ltd",
        "service": "transaction-ledger hosting and fraud-monitoring infrastructure",
        "purpose": "hosting the Company's payment ledger and running fraud-monitoring rules on it",
        "data": "names, bank account identifiers, transaction records and device identifiers",
        "principals": "the Company's account holders",
        "cities": ("Mumbai", "Navi Mumbai"), "court": "Mumbai",
        "hours": "twenty-four (24) hours", "floor": "₹10,00,00,000 (ten crore rupees)",
        "children": "excluded",
    },
    {
        "id": "b5", "style": 1, "sector": "HR-tech",
        "C": "TalentLoop", "CF": "TalentLoop HR Solutions Pvt Ltd",
        "V": "PeopleCore", "VF": "PeopleCore Payroll Services Pvt Ltd",
        "service": "payroll processing and employee-records management",
        "purpose": "running payroll and maintaining employment records for the Company's clients",
        "data": "employee names, PAN, bank details, salary and attendance records",
        "principals": "employees of the Company's client organisations",
        "cities": ("Chennai", "Coimbatore"), "court": "Chennai",
        "hours": "forty-eight (48) hours", "floor": "₹4,00,00,000 (four crore rupees)",
        # payroll data of employees: no children's data is processed at all, so
        # a contract silent on children breaks nothing (see gold_label)
        "children": "not_applicable",
    },
    {
        "id": "b6", "style": 2, "sector": "logistics",
        "C": "ShipRaftaar", "CF": "ShipRaftaar Logistics Pvt Ltd",
        "V": "RouteMind", "VF": "RouteMind Technologies Pvt Ltd",
        "service": "delivery-route optimisation and shipment-tracking software",
        "purpose": "optimising delivery routes and sending shipment-tracking updates to the Company's customers",
        "data": "recipient names, delivery addresses, phone numbers and delivery-time records",
        "principals": "recipients of the Company's shipments",
        "cities": ("Gurugram", "Noida"), "court": "New Delhi",
        "hours": "seventy-two (72) hours", "floor": "₹1,50,00,000 (one crore fifty lakh rupees)",
        "children": "excluded",
    },
]

# --------------------------------------------------------------------------- #
# Clause texts. Each list holds three drafting styles; a base uses BASES[i]["style"].
# Placeholders are filled from the base dict ({C}, {V}, {cities[0]}, ...).
# --------------------------------------------------------------------------- #
FOLLOWS: dict[str, list[str]] = {
    "breach_notification": [
        "The Vendor shall implement appropriate technical and organisational security measures to protect Personal Data, including encryption and access controls, and shall notify the Company of any Personal Data Breach without undue delay and in any event within {hours} of becoming aware of it, providing the information the Company needs to inform the Data Protection Board of India and each affected Data Principal.",
        "{V} shall maintain reasonable security safeguards (including encryption at rest and role-based access control) and shall inform {C} of every personal data breach without undue delay, and no later than {hours} after discovering it, and shall assist {C} in notifying the Board and the affected Data Principals.",
        "Security. {V} will protect Personal Data with appropriate technical and organisational measures. If {V} becomes aware of a Personal Data Breach it will tell {C} without undue delay and within {hours}, and will give {C} all details required for {C}'s notices to the Data Protection Board and to affected Data Principals.",
    ],
    "liability_cap": [
        "Each party's aggregate liability under this Agreement shall not exceed the fees paid in the twelve (12) months preceding the claim, provided that for breaches of data-protection or confidentiality obligations the Vendor's liability shall be the greater of three (3) times such fees or {floor}.",
        "Save for breaches of data-protection or confidentiality obligations, {V}'s total liability is limited to the fees paid by {C} in the preceding twelve (12) months. For those breaches, {V}'s liability shall be not less than the greater of twelve (12) months' fees and {floor}.",
        "Liability. Neither party's liability shall exceed twelve (12) months' fees, except that {V}'s liability for any data-protection or confidentiality breach shall be the greater of three times those fees or {floor}.",
    ],
    "dpa_fields": [
        "Schedule 1 sets out the processing: purpose — {purpose}; categories of personal data — {data}; categories of Data Principals — {principals}; retention — personal data is kept only for the term of this Agreement and deleted within thirty (30) days after it ends.",
        "Details of processing. Purpose: {purpose}. Personal data categories: {data}. Data Principals: {principals}. Retention: for the duration of the services, and thereafter only until deletion under the termination clause (no more than thirty (30) days).",
        "{V} processes the following under this Agreement — purpose: {purpose}; data: {data}; data principals: {principals}; retention period: the term of the Agreement plus no more than thirty (30) days.",
    ],
    "children_data:excluded": [
        "The Vendor shall not knowingly process personal data of children. Where the Company instructs the Vendor to process a child's personal data, the Vendor shall do so only after the Company has obtained the verifiable consent of the child's parent or lawful guardian, and the Vendor shall never undertake tracking, behavioural monitoring or targeted advertising directed at children.",
        "{V} does not expect to process data of children. If any child's personal data is to be processed, {V} will process it only once {C} has obtained verifiable consent from a parent or lawful guardian, and {V} will not carry out tracking, behavioural monitoring or targeted advertising aimed at children.",
        "Children. No personal data of children is to be processed under this Agreement unless {C} has first obtained verifiable parental or guardian consent; {V} shall not track, behaviourally monitor or target advertising at children in any case.",
    ],
    "children_data:processed": [
        "The Vendor processes personal data of students under the age of eighteen only after the Company has obtained the verifiable consent of each student's parent or lawful guardian, and the Vendor shall not undertake tracking, behavioural monitoring or targeted advertising directed at children.",
        "{V} will process personal data of children (students under 18) only where {C} has obtained verifiable consent from the child's parent or lawful guardian, and will never track, behaviourally monitor or show targeted advertising to children.",
        "Children's data. Student records of children are processed only after {C} obtains verifiable consent of a parent or lawful guardian. {V} shall not track, behaviourally monitor or direct targeted advertising at children.",
    ],
    "subprocessors": [
        "The Vendor shall not engage any sub-processor without the Company's prior written approval and shall impose on each approved sub-processor data-protection obligations no less protective than those in this Agreement.",
        "{V} may use a sub-processor only after {C} has approved it in writing in advance, and {V} shall flow down to every sub-processor the same data-protection obligations it owes under this Agreement.",
        "Sub-processors. Prior written approval from {C} is required before {V} engages any sub-processor; each approved sub-processor must be bound by data-protection terms at least as protective as these.",
    ],
    "cross_border": [
        "Personal Data shall be stored and processed only in data centres located in {cities[0]} and {cities[1]}, India. The Vendor shall not transfer Personal Data outside India except to a country not restricted by the Central Government, with the Company's prior written consent and appropriate safeguards.",
        "All personal data will be hosted in {V}'s facilities in {cities[0]} and {cities[1]}, India. Any transfer outside India requires {C}'s written consent, appropriate safeguards, and may only be to a jurisdiction not restricted by the Central Government.",
        "Location. Data is stored and processed in {cities[0]} and {cities[1]} (India) only. {V} may transfer data abroad only with {C}'s prior written consent, appropriate safeguards, and never to a country restricted by the Central Government.",
    ],
    "deletion": [
        "Upon termination or expiry of this Agreement, the Vendor shall, at the Company's election, return or delete all Personal Data within thirty (30) days and shall certify the deletion in writing.",
        "When this Agreement ends, {V} shall return or delete (as {C} chooses) all personal data within thirty (30) days and give {C} a written certificate of deletion.",
        "Exit. Within thirty (30) days after termination or expiry, {V} must return or delete all Personal Data at {C}'s option and certify the deletion in writing.",
    ],
    "audit": [
        "The Company, directly or through an independent auditor, may audit the Vendor's data-processing practices once in every year and additionally following any Personal Data Breach.",
        "{C} may audit {V}'s processing of personal data, itself or through an independent auditor, at least once a year and also after any personal data breach.",
        "Audit. {C} (or an independent auditor it appoints) may audit {V}'s data-processing practices annually and after any Personal Data Breach.",
    ],
    "lawful_basis": [
        "The Vendor shall process Personal Data only on the documented instructions of the Company, and the Company confirms that it has a lawful ground, including the valid consent of Data Principals where required, for all processing it instructs.",
        "{V} acts only on {C}'s documented instructions. {C} is responsible for having a lawful basis, including any consent required from Data Principals, for the processing it asks {V} to carry out.",
        "Instructions. {V} processes Personal Data solely on {C}'s documented instructions; {C} warrants that each instructed processing has a lawful ground, including Data Principal consent where needed.",
    ],
    # fillers
    "services": [
        "The Vendor shall provide {service} as described in the Order Form.",
        "{V} will provide {C} with {service}, as set out in the Order Form.",
        "Services. {V} provides {service} under the Order Form.",
    ],
    "confidentiality": [
        "Each party shall keep confidential all information disclosed by the other party and shall use it only to perform this Agreement.",
        "Both parties will keep the other's confidential information secret and use it only for the purposes of this Agreement.",
        "Confidentiality. Each party must protect the other's confidential information and use it solely to perform this Agreement.",
    ],
    "indemnification": [
        "The Vendor shall indemnify the Company against third-party claims arising from the Vendor's breach of this Agreement.",
        "{V} will indemnify {C} against any third-party claim caused by {V}'s breach of this Agreement.",
        "Indemnity. {V} indemnifies {C} against third-party claims resulting from {V}'s breach of this Agreement.",
    ],
    "governing_law": [
        "This Agreement is governed by the laws of India and the courts at {court} shall have exclusive jurisdiction.",
        "Indian law governs this Agreement; the courts at {court} have exclusive jurisdiction.",
        "Governing law. The laws of India apply, and the courts in {court} have exclusive jurisdiction.",
    ],
}

BREAKS: dict[str, list[str]] = {
    "breach_notification": [
        "The Vendor shall implement appropriate technical and organisational security measures to protect Personal Data, and shall notify the Company of a Personal Data Breach within thirty (30) days after completing its internal investigation of the incident.",
        "{V} shall maintain reasonable security safeguards. {V} may decide at its sole discretion whether a security incident warrants notifying {C}, and has no obligation to report incidents it considers minor.",
        "Security. {V} will protect Personal Data with appropriate technical and organisational measures, and will report a confirmed Personal Data Breach to {C} within fifteen (15) business days of confirming it.",
    ],
    "liability_cap": [
        "The Vendor's total liability for any data breach or confidentiality claim shall not exceed ₹50,000 (fifty thousand rupees).",
        "{V}'s aggregate liability for all claims, including data-protection and confidentiality breaches, is limited to one (1) month's fees.",
        "Liability. {V}'s liability for any breach of data-protection or confidentiality obligations is capped at ₹1,00,000 (one lakh rupees) in total.",
    ],
    # Breaks the rule by OMITTING the required details — deliberately without
    # widening the purpose, so it does not also touch the lawful-basis rules.
    "dpa_fields": [
        "The Vendor shall process Personal Data as necessary to provide the Services. The categories of personal data, the Data Principals concerned and the retention period will be agreed between the parties from time to time.",
        "{V} will process personal data as needed to deliver the services; the parties will settle the data categories, the persons concerned and how long data is kept at a later date.",
        "Processing. {V} processes Personal Data to the extent needed for the Services. No schedule of data categories, Data Principals or retention periods forms part of this Agreement.",
    ],
    "children_data:excluded": [
        "The Vendor may process personal data of users of any age, including children, and may use such data for behavioural analytics and personalised advertising without verifiable parental or guardian consent.",
        "{V} may collect and use data of children as well as adults, including for behavioural profiling and targeted advertising, without seeking consent from parents or guardians.",
        "Children. {V} may process children's personal data and use it for behavioural monitoring and targeted advertising without any parental or guardian consent.",
    ],
    "children_data:processed": [
        "The Vendor may process personal data of students of any age, including children, and may use it for behavioural analytics and personalised advertising without obtaining parental or guardian consent.",
        "{V} may process children's data (students under 18) without parental or guardian consent and may use it to track students' behaviour and target advertising to them.",
        "Children's data. Student records of children may be processed without any parental or guardian consent and may be used by {V} for behavioural monitoring and targeted advertising.",
    ],
    "subprocessors": [
        "The Vendor may engage sub-processors at its discretion without notice to, or approval from, the Company.",
        "{V} may appoint any sub-processor it chooses without telling {C} and without passing on any data-protection obligations.",
        "Sub-processors. {V} may engage sub-processors freely, without {C}'s approval.",
    ],
    "cross_border": [
        "The Vendor may store and process Personal Data in any country in which it or its affiliates operate, without restriction.",
        "{V} may move personal data to any country it chooses, at its discretion, and need not tell {C} where the data is held.",
        "Location. {V} may host and transfer Personal Data to any country, without restriction or notice to {C}.",
    ],
    "deletion": [
        "Upon termination, the Vendor may retain Personal Data indefinitely and need not return or delete it.",
        "After this Agreement ends, {V} may keep all personal data indefinitely and is under no duty to return or delete it.",
        "Exit. {V} may retain Personal Data indefinitely after termination, without any obligation to delete or return it.",
    ],
    "audit": [
        "The Vendor shall not be subject to audits by the Company; the Vendor's annual self-assessment report shall be conclusive evidence of compliance.",
        "{C} has no right to audit {V}; {V}'s own self-assessment is conclusive.",
        "Audit. {V} is not subject to audit by {C} or any auditor; {V}'s self-certification is conclusive.",
    ],
    "lawful_basis": [
        "The Vendor may process Personal Data for its own purposes, including product improvement and the sale of aggregated insights to third parties, without the consent of Data Principals.",
        "{V} may use personal data for its own business purposes, including selling insights derived from it to others, without obtaining consent from Data Principals.",
        "Own use. {V} may process Personal Data for its own purposes, including resale of derived insights, without any Data Principal's consent.",
    ],
}

# --------------------------------------------------------------------------- #
# "Trap" contracts: a later amendment changes an earlier clause.
# hidden_violation — the clause itself is fine, the amendment breaks the rule.
# hidden_fix       — the clause itself breaks the rule, the amendment cures it.
# Only a checker that reads a clause together with what overrides it gets these
# right (Known Issues §10.3: OVERRIDES traversal).
# {ref} is replaced with the clause number the amendment refers to.
# --------------------------------------------------------------------------- #
TRAPS: dict[str, dict] = {
    "breach_notification": {
        "hidden_violation": {
            "clause": "follows",
            "amendment": "Notwithstanding Clause {ref} (Security and Breach Notification), for any incident affecting backup or archival systems the Vendor shall notify the Company within ten (10) business days of completing its investigation.",
            "scope": "incidents affecting backup or archival systems",
        },
        "hidden_fix": {
            "clause": "The Vendor shall implement appropriate technical and organisational security measures to protect Personal Data, and shall notify the Company of a Personal Data Breach within fifteen (15) days of discovering it.",
            "amendment": "Notwithstanding Clause {ref} (Security and Breach Notification), the Vendor shall notify the Company of every Personal Data Breach without undue delay and in any event within forty-eight (48) hours of becoming aware of it.",
            "scope": "all personal data breaches",
        },
    },
    "deletion": {
        "hidden_violation": {
            "clause": "follows",
            "amendment": "Notwithstanding Clause {ref} (Return and Deletion of Data), the Vendor may retain copies of Personal Data in its backups for up to twelve (12) months after termination.",
            "scope": "copies held in backups",
        },
        "hidden_fix": {
            "clause": "Upon termination of this Agreement, the Vendor shall delete Personal Data within one hundred and eighty (180) days.",
            "amendment": "Notwithstanding Clause {ref} (Return and Deletion of Data), the Vendor shall, at the Company's election, return or delete all Personal Data within thirty (30) days of termination and certify the deletion in writing.",
            "scope": "all personal data on termination",
        },
    },
}

# --------------------------------------------------------------------------- #
# Pairs excluded from scoring (gold label EXCLUDE). A rewritten clause can
# reasonably be read as ALSO affecting a rule from another topic; where careful
# readers could disagree, the pair is left out rather than given a label a
# correct model might "fail". Decided in the label review (LABEL_REVIEW.md).
# (variant kind, varied topic) -> requirement ids excluded in those contracts
# --------------------------------------------------------------------------- #
EXCLUDED: dict[tuple[str, str], list[str]] = {
    # processing a child's data without parental consent also arguably lacks a
    # valid consent ground under DPDP s4; GDPR Art 6 may rest on another basis
    ("BREAKS", "children_data"): ["dpdp_s4", "gdpr_art6"],
    # letting the vendor use data for its own purposes contradicts the purpose
    # stated in the processing details
    ("BREAKS", "lawful_basis"): ["pb_mandatory_dpa_fields"],
    # keeping data after termination contradicts the retention period stated
    # in the processing details
    ("BREAKS", "deletion"): ["pb_mandatory_dpa_fields"],
    ("TRAP_HIDDEN_VIOLATION", "deletion"): ["pb_mandatory_dpa_fields"],
    # unvetted sub-processors / unrestricted transfers arguably undermine the
    # "appropriate technical and organisational measures" in DPDP s8
    ("BREAKS", "subprocessors"): ["dpdp_s8"],
    ("BREAKS", "cross_border"): ["dpdp_s8"],
}

# --------------------------------------------------------------------------- #
# Experiment 4 — simulated regulation updates (Horizon-Scanning path)
# For each update: the topic it concerns, and the correct answer by how that
# topic appears in a contract. Contracts where the topic was not changed use
# "FOLLOWS". A new requirement no contract addresses uses topic=None.
# --------------------------------------------------------------------------- #
UPDATES: list[dict] = [
    {
        "id": "u1_breach_72h",
        "regulation_name": "DPDP Act 2023 (India)",
        "effective_date": "2027-01-01",
        "text": "A Data Processor shall notify the Data Fiduciary of any personal data breach without delay and in any event within seventy-two hours of becoming aware of it.",
        "topic": "breach_notification",
        "gold_by_variant": {"FOLLOWS": "NONE", "BREAKS": "VIOLATES", "SILENT": "GAP",
                            "TRAP_HIDDEN_VIOLATION": "VIOLATES", "TRAP_HIDDEN_FIX": "NONE"},
    },
    {
        "id": "u2_erasure_30d",
        "regulation_name": "DPDP Act 2023 (India)",
        "effective_date": "2027-01-01",
        "text": "On termination of a processing contract, the Data Processor shall erase or return all personal data within thirty days and confirm the erasure to the Data Fiduciary in writing.",
        "topic": "deletion",
        "gold_by_variant": {"FOLLOWS": "NONE", "BREAKS": "VIOLATES", "SILENT": "GAP",
                            "TRAP_HIDDEN_VIOLATION": "VIOLATES", "TRAP_HIDDEN_FIX": "NONE"},
    },
    {
        "id": "u3_transfer_whitelist",
        "regulation_name": "DPDP Act 2023 (India)",
        "effective_date": "2027-04-01",
        "text": "Personal data may be transferred outside India only to a country or territory that has not been restricted by notification of the Central Government, and the processing contract must name the locations where personal data is stored.",
        "topic": "cross_border",
        "gold_by_variant": {"FOLLOWS": "NONE", "BREAKS": "VIOLATES", "SILENT": "GAP"},
    },
    {
        "id": "u4_grievance_contact",
        "regulation_name": "DPDP Act 2023 (India)",
        "effective_date": "2027-04-01",
        "text": "Every processing contract shall name a contact person resident in India who is responsible for responding to grievances of Data Principals about the processing.",
        "topic": None,  # a brand-new requirement: no contract addresses it
        "gold_all": "GAP",
    },
]
