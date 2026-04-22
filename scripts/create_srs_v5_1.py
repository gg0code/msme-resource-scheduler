"""
Script to create ZetaOps_SRS_v5_1.docx from ZetaOps_SRS_v5_0.docx.
Applies all changes specified for SRS v5.1 (document revision after
dev prompt v7.2 reshuffled the v6.x feature roadmap per IDC Worldwide
Intelligent ERP 2025 analysis).

Key changes v5.0 -> v5.1:
  * Add Section 1.1 Version Strategy (document vs product version distinction)
  * Add Section 1.2 Current State (at-a-glance shipped / blocked / planned)
  * Add Sections 6.24 - 6.27 (KPI Baseline v6.3, Material Estimator v6.4,
    Compliance Tracker v6.5, GST E-Invoicing v6.6)
  * Add 4 new feature flag rows (Table 2)
  * Add 4 new Core Entity rows (Table 14)
  * Add 3 new Migration Chain rows (024, 025, 026) in Table 15
  * Add Phase 8.5 Proof and Retention in Table 20
  * Move compliance tracker in Known Gaps (Table 18) from v7.1 to v6.5
  * Add 4 new Glossary rows (Table 21)
  * Update title subtitle and footer version line
  * Add v5.1 version history row (Table 0)

The script preserves the exact python-docx conventions from create_srs_v5.py:
  - Same helpers (replace_para_text, add_table_row, find_para_index,
    insert_para_after, insert_heading_after, insert_list_item_after)
  - Same table-indexing approach (tables[N] by ordinal)
  - Same insertion pattern (OxmlElement addprevious / addnext loop)
"""
import copy
import docx
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import lxml.etree as etree

SRC = r'C:\Users\gaura\OneDrive - ZERO CODE TECHNOLOGY & APPLIED RESEARCH PRIVATE\zPrograms\IITBhubneswar\MSME\LATEST\V5\ZetaOps_SRS_v5_0.docx'
DST = r'C:\Users\gaura\OneDrive - ZERO CODE TECHNOLOGY & APPLIED RESEARCH PRIVATE\zPrograms\IITBhubneswar\MSME\LATEST\V5\ZetaOps_SRS_v5_1.docx'

doc = Document(SRC)


# ---------------------------------------------------------------------------
# Helpers (copied verbatim from create_srs_v5.py for consistency)
# ---------------------------------------------------------------------------
def replace_para_text(para, old, new):
    """Replace first occurrence of old in para.text using the first run."""
    full = para.text
    if old not in full:
        return False
    if para.runs:
        r0 = para.runs[0]
        fmt_xml = copy.deepcopy(r0._r)
        for r in para.runs:
            r._r.getparent().remove(r._r)
        new_text = full.replace(old, new, 1)
        r0._r = fmt_xml
        r0.text = new_text
        para._p.append(r0._r)
    return True


def set_cell_text(cell, text):
    """Set cell to plain text, clearing existing paragraphs."""
    for para in cell.paragraphs:
        for run in para.runs:
            run.text = ''
    if cell.paragraphs:
        cell.paragraphs[0].runs[0].text = text if cell.paragraphs[0].runs else None
        if not cell.paragraphs[0].runs:
            cell.paragraphs[0].add_run(text)
    else:
        cell.add_paragraph(text)


def get_cell_text(cell):
    return cell.text.strip()


def add_table_row(table, values):
    """Append a row with the given list of string values."""
    row = table.add_row()
    for i, val in enumerate(values):
        if i < len(row.cells):
            row.cells[i].paragraphs[0].clear()
            row.cells[i].paragraphs[0].add_run(val)
    return row


def find_para_index(doc, substring):
    """Return index of first paragraph containing substring."""
    for i, p in enumerate(doc.paragraphs):
        if substring in p.text:
            return i
    return -1


def insert_block_before(doc, ref_substring, block):
    """
    Insert a list of (style, text) paragraphs BEFORE the first paragraph
    whose text contains ref_substring. Uses addprevious so accumulation
    is forward (order preserved).
    """
    idx = find_para_index(doc, ref_substring)
    if idx < 0:
        raise ValueError(f'Reference substring not found: {ref_substring!r}')
    ref_para = doc.paragraphs[idx]
    for style, text in block:
        new_el = OxmlElement('w:p')
        ref_para._p.addprevious(new_el)
        for p in doc.paragraphs:
            if p._p is new_el:
                try:
                    p.style = doc.styles[style]
                except Exception:
                    pass
                p.add_run(text)
                break


# ===========================================================================
# 1. Title / subtitle line -- bump to v5.1
# ===========================================================================
paras = doc.paragraphs
# Search for the existing subtitle to handle any line-number drift
subtitle_idx = -1
for i, p in enumerate(paras[:10]):
    if 'Version 5.0' in p.text and 'Updated through v6.2' in p.text:
        subtitle_idx = i
        break
if subtitle_idx >= 0:
    paras[subtitle_idx].clear()
    paras[subtitle_idx].add_run(
        'Version 5.1  |  April 20, 2026  |  '
        'Updated through v6.2 and green-baseline test recovery'
    )
else:
    print('WARNING: subtitle not found for update')

# ===========================================================================
# 2. Version history table (Table 0) -- add v5.1 row
# ===========================================================================
t0 = doc.tables[0]
add_table_row(t0, [
    '5.1',
    'Updated through green-baseline (Apr 20 2026). Reshuffled v6.x roadmap '
    'after IDC Worldwide Intelligent ERP 2025 analysis: v6.3 KPI Baseline + '
    'Savings Summary (retention moat), v6.4 Material Estimator as standalone '
    'WhatsApp surface (acquisition wedge), v6.5 Compliance Tracker (pulled '
    'forward from v7.1), v6.6 GST E-Invoicing JSON. Old v6.3 RAG pgvector '
    'becomes v6.7. Old v6.5 Supervisor Agent becomes v6.8. Added Section 1.1 '
    'Version Strategy and Section 1.2 Current State at top of document. '
    'Added functional requirement Sections 6.24-6.27 for new v6.3-v6.6 '
    'features. Test suite recovered to 199 passing (green-baseline). '
    'Aligns with dev prompt v7.2.'
])

# ===========================================================================
# 3. Insert Section 1.1 Version Strategy and Section 1.2 Current State
#    These go BEFORE Section 2 Business Context.
# ===========================================================================
section_1_1_and_1_2 = [
    ('Heading 2', '1.1 Version Strategy'),
    ('Normal',
     'This document uses two independent version numbers. Confusion between '
     'them is the single most common source of documentation drift in this '
     'project, so the distinction is called out explicitly.'),
    ('List Paragraph',
     'Product Version (used in git tags, CHANGELOG, customer-facing '
     'communications). Format vMAJOR.MINOR. MAJOR denotes product era: V5 = '
     'WhatsApp-first MSME platform, V6 = AI-first intelligent platform, V7 = '
     'ERP-connected mid-market platform. MINOR increments with each shipped '
     'feature release within that era. Current product release as of this '
     'document: v6.2 (shipped April 13, 2026) plus green-baseline test suite '
     'recovery (April 20, 2026). Next planned: v6.3.'),
    ('List Paragraph',
     'Document Version (this SRS only). Format Document vX.Y. Independent '
     'of product version. This is SRS Document v5.1. It describes product '
     'releases v5.0 through v6.2 (shipped) and v6.3 through v7.2 (planned).'),
    ('Normal',
     'Rule: where this document refers to a version number without a '
     '"Document" prefix, the reference is to a Product Version. Where this '
     'document refers to SRS Document revisions, the word "Document" is '
     'always used.'),
    ('Heading 2', '1.2 Current State (as of April 20, 2026)'),
    ('Normal',
     'At-a-glance state of all features. This section answers the single '
     'most common question a reader has when picking up this document cold: '
     'where is the product right now?'),
    ('Normal', 'SHIPPED (production-ready in mock mode, awaiting Meta go-live):'),
    ('List Paragraph',
     'v5.10 Proactive Alerts -- morning briefing, conflict alert, job-ending-soon.'),
    ('List Paragraph',
     'v5.12 Role Limiting + 3-Language Support (Hindi / Hinglish / English).'),
    ('List Paragraph',
     'v5.15 Manager Check-in Flow (7:00am WhatsApp input) + Owner Briefing (7:15am output).'),
    ('List Paragraph',
     'v5.16 Day 1 Simple Table with source and worker_type fields (migration 023).'),
    ('List Paragraph',
     'v6.0 Schema Context layer for AI multi-hop reasoning.'),
    ('List Paragraph',
     'v6.1 RAG Pipeline with industry templates for 4 verticals (printing, manufacturing, fabrication, field_service).'),
    ('List Paragraph',
     'v6.2 Industry-Aware Dynamic UI Labels + RegisterPage auth bug fix.'),
    ('List Paragraph',
     'green-baseline (Apr 20) -- test suite recovery: 199 tests passing, 0 failed, 0 errors. SQLite StaticPool fix for in-memory unit tests.'),
    ('Normal', 'BLOCKED (external dependency -- Meta Business portfolio review):'),
    ('List Paragraph',
     'v5.11 WhatsApp Go-Live -- Zero Zeta portfolio appeal submitted Apr 8, in review.'),
    ('List Paragraph',
     'v5.13 Voice Notes (Whisper transcription) -- depends on v5.11.'),
    ('List Paragraph',
     'v5.14 Live End-to-End Test on real device -- depends on v5.11 and v5.13.'),
    ('Normal', 'NEXT TO BUILD (renumbered from earlier v5.17-v5.20 after IDC analysis):'),
    ('List Paragraph',
     'v6.3 KPI Baseline + Monthly Savings Summary -- retention moat. Build first.'),
    ('List Paragraph',
     'v6.4 Material Estimator as standalone WhatsApp surface -- acquisition wedge.'),
    ('List Paragraph',
     'v6.5 Compliance Deadline Tracker -- pulled forward from v7.1. Standalone-valuable.'),
    ('List Paragraph',
     'v6.6 GST E-Invoicing JSON generation -- natural extension of v6.5.'),
    ('List Paragraph',
     'v6.7 RAG pgvector migration (was old v6.3) -- infrastructure, not user-facing.'),
    ('List Paragraph',
     'v6.8 Supervisor Agent (was old v6.5) -- depends on v6.3-v6.7 as surface area.'),
    ('Normal', 'V7 ERA PLANNED (mid-market, ERP-connected):'),
    ('List Paragraph',
     'v7.0 ERP Connector Layer (SAP / Tally / Excel). Chemical / process enters here.'),
    ('List Paragraph',
     'v7.1 Contractor Labour Layer (was v7.2, renumbered after compliance moved forward).'),
    ('List Paragraph',
     'v7.2 Reserved slot.'),
    ('Normal', 'REFERENCE DOCUMENTS:'),
    ('List Paragraph',
     'Build standards and architectural rules: ZETAOPS_DEV_PROMPT.md v7.2.'),
    ('List Paragraph',
     'Product version scheme: Section 1.1 of this document.'),
    ('List Paragraph',
     'Detailed feature specs: Sections 6.17 - 6.27 of this document.'),
    ('List Paragraph',
     'Migration chain truth: Section 9.2 of this document. Current head: 023.'),
]

insert_block_before(doc, '2. Business Context', section_1_1_and_1_2)

# ===========================================================================
# 4. Feature Flags table -- add 4 new rows for v6.3 / v6.4 / v6.5 / v6.6
#    Table 2 is the Feature Flags table (per v5.0 script convention,
#    Table 0 = version history, Table 1 = stakeholders, Table 2 = flags).
# ===========================================================================
# Safer than assuming index: find by header content
flag_table = None
for t in doc.tables:
    header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
    if 'Flag' in header_text and 'Default' in header_text and 'Unlocks' in header_text:
        flag_table = t
        break

if flag_table is not None:
    add_table_row(flag_table, [
        'kpi_baseline', 'True', 'V6',
        'Daily tenant_kpi_snapshot capture + monthly savings summary to '
        'owner phone. Shipped in v6.3.'
    ])
    add_table_row(flag_table, [
        'material_estimator_freemium', 'False', 'V6',
        'When True: first 10 material queries per month free for free-tier '
        'tenants. Acquisition wedge. Shipped in v6.4.'
    ])
    add_table_row(flag_table, [
        'compliance_tracker', 'False', 'V6',
        'Tenant-specific compliance item seeding, reminder scheduler, and '
        'document upload. Shipped in v6.5.'
    ])
    add_table_row(flag_table, [
        'einvoice_generator', 'False', 'V6',
        'Generate GSTN-compliant JSON from completed job data. No portal '
        'submission. Shipped in v6.6.'
    ])
else:
    print('WARNING: Feature flags table not found')

# ===========================================================================
# 5. Insert Sections 6.24 - 6.27 (new functional requirements)
#    Inserted BEFORE "7. Bug Fixes" heading, after existing 6.23.
# ===========================================================================
new_sections_624_627 = [
    # --- 6.24 KPI Baseline + Monthly Savings Summary (v6.3) ---
    ('Heading 2', '6.24 KPI Baseline and Monthly Savings Summary (v6.3)'),
    ('Normal',
     'Captures operational KPIs passively during the first week of every '
     'tenant lifecycle (the baseline), then reports monthly savings to the '
     'owner via WhatsApp. Proves ongoing ROI. Prevents churn from owners '
     'forgetting why they pay for ZetaOps.'),
    ('List Paragraph',
     'New table tenant_kpi_snapshot (migration 024): one row per tenant '
     'per day. Columns include tenant_id, snapshot_date, orders_delayed_count, '
     'orders_on_time_count, substitute_find_minutes_avg, overtime_hours_total, '
     'machine_idle_hours, conflicts_detected, conflicts_resolved_by_ai, '
     'ai_suggestions_accepted, ai_suggestions_rejected, is_baseline (boolean).'),
    ('List Paragraph',
     'Baseline window: first 7 calendar days after tenant registration. '
     'Rows tagged is_baseline=True. All subsequent rows tagged is_baseline=False.'),
    ('List Paragraph',
     'Capture service: backend/app/services/kpi_capture.py. Hooks into '
     'existing scheduler, whatsapp_alerts, and assignments endpoints. '
     'APScheduler job at 23:59 writes daily snapshot. Reads from existing '
     'tables only -- no new user data collection.'),
    ('List Paragraph',
     'Monthly summary: APScheduler job at 09:00 on the 1st of each month. '
     'Compares last 30 days of measured KPIs against baseline. 3-line '
     'WhatsApp message to owner in detected language: rupees saved, hours '
     'saved, one concrete highlight.'),
    ('List Paragraph',
     'On-demand query: owner can ask "kitna save hua is month?" via '
     'WhatsApp; system returns live month-to-date summary.'),
    ('List Paragraph',
     'Data retention: kpi_snapshot rows kept 13 months rolling. Aggregation '
     'tables used for longer history.'),
    ('Normal',
     'Acceptance criteria: new tenant Days 1-7 produce 7 baseline rows. '
     'Day 8 onwards non-baseline. First monthly summary fires between Day 31 '
     'and Day 37. Summary does not send if fewer than 7 baseline days exist. '
     'Less-than-30-day measurements tagged "tentative savings". All KPI '
     'computations respect tenant_id isolation.'),
    ('Normal',
     'Out of scope for v6.3: dashboard visualization (deferred to v6.3.1), '
     'cross-tenant benchmarks (deferred to v7.x), per-employee breakdowns '
     '(deferred unless demand emerges).'),

    # --- 6.25 Material Estimator Standalone (v6.4) ---
    ('Heading 2', '6.25 Material Estimator as First-Class WhatsApp Surface (v6.4)'),
    ('Normal',
     'Exposes existing material estimation capability (backend endpoint '
     'shipped in v3.9.8, RAG grounding shipped in v6.1) as a standalone '
     'WhatsApp entry point. Primary use case: an MSME owner asks "5000 '
     'brochures ke liye kitna paper chahiye" and receives a grounded, '
     'industry-calibrated answer without creating a job or understanding '
     'the scheduler.'),
    ('List Paragraph',
     'New WhatsApp intent: material_query. Detected in whatsapp_intent.py '
     'alongside existing intents. Read-only -- bypasses confirmation flow.'),
    ('List Paragraph',
     'Keyword triggers loaded from rag_data/_templates/{industry}/materials.txt. '
     'Printing: paper, ink, plates, binding, lamination. Manufacturing: steel, '
     'aluminum, threads, fasteners, coolant. Fabrication: MS plate, pipes, '
     'rods, welding rods, gas. Field service: spares, consumables, PPE, tools.'),
    ('List Paragraph',
     'Reuses existing endpoint GET /api/jobs/{job_id}/material-estimate. '
     'Estimation math always in backend. AI only narrates -- never computes '
     '(Principle 11 from dev prompt).'),
    ('List Paragraph',
     'Response format (3 lines): quantity needed, estimated cost, '
     'confidence level. High = 3+ historical jobs of same industry and type. '
     'Medium = 1-2 historical or RAG-based. Low = pure inference from industry norm.'),
    ('List Paragraph',
     'Works for all three phone roles (owner / manager / operator) -- '
     'material estimation is operational, not financial, so no role-based '
     'blocking needed.'),
    ('List Paragraph',
     'Feature flag material_estimator_freemium (default False). When True: '
     'free-tier tenants get first 10 queries per month free, then upgrade '
     'prompt. Candidate acquisition wedge -- stripped-down "ZetaOps Estimator" '
     'possible as separate free-tier signup product.'),
    ('List Paragraph',
     'Response cached per tenant per material for 24 hours. End-to-end '
     'response time target: 4 seconds from WhatsApp message received to '
     'reply sent.'),
    ('Normal',
     'Acceptance criteria: "5000 brochures ke liye kitna paper chahiye" '
     'on a printing tenant returns paper quantity, rupee estimate, and '
     'confidence. Same query on a fabrication tenant returns a clarification '
     'or redirect. Query without quantity returns a clarifying question, not '
     'an estimate. Historical lookups use tenant own jobs only -- never '
     'cross-tenant data.'),

    # --- 6.26 Compliance Deadline Tracker (v6.5) ---
    ('Heading 2', '6.26 Compliance Deadline Tracker (v6.5)'),
    ('Normal',
     'Tracks statutory and regulatory deadlines per tenant. Sends WhatsApp '
     'reminders at T-30, T-7, and T-1 days before each deadline. Accepts '
     'document upload via WhatsApp reply to mark compliance. Standalone-'
     'valuable -- delivers value even to tenants who do not use the '
     'scheduler. Pulled forward from v7.1 after IDC analysis identified '
     'compliance as the single highest-ROI addition for MSMEs.'),
    ('Normal', 'Scope includes (India, MSME-focused):'),
    ('List Paragraph',
     'Statutory filings: GST monthly return GSTR-3B (20th), GST quarterly '
     'return GSTR-1, ESI return (15th monthly), PF return (15th monthly), '
     'TDS return (quarterly), Professional Tax (state-varies).'),
    ('List Paragraph',
     'Licenses and registrations: Factory License renewal, Pollution Control '
     'Board Consent to Operate, Fire Safety NOC, Trade License, MSME Udyam '
     'certificate update.'),
    ('List Paragraph',
     'Industry-specific items loaded from rag_data/_templates/{industry}/'
     'compliance.yaml per vertical. Printing: pollution NOC. Manufacturing '
     'and fabrication: Factory Act, welding safety. Field service: vehicle '
     'fitness certificates, driver licenses.'),
    ('Normal', 'Implementation:'),
    ('List Paragraph',
     'New tables in migration 025: compliance_item (tenant_id, item_type, '
     'item_name, renewal_frequency, last_filed_date, next_due_date, status, '
     'industry_default), compliance_document (compliance_item_id, tenant_id, '
     'filename, mime_type, uploaded_at, file_path, uploader_user_id), '
     'compliance_reminder_log (compliance_item_id, reminder_day, sent_at, '
     'channel).'),
    ('List Paragraph',
     'Seeding at tenant registration: industry-appropriate compliance_item '
     'rows created with status=active and due dates computed from common '
     'filing calendar. Owner can deactivate items that do not apply.'),
    ('List Paragraph',
     'APScheduler daily at 08:00: compliance_reminder_job. For each active '
     'item where next_due_date - today equals 30, 7, or 1 and no reminder_log '
     'row exists: send WhatsApp to owner, log the send. Idempotent via '
     'log check.'),
    ('List Paragraph',
     'Document upload via WhatsApp reply: PDF, JPG, PNG up to 10 MB. '
     'Stores in compliance_document table. Marks last_filed_date=today. '
     'Advances next_due_date by renewal_frequency. Confirms via WhatsApp.'),
    ('List Paragraph',
     'Dashboard widget: "Upcoming Deadlines" card on main dashboard showing '
     'next 3 items with countdown. Click-through to full list.'),
    ('List Paragraph',
     'Tenant-isolated storage. 5-year document retention minimum '
     '(statutory audit window). tenant_id filter on every query.'),
    ('Normal',
     'Acceptance criteria: new manufacturing tenant gets compliance_item '
     'rows seeded for GSTR-3B, GSTR-1, ESI, PF, Factory License, Pollution '
     'NOC. Owner can deactivate any item. Reminder at T-30 fires once per '
     'cycle. Document upload advances next_due_date. Dashboard widget renders '
     'next 3 items ascending by date.'),
    ('Normal',
     'Out of scope for v6.5: auto-generation of e-invoice JSON (deferred to '
     'v6.6), submission to GSTN or any government portal (never in scope -- '
     'ZetaOps reminds, does not file), legal or tax advice.'),
    ('Normal',
     'Pricing implication: standalone-valuable feature. Consider unbundled '
     'tier at Rs 499/month or Rs 0 additional bundled with ZetaOps Core. '
     'Decision deferred to post-v6.5 pricing review.'),

    # --- 6.27 GST E-Invoicing JSON Generation (v6.6) ---
    ('Heading 2', '6.27 GST E-Invoicing JSON Generation (v6.6)'),
    ('Normal',
     'Converts completed job data into GSTN-compliant e-invoice JSON. '
     'Sends JSON to owner via WhatsApp and email for submission by the '
     'owner CA or accountant. ZetaOps does not submit to GSTN directly. '
     'Build only after v6.5 is shipped and customers are using the '
     'reminder layer.'),
    ('List Paragraph',
     'New service: backend/app/services/einvoice_generator.py. Takes '
     'completed Job record + customer GSTIN + tenant GSTIN, produces JSON '
     'conforming to GSTN schema v1.1 (as of 2026).'),
    ('List Paragraph',
     'New endpoint: POST /api/einvoice/generate/{job_id}. Returns JSON '
     'payload and validation report.'),
    ('List Paragraph',
     'Migration 026: add gstin column to Customer model (String 15, nullable).'),
    ('List Paragraph',
     'WhatsApp trigger: when manager marks job complete, system asks '
     'owner "E-invoice banaun? Customer ka GSTIN bhej do". Owner replies '
     'with GSTIN, system generates JSON, sends to owner email plus WhatsApp.'),
    ('List Paragraph',
     'Compliance item for e-invoicing auto-created once tenant turnover '
     'crosses threshold (Rs 5 crore as of 2026, decreasing annually).'),
    ('List Paragraph',
     'Feature flag einvoice_generator (default False). Enabled per tenant '
     'on request or when turnover indicator triggers it.'),
    ('Normal',
     'Out of scope: managing tenant GSTN login credentials or API keys '
     '(those live in owner device, never in ZetaOps). Reconciliation with '
     'bank statements or accounting software. Direct GSTN portal submission.'),
]

insert_block_before(doc, '7. Bug Fixes', new_sections_624_627)

# ===========================================================================
# 6. Core Entities table (Table 14 in v5.0 script convention)
#    Add 4 new rows for v6.3-v6.6 entities.
# ===========================================================================
# Find by header match to be resilient to ordinal drift
core_entity_table = None
for t in doc.tables:
    header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
    if 'Entity' in header_text and 'Key Attributes' in header_text:
        core_entity_table = t
        break

if core_entity_table is not None:
    add_table_row(core_entity_table, [
        'TenantKPISnapshot',
        'tenant_id, snapshot_date, orders_delayed_count, '
        'orders_on_time_count, substitute_find_minutes_avg, '
        'overtime_hours_total, machine_idle_hours, conflicts_detected, '
        'conflicts_resolved_by_ai, is_baseline',
        'New table in migration 024 (v6.3). One row per tenant per day. '
        'First 7 days tagged is_baseline=True. 13-month rolling retention.'
    ])
    add_table_row(core_entity_table, [
        'ComplianceItem',
        'tenant_id, item_type, item_name, renewal_frequency, '
        'last_filed_date, next_due_date, status, industry_default',
        'New table in migration 025 (v6.5). Industry-appropriate items '
        'seeded at tenant registration. Owner can deactivate.'
    ])
    add_table_row(core_entity_table, [
        'ComplianceDocument',
        'compliance_item_id, tenant_id, filename, mime_type, '
        'uploaded_at, file_path, uploader_user_id',
        'New table in migration 025 (v6.5). 5-year retention (statutory '
        'audit window). 10 MB file size limit. PDF, JPG, PNG, XML supported.'
    ])
    add_table_row(core_entity_table, [
        'ComplianceReminderLog',
        'compliance_item_id, reminder_day, sent_at, channel',
        'New table in migration 025 (v6.5). reminder_day in {30, 7, 1}. '
        'Idempotent reminder send via log check.'
    ])
else:
    print('WARNING: Core Entity table not found')

# ===========================================================================
# 7. Migration Chain table -- add rows 024, 025, 026.
#    Table 15 in v5.0 script convention; find by header for safety.
# ===========================================================================
migration_table = None
for t in doc.tables:
    header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
    if 'Revision' in header_text and 'Description' in header_text:
        migration_table = t
        break

if migration_table is not None:
    add_table_row(migration_table, [
        '024',
        'KPI Baseline -- creates tenant_kpi_snapshot table (tenant_id, '
        'snapshot_date, orders_delayed_count, orders_on_time_count, '
        'substitute_find_minutes_avg, overtime_hours_total, machine_idle_hours, '
        'conflicts_detected, conflicts_resolved_by_ai, ai_suggestions_accepted, '
        'ai_suggestions_rejected, is_baseline BOOLEAN DEFAULT FALSE). '
        'Required for v6.3.'
    ])
    add_table_row(migration_table, [
        '025',
        'Compliance tracking -- creates three tables: compliance_item '
        '(tenant_id, item_type VARCHAR 50, item_name VARCHAR 200, '
        'renewal_frequency VARCHAR 20, last_filed_date DATE NULL, '
        'next_due_date DATE NOT NULL, status VARCHAR 20 DEFAULT active, '
        'industry_default BOOLEAN DEFAULT FALSE); compliance_document '
        '(compliance_item_id, tenant_id, filename, mime_type, uploaded_at, '
        'file_path, uploader_user_id); compliance_reminder_log '
        '(compliance_item_id, reminder_day INT, sent_at, channel). '
        'Required for v6.5.'
    ])
    add_table_row(migration_table, [
        '026',
        'E-invoicing support -- adds gstin (VARCHAR 15 NULL) to customers '
        'table for GSTN-compliant invoice generation. Required for v6.6.'
    ])
else:
    print('WARNING: Migration chain table not found')

# ===========================================================================
# 8. Known Gaps table (Table 18 in v5.0 script convention) --
#    move row #1 (Operator % allocation) or similar if compliance exists;
#    more importantly: update any row mentioning v7.1 compliance, add new
#    gaps for v6.3/v6.4/v6.5/v6.6.
# ===========================================================================
known_gaps_table = None
for t in doc.tables:
    header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
    if 'Pain Point' in header_text and 'Planned Fix' in header_text:
        known_gaps_table = t
        break

if known_gaps_table is not None:
    # Update any row that points compliance at v7.1 -> point at v6.5
    for row in known_gaps_table.rows:
        cells = [get_cell_text(c) for c in row.cells]
        if len(cells) >= 5:
            row_text = ' '.join(cells).lower()
            if 'compliance' in row_text and ('v7.1' in row_text or '7.1' in cells[-1]):
                # Update the Target column (last cell) to v6.5
                row.cells[-1].paragraphs[0].clear()
                row.cells[-1].paragraphs[0].add_run('v6.5')
                # Update status column
                row.cells[2].paragraphs[0].clear()
                row.cells[2].paragraphs[0].add_run('Planned')
                # Update Planned Fix column
                row.cells[3].paragraphs[0].clear()
                row.cells[3].paragraphs[0].add_run(
                    'Pulled forward from v7.1 after IDC analysis. WhatsApp '
                    'reminders at T-30/7/1 with document upload. Standalone-'
                    'valuable feature. See Section 6.26.'
                )

    # Add new gap rows for v6.3 / v6.4 / v6.5 / v6.6
    next_num_start = 26  # v5.0 script added up through #25; use 26+ here
    new_gaps_v51 = [
        [str(next_num_start),
         'Prove ROI to owner month-over-month',
         'Planned',
         'KPI Baseline + Monthly Savings Summary. Retention moat. '
         'Migration 024 creates tenant_kpi_snapshot. See Section 6.24.',
         'v6.3'],
        [str(next_num_start + 1),
         'Material estimation as first-class WhatsApp entry point',
         'Planned',
         'Standalone WhatsApp surface for "kitna chahiye" queries. '
         'Backend already shipped in v3.9.8; exposing as direct intent. '
         'See Section 6.25.',
         'v6.4'],
        [str(next_num_start + 2),
         'Compliance deadline tracking (GST, ESI, PF, Factory Act, NOC)',
         'Planned',
         'Pulled forward from v7.1. WhatsApp reminders + document upload. '
         'Migration 025. See Section 6.26.',
         'v6.5'],
        [str(next_num_start + 3),
         'GST e-invoicing JSON generation',
         'Planned',
         'Generate GSTN schema v1.1 JSON from completed jobs. Send to '
         'owner for CA submission. No direct GSTN portal integration. '
         'Migration 026. See Section 6.27.',
         'v6.6'],
    ]
    for gap in new_gaps_v51:
        add_table_row(known_gaps_table, gap)
else:
    print('WARNING: Known Gaps table not found')

# ===========================================================================
# 9. Roadmap table (Table 20 in v5.0 script convention) --
#    insert Phase 8.5 "Proof and Retention" between Phase 8 and Phase 9.
# ===========================================================================
roadmap_table = None
for t in doc.tables:
    header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
    if 'Phase' in header_text and 'Deliverables' in header_text:
        roadmap_table = t
        break

if roadmap_table is not None:
    # Find Phase 9 row; insert Phase 8.5 BEFORE it.
    phase_9_row = None
    phase_9_idx = -1
    for i, row in enumerate(roadmap_table.rows):
        if 'Phase 9' in get_cell_text(row.cells[0]):
            phase_9_row = row
            phase_9_idx = i
            break

    if phase_9_row is not None:
        # Build a new row XML element by cloning Phase 9's structure
        new_row_xml = copy.deepcopy(phase_9_row._tr)
        phase_9_row._tr.addprevious(new_row_xml)
        # Locate the newly-inserted row and populate
        new_row = roadmap_table.rows[phase_9_idx]
        phase_8_5_values = [
            'Phase 8.5 -- Proof and Retention',
            'Planned',
            'v6.3 - v6.6',
            'v6.3: KPI Baseline + monthly WhatsApp savings summary '
            '(retention moat). v6.4: Material Estimator as first-class '
            'WhatsApp surface (acquisition wedge). v6.5: Compliance '
            'Tracker + deadline reminders (pulled forward from v7.1, '
            'standalone-valuable). v6.6: GST E-invoicing JSON generation. '
            'Reshuffled after IDC Worldwide Intelligent ERP 2025 analysis.'
        ]
        for i, val in enumerate(phase_8_5_values):
            if i < len(new_row.cells):
                new_row.cells[i].paragraphs[0].clear()
                new_row.cells[i].paragraphs[0].add_run(val)
    else:
        # Fallback: append at end if Phase 9 not found
        add_table_row(roadmap_table, [
            'Phase 8.5 -- Proof and Retention',
            'Planned',
            'v6.3 - v6.6',
            'KPI Baseline, Material Estimator standalone, Compliance '
            'Tracker (pulled from v7.1), GST E-invoicing. See Section 1.2.'
        ])
        print('NOTE: Phase 9 not found; Phase 8.5 appended at end instead.')
else:
    print('WARNING: Roadmap table not found')

# ===========================================================================
# 10. Glossary table (Table 21 in v5.0 script convention) --
#     add 4 new terms.
# ===========================================================================
glossary_table = None
# Heuristic: last table in doc with 2-column layout and 'Term' in header.
for t in doc.tables:
    if len(t.columns) == 2:
        header_text = ' | '.join(get_cell_text(c) for c in t.rows[0].cells)
        if 'Term' in header_text and 'Definition' in header_text:
            glossary_table = t  # keep last match (in case there are multiples)

if glossary_table is not None:
    new_glossary_v51 = [
        ['KPI Baseline',
         'Operational metrics captured during the first 7 calendar days of '
         'a tenant lifecycle, used as the comparison base for monthly '
         'savings summaries (v6.3). Rows in tenant_kpi_snapshot tagged '
         'is_baseline=True. See Section 6.24.'],
        ['Material Estimator (standalone)',
         'First-class WhatsApp entry point for material quantity queries, '
         'backed by tenant historical data plus RAG industry norms (v6.4). '
         'Read-only intent; bypasses confirmation flow. See Section 6.25.'],
        ['Compliance Item',
         'A tracked statutory or regulatory obligation with a recurring '
         'due date (v6.5). Seeded per industry at tenant registration. '
         'Owner can deactivate. Reminders fire at T-30, T-7, T-1 days.'],
        ['E-invoice IRP',
         'Government of India Invoice Registration Portal. Mandatory for '
         'tenants with turnover above threshold (Rs 5 crore as of 2026, '
         'decreasing annually). ZetaOps generates compliant JSON (v6.6) '
         'but does not submit directly to IRP.'],
    ]
    for row_vals in new_glossary_v51:
        add_table_row(glossary_table, row_vals)
else:
    print('WARNING: Glossary table not found')

# ===========================================================================
# 11. Footer para -- update version string to v5.1
# ===========================================================================
last_para = doc.paragraphs[-1]
if 'SRS v5.0' in last_para.text:
    last_para.clear()
    last_para.add_run(
        'ZetaOps Copilot  |  SRS v5.1  |  Updated through v6.2 and green-baseline '
        '|  April 20, 2026  |  End of Document'
    )
elif 'End of Document' in last_para.text:
    # Generic catch-all if version string differs slightly
    last_para.clear()
    last_para.add_run(
        'ZetaOps Copilot  |  SRS v5.1  |  Updated through v6.2 and green-baseline '
        '|  April 20, 2026  |  End of Document'
    )

# ===========================================================================
# Save
# ===========================================================================
doc.save(DST)
print(f'Saved: {DST}')
print(f'Paragraphs: {len(doc.paragraphs)}')
print(f'Tables: {len(doc.tables)}')
