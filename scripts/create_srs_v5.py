"""
Script to create ZetaOps_SRS_v5_0.docx from ZetaOps_SRS_v4_0.docx.
Applies all changes specified for SRS v5.0 (updated through v6.2).
"""
import copy
import docx
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import lxml.etree as etree

SRC = r'C:\Users\gaura\OneDrive - ZERO CODE TECHNOLOGY & APPLIED RESEARCH PRIVATE\zPrograms\IITBhubneswar\MSME\LATEST\V5\ZetaOps_SRS_v4_0.docx'
DST = r'C:\Users\gaura\OneDrive - ZERO CODE TECHNOLOGY & APPLIED RESEARCH PRIVATE\zPrograms\IITBhubneswar\MSME\LATEST\V5\ZetaOps_SRS_v5_0.docx'

doc = Document(SRC)


# ---------------------------------------------------------------------------
# Helper: replace text in a paragraph while preserving run formatting
# ---------------------------------------------------------------------------
def replace_para_text(para, old, new):
    """Replace first occurrence of old in para.text using the first run."""
    full = para.text
    if old not in full:
        return False
    # Build a single-run replacement preserving style of first run
    if para.runs:
        r0 = para.runs[0]
        fmt_xml = copy.deepcopy(r0._r)
        # clear all runs
        for r in para.runs:
            r._r.getparent().remove(r._r)
        # insert new run
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


def insert_para_after(doc, idx, text, style='Normal'):
    """Insert a new paragraph after paragraph at idx."""
    ref_para = doc.paragraphs[idx]
    new_para = OxmlElement('w:p')
    ref_para._p.addnext(new_para)
    # Find our new paragraph object
    for i, p in enumerate(doc.paragraphs):
        if p._p is new_para:
            p.style = doc.styles[style]
            p.add_run(text)
            return i
    return -1


def insert_heading_after(doc, idx, text, level=2):
    """Insert a Heading N paragraph after paragraph at idx."""
    ref_para = doc.paragraphs[idx]
    new_para_el = OxmlElement('w:p')
    ref_para._p.addnext(new_para_el)
    for i, p in enumerate(doc.paragraphs):
        if p._p is new_para_el:
            p.style = doc.styles[f'Heading {level}']
            p.add_run(text)
            return i
    return -1


def insert_list_item_after(doc, idx, text):
    """Insert a List Paragraph after paragraph at idx."""
    ref_para = doc.paragraphs[idx]
    new_para_el = OxmlElement('w:p')
    ref_para._p.addnext(new_para_el)
    for i, p in enumerate(doc.paragraphs):
        if p._p is new_para_el:
            p.style = doc.styles['List Paragraph']
            p.add_run(text)
            return i
    return -1


# ===========================================================================
# 1. Title / subtitle / version line  (para [1], [2], [4])
# ===========================================================================
paras = doc.paragraphs
paras[4].clear()
paras[4].add_run('Version 5.0  |  April 2026  |  Updated through v6.2')

# ===========================================================================
# 2. Version history table (Table 0) -- add v5.0 row
# ===========================================================================
t0 = doc.tables[0]
add_table_row(t0, [
    '5.0',
    'Updated through v6.2 -- April 2026. WhatsApp Copilot role limiting and '
    '3-language support (v5.12). Day 1 Simple Table with source/worker_type '
    'fields (v5.16). Manager check-in flow and owner briefing (v5.15). RAG '
    'pipeline with industry templates (v6.1). Industry-aware dynamic UI labels '
    'and RegisterPage auth fix (v6.2). Migration head updated to 023. '
    'ERP Connector Strategy section added (Section 21). Test Environment '
    'section added (Section 22). Python version updated to 3.14.'
])

# ===========================================================================
# 3. Para [17]: "five verticals" -> clarify 4 Plan A + chemical Plan B
# ===========================================================================
p17 = doc.paragraphs[17]
old17 = p17.text
new17 = old17.replace(
    'five verticals: commercial printing,',
    'four active verticals (Plan A): commercial printing,'
).replace(
    'field service. Chemical / process',
    'field service. Chemical / process (Plan B only --'
).replace(
    'field service. Chemical',
    'field service. Chemical'
)
# Full targeted replacement
for r in p17.runs:
    r.text = ''
p17.clear()
p17.add_run(
    'The platform targets MSME operators across four active verticals (Plan A): '
    'commercial printing, discrete manufacturing, metal fabrication, and field '
    'service. Chemical / process industry is reserved for Plan B (mid-market, '
    'ERP-connected customers) -- batch-first entry model differs from Plan A. '
    'The platform serves proprietors (Plan A, WhatsApp-first, no ERP) and '
    'managers/operators within each business.'
)

# ===========================================================================
# 4. Table 3: Industry Verticals -- mark Chemical as Plan B
# ===========================================================================
t3 = doc.tables[3]
# Row 4 is Chemical (0=header, 1=Printing, 2=Mfg, 3=Fab, 4=Chemical, 5=FieldSvc)
chem_row = t3.rows[4]
# Update Product Name cell to indicate Plan B
prod_cell = chem_row.cells[1]
prod_cell.paragraphs[0].clear()
prod_cell.paragraphs[0].add_run('BatchFlow Process Scheduler (Plan B only)')
# Add note to Industry cell
ind_cell = chem_row.cells[0]
ind_cell.paragraphs[0].clear()
ind_cell.paragraphs[0].add_run('Chemical / Process (Plan B)')

# ===========================================================================
# 5. Table 14: Data Model -- update Employee and Machine rows
# ===========================================================================
t14 = doc.tables[14]
# Find Employee row (row index 2)
for row in t14.rows:
    first = get_cell_text(row.cells[0])
    if first == 'Employee':
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(
            'id, tenant_id, full_name, department, employment_type, '
            'base_availability_pct, hourly_rate, overtime_rate, '
            'source (manual|whatsapp|erp_sync), '
            'worker_type (permanent|contractor)'
        )
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run(
            'source and worker_type added in migration 023 (v5.16). '
            'source tracks data origin for v7.0 ERP connector. '
            'worker_type enables contractor labour layer (v7.2). '
            'UI labels adapt per industry.'
        )
    elif first == 'Machine':
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(
            'id, tenant_id, name, machine_type, base_availability_pct, '
            'source (manual|whatsapp|erp_sync)'
        )
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run(
            'source added in migration 023 (v5.16). '
            'Tracks data origin for v7.0 ERP connector. '
            'UI labels adapt per industry.'
        )

# ===========================================================================
# 6. Table 15: Migration Chain -- correct 017-020, add 021/022/023, update head
# ===========================================================================
t15 = doc.tables[15]
# Map revision -> correct description
migration_fixes = {
    '017': (
        '017',
        'WhatsApp phone mapping tables -- phone_tenant_map (phone number E.164, '
        'tenant_id, user_id, is_active, consent_given, alert_preferences JSONB) '
        'and whatsapp_conversations (Factory GPT training data: role, content, '
        'language, session_id, consent_given). Introduced v5.0.'
    ),
    '018': (
        '018',
        'WhatsApp RBAC -- adds display_name (VARCHAR 100, nullable) and '
        'phone_role (VARCHAR 20, NOT NULL, default owner; values: owner | '
        'manager | viewer) to phone_tenant_map. Introduced with role limiting support.'
    ),
    '019': (
        '019',
        'AI usage tracking -- adds ai_queries_today (INT DEFAULT 0), '
        'ai_tokens_today (INT DEFAULT 0), ai_queries_date (DATE NULL), '
        'industry_type (VARCHAR 50 NULL) to tenants. Uses IF NOT EXISTS for '
        'safe re-runs. Introduced v4.0.9.'
    ),
    '020': (
        '020',
        'Unavailability and allocation -- adds allocation_pct (FLOAT NULL) to '
        'job_assignments; creates employee_leaves table (tenant_id, employee_id, '
        'start_date, end_date, reason); creates machine_downtimes table '
        '(tenant_id, machine_id, start_date, end_date, reason). Introduced v4.0.9.'
    ),
}

for row in t15.rows:
    rev = get_cell_text(row.cells[0])
    if rev in migration_fixes:
        new_rev, new_desc = migration_fixes[rev]
        row.cells[0].paragraphs[0].clear()
        row.cells[0].paragraphs[0].add_run(new_rev)
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(new_desc)

# Add 021, 022, 023 rows
add_table_row(t15, [
    '021',
    'Job locking -- adds is_locked (BOOLEAN NOT NULL DEFAULT FALSE) to jobs. '
    'Introduced v4.0.9.'
])
add_table_row(t15, [
    '022',
    'Original dates -- adds original_start_date and original_end_date (DATE NULL) '
    'to jobs. Introduced v4.0.9.'
])
add_table_row(t15, [
    '023',
    'Source and worker type -- adds source (VARCHAR 20, server_default=manual) to '
    'employees and machines; adds worker_type (VARCHAR 20, server_default=permanent) '
    'to employees. Current head. Introduced v5.16.'
])

# ===========================================================================
# 7. Table 17: Tech Stack -- update Python and migration head
# ===========================================================================
t17 = doc.tables[17]
for row in t17.rows:
    layer = get_cell_text(row.cells[0])
    tech = get_cell_text(row.cells[1])
    if layer == 'Backend' and 'Python 3.12' in tech:
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(
            tech.replace('Python 3.12', 'Python 3.14')
        )
    elif layer == 'ORM + Migrations' and 'migration head: 020' in tech:
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(
            tech.replace('migration head: 020', 'migration head: 023')
        )

# ===========================================================================
# 8. Para [361]: Python 3.12 constraint -- update to 3.14
# ===========================================================================
p361 = doc.paragraphs[361]
if 'Python 3.12' in p361.text:
    p361.clear()
    p361.add_run(
        'Python 3.14 is the production runtime. Earlier versions (3.12, 3.11) '
        'are not tested. bcrypt is imported directly -- passlib is incompatible '
        'with Python 3.12+.'
    )

# ===========================================================================
# 9. Table 18: Known Gaps -- update rows 13/14/15, add new gaps
# ===========================================================================
t18 = doc.tables[18]
for row in t18.rows:
    num = get_cell_text(row.cells[0])
    if num == '13':
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run('DONE v5.10')
        row.cells[3].paragraphs[0].clear()
        row.cells[3].paragraphs[0].add_run(
            'Morning briefing, conflict alert, job delay alert all live in mock mode.'
        )
        row.cells[4].paragraphs[0].clear()
        row.cells[4].paragraphs[0].add_run('v5.10')
    elif num == '14':
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run(
            'Meta Business portfolio link'
        )
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run('Blocked')
        row.cells[3].paragraphs[0].clear()
        row.cells[3].paragraphs[0].add_run(
            'Zero Zeta Business Portfolio appeal submitted Apr 8. In review.'
        )
        row.cells[4].paragraphs[0].clear()
        row.cells[4].paragraphs[0].add_run('Blocked -- Meta review')
    elif num == '15':
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run('Interakt integration and production config')
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run('Blocked')
        row.cells[3].paragraphs[0].clear()
        row.cells[3].paragraphs[0].add_run(
            'Pending Meta approval. New SIM obtained, not on consumer WhatsApp.'
        )
        row.cells[4].paragraphs[0].clear()
        row.cells[4].paragraphs[0].add_run('Blocked -- Meta review')

# Add new gap rows for v5.12 through v6.2
new_gaps = [
    ['16', 'WhatsApp role limiting (owner/manager/viewer)', 'DONE v5.12',
     'phone_role enforcement in place. Blocked actions never reach AI.', 'v5.12'],
    ['17', '3-language support (Hindi / Hinglish / English)', 'DONE v5.12',
     'detect_language() in whatsapp_responses.py. LANGUAGE_INSTRUCTION in system prompt.', 'v5.12'],
    ['18', 'Day 1 Simple Table (seed worker + machine data)', 'DONE v5.16',
     'First screen after registration. source and worker_type fields in DB.', 'v5.16'],
    ['19', 'Manager check-in flow (7:00am WhatsApp input)', 'DONE v5.15',
     'APScheduler triggers check-in. Absent worker -> substitute suggestion.', 'v5.15'],
    ['20', 'Owner briefing (7:15am WhatsApp output)', 'DONE v5.15',
     'Single clean briefing generated from manager inputs. No questions to owner.', 'v5.15'],
    ['21', 'RAG pipeline with industry templates', 'DONE v6.1',
     'Flat file MVP. rag_data/_templates/{industry}/ seeded at registration.', 'v6.1'],
    ['22', 'Industry-aware dynamic UI labels', 'DONE v6.2',
     'useLabels() hook. Sidebar and page titles dynamic per industry_type.', 'v6.2'],
    ['23', 'RegisterPage auth bug (localStorage bypass)', 'DONE v6.2',
     'AuthContext.register() now called correctly. localStorage direct call removed.', 'v6.2'],
    ['24', 'Voice notes via WhatsApp (Whisper API)', 'Blocked',
     'Blocked by Meta/Interakt go-live (v5.11). Needs real inbound audio.', 'v5.13'],
    ['25', 'RAG pgvector migration', 'Planned',
     'Migration 024 -- tenant_knowledge_base table with embeddings. Flat file structure unchanged.', 'v6.3'],
]
for gap in new_gaps:
    add_table_row(t18, gap)

# ===========================================================================
# 10. Table 20: Roadmap -- update Phases 7 and 8, add Phase 9
# ===========================================================================
t20 = doc.tables[20]
for row in t20.rows:
    phase = get_cell_text(row.cells[0])
    if 'Phase 7' in phase:
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run('Done (mock mode)')
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run('v5.12, v5.15, v5.16')
        row.cells[3].paragraphs[0].clear()
        row.cells[3].paragraphs[0].add_run(
            'Role limiting + 3-language support (v5.12). Day 1 Simple Table with '
            'source/worker_type (v5.16). Manager check-in flow + owner briefing '
            '(v5.15). WhatsApp go-live blocked by Meta review.'
        )
    elif 'Phase 8' in phase:
        row.cells[1].paragraphs[0].clear()
        row.cells[1].paragraphs[0].add_run('Done')
        row.cells[2].paragraphs[0].clear()
        row.cells[2].paragraphs[0].add_run('v6.0, v6.1, v6.2')
        row.cells[3].paragraphs[0].clear()
        row.cells[3].paragraphs[0].add_run(
            'Schema context layer (v6.0). RAG pipeline flat file MVP, industry '
            'templates for 4 verticals (v6.1). Dynamic UI labels via useLabels() '
            'hook, RegisterPage auth fix (v6.2).'
        )

# Add Phase 9
add_table_row(t20, [
    'Phase 9 -- ERP Connector',
    'Planned',
    'v7.0+',
    'Python connector for SAP / Tally / Excel. Pulls employee list, active '
    'orders, leaves and machine downtime. Daily sync at 6:30am. source field '
    'activated for erp_sync. Same scheduling engine -- zero changes. '
    'Contractor labour layer (v7.2). Compliance tracker (v7.1).'
])

# ===========================================================================
# 11. New sections 6.17-6.23 -- insert after section 6.16
# ===========================================================================
# Find para index of "6.16 CSV / Excel Import" heading (index 173)
idx616 = find_para_index(doc, '6.16 CSV / Excel Import')

# We need to find the LAST paragraph of section 6.16 (before the next Heading 1)
# Section 6.16 ends just before the "7. Bug Fixes" heading
idx_next_h1 = find_para_index(doc, '7. Bug Fixes')

# We'll insert new sections BEFORE the "7. Bug Fixes" heading
# But first we need to locate where 6.16 ends
# Insert in reverse so index positions stay valid (insert before heading 7)
insert_point = idx_next_h1 - 1  # last para before "7. Bug Fixes"

new_sections_617_623 = [
    # (style, text)
    ('Heading 2', '6.17 WhatsApp Copilot -- Role Limiting (v5.12)'),
    ('Normal', 'Three distinct WhatsApp roles constrain what each phone number can do.'),
    ('List Paragraph', 'owner -- full access: read schedule, approve actions, receive briefings.'),
    ('List Paragraph', 'manager -- operational access: attendance, machine status, job updates. Blocked from financial and tenant-level actions.'),
    ('List Paragraph', 'viewer -- read-only: status queries only, no write operations.'),
    ('Normal', 'Role check runs in detect_write_intent() BEFORE the AI layer is called. Blocked actions never reach Groq API. Enforcement is structural, not prompt-based.'),
    ('Heading 2', '6.18 WhatsApp Copilot -- 3-Language Support (v5.12)'),
    ('Normal', 'Every inbound WhatsApp message is classified once: detect_language(text) returns hindi | hinglish | en. The classification drives the LANGUAGE_INSTRUCTION injected into _build_system_prompt(). AI responds in the detected language throughout the conversation session.'),
    ('List Paragraph', 'Hindi -- Devanagari script detected (Unicode range).'),
    ('List Paragraph', 'Hinglish -- Latin-script marker words (aaj, kaam, nahi, theek) detected.'),
    ('List Paragraph', 'English -- default when neither Hindi nor Hinglish markers found.'),
    ('Heading 2', '6.19 Day 1 Simple Table (v5.16)'),
    ('Normal', 'The first screen a new tenant sees after registration -- before the Gantt chart, before jobs. Designed for a proprietor with zero ERP and zero patience.'),
    ('List Paragraph', 'Input: worker name + primary skill (one word: welder, stitching, cutting, finishing) + worker type (permanent | contractor).'),
    ('List Paragraph', 'Input: machine name + machine type.'),
    ('List Paragraph', 'Nothing else -- no hourly rates, no availability percentages, no shift timings on Day 1.'),
    ('List Paragraph', 'Onboarding question: "Do you have employee/job data in SAP, Tally, or Excel?" Yes -> ERP path placeholder (v7.0). No -> proceed with this table.'),
    ('Normal', 'Migration 023 adds source (VARCHAR 20, server_default=manual) to employees and machines, and worker_type (VARCHAR 20, server_default=permanent) to employees. These fields cost one column now. Removing them forces a full rewrite at v7.0.'),
    ('Heading 2', '6.20 Manager Check-in Flow (v5.15)'),
    ('Normal', 'APScheduler triggers a WhatsApp message to the manager phone at 7:00am. The manager replies naturally; the system parses names against the Day 1 seed table.'),
    ('List Paragraph', '"Aaj kaun kaun aaya?" -- manager lists present workers. Absent workers identified by diff against seed table.'),
    ('List Paragraph', 'Absent worker -> skill looked up -> substitute suggested immediately from available pool.'),
    ('List Paragraph', '"Machines theek hain?" -- manager flags downtime. Writes to machine_downtimes table.'),
    ('List Paragraph', '"Aaj ke main kaam kya hain?" -- manager states work. Maps to skill requirements.'),
    ('List Paragraph', 'All inputs write to the availability engine. Conversation ends: "Got it. Sahab ko summary bhej raha hoon."'),
    ('Heading 2', '6.21 Owner Briefing (v5.15)'),
    ('Normal', 'At 7:15am a single clean briefing is generated FROM the manager inputs, not from scheduled data alone. Format: who is present, who is absent, skill gap, order at risk, one suggested action. No questions to owner -- signal only, zero input required from owner phone.'),
    ('Normal', 'After one week of daily check-ins: real attendance patterns, skill usage, and machine reliability are all in the system passively.'),
    ('Heading 2', '6.22 RAG Pipeline (v6.1)'),
    ('Normal', 'Industry-aware knowledge injected into every AI query via a flat-file Retrieval-Augmented Generation pipeline.'),
    ('List Paragraph', 'Folder: backend/rag_data/_templates/{industry}/ -- default knowledge per industry (4 verticals: printing, manufacturing, fabrication, field_service). Chemical excluded -- batch-first model differs.'),
    ('List Paragraph', 'Tenant override: backend/rag_data/{tenant_id}/ -- tenant-specific knowledge seeded at registration from the industry template.'),
    ('List Paragraph', '_build_system_prompt() injects tenant RAG context before every AI query.'),
    ('List Paragraph', 'RAG data is tenant-isolated -- never read from another tenant folder.'),
    ('List Paragraph', 'Migration path: flat files (v6.1) -> pgvector (v6.3). Folder structure unchanged across migration.'),
    ('Heading 2', '6.23 Industry-Aware Dynamic Labels (v6.2)'),
    ('Normal', 'All user-visible entity labels are driven by industry_type, never hardcoded.'),
    ('List Paragraph', 'IndustryContext.tsx reads industry_type from AuthContext at login.'),
    ('List Paragraph', 'useLabels() hook returns labels.jobs, labels.employees, labels.machines per industry.'),
    ('List Paragraph', 'Sidebar and page titles use useLabels() -- zero hardcoded "Jobs", "Employees", "Machines" strings in src/pages/ or src/components/.'),
    ('List Paragraph', 'Example: printing tenant sees "Print Jobs" / "Press Operators" / "Presses". Fabrication tenant sees "Fabrication Orders" / "Fitters" / "CNC Machines".'),
    ('Normal', 'Verification: grep -r \'"Jobs"\\|"Machines"\\|"Employees"\' frontend/src/pages/ must return empty.'),
]

# Insert in forward order - addprevious(new_el) inserts immediately before ref_para,
# so each new element goes between the previous insert and ref_para (forward accumulation).
idx_7bugfixes = find_para_index(doc, '7. Bug Fixes')
ref_para = doc.paragraphs[idx_7bugfixes]

for style, text in new_sections_617_623:
    new_el = OxmlElement('w:p')
    ref_para._p.addprevious(new_el)
    # Find the new paragraph
    for p in doc.paragraphs:
        if p._p is new_el:
            try:
                p.style = doc.styles[style]
            except Exception:
                pass
            p.add_run(text)
            break

# ===========================================================================
# 12. Section 21: ERP Connector Strategy
#     Section 22: Test Environment
#     Insert before footer paragraph (last paragraph)
# ===========================================================================
footer_idx = len(doc.paragraphs) - 1
footer_para = doc.paragraphs[footer_idx]

section_21_22 = [
    ('Heading 1', '21. ERP Connector Strategy'),
    ('Normal',
     'ZetaOps Copilot is structured as a two-plan product. Plan A (MSME, no ERP) '
     'uses WhatsApp as the primary data input channel. Plan B (mid-market, has ERP) '
     'uses a Python connector that feeds the same scheduling engine. The same '
     'briefing reaches the owner in both plans.'),
    ('Normal',
     'The connector pulls three things only: employee list with skills, active orders, '
     'and leaves / machine downtime. A daily sync job runs at 6:30am -- before the '
     'manager check-in and owner briefing window.'),
    ('List Paragraph', 'Supported systems (v7.0): SAP, Tally, Excel export.'),
    ('List Paragraph', 'source field (migration 023) activates erp_sync value when connector is live.'),
    ('List Paragraph', '4 Plan A verticals x mid-market addressable without rebuilding the engine.'),
    ('List Paragraph', 'Chemical / process industry enters via Plan B (batch-first entry model).'),
    ('Normal',
     'The structural decision that makes v7.0 a sprint: source field on Employee and '
     'Machine added in migration 023. Removing it forces a full schema rewrite at v7.0.'),
    ('Heading 1', '22. Test Environment'),
    ('Normal',
     'Backend tests use a two-tier strategy: unit tests run against SQLite in-memory '
     '(StaticPool); integration tests require real PostgreSQL and are marked with '
     '@pytest.mark.integration.'),
    ('List Paragraph',
     'Unit tier (pytest -m "not integration"): test_scheduler_engine.py, '
     'test_conflict_detection.py, test_skills.py, test_alembic_migrations.py. '
     'SQLite in-memory with StaticPool ensures DDL and DML share the same connection.'),
    ('List Paragraph',
     'Integration tier (pytest -m integration): test_jobs_api.py, '
     'test_assignment_service.py. Hit real PostgreSQL. Skipped in CI. '
     'Run manually: pytest tests/ -m integration -v'),
    ('List Paragraph',
     'PG-only column types (ARRAY, JSONB) are patched to JSON in conftest.py '
     'so SQLite can create tables for unit tests.'),
    ('Normal',
     'Test tenant: what@what.what / qazx1234 / tenant_id=12 / phone: +919876543210. '
     'Used for manual WhatsApp pipeline testing in WHATSAPP_MOCK_MODE=True.'),
    ('Normal',
     'Verification gates (must pass before any commit is merged):\n'
     'npx tsc --noEmit -- zero errors.\n'
     'python -m py_compile app/ -- zero errors.\n'
     'pytest tests/ -m "not integration" -v -- zero failures.\n'
     'alembic heads -- exactly one head (023).'),
]

for style, text in section_21_22:
    new_el = OxmlElement('w:p')
    footer_para._p.addprevious(new_el)
    for p in doc.paragraphs:
        if p._p is new_el:
            try:
                p.style = doc.styles[style]
            except Exception:
                pass
            p.add_run(text)
            break

# ===========================================================================
# 13. Table 21: Glossary -- add new terms
# ===========================================================================
t21 = doc.tables[21]
new_glossary = [
    ['source field',
     'VARCHAR 20 column on Employee and Machine (migration 023). Values: manual '
     '(Day 1 Simple Table), whatsapp (captured via conversation), erp_sync (v7.0 '
     'ERP connector). Structural decision that keeps v7.0 a sprint not a rewrite. '
     'Never remove.'],
    ['worker_type',
     'VARCHAR 20 column on Employee (migration 023). Values: permanent (salaried '
     'staff), contractor (daily-rate labour pool). Enables contractor labour layer '
     'in v7.2.'],
    ['Plan A',
     'MSME customer tier. WhatsApp-first, no ERP. 4 active verticals: printing, '
     'manufacturing, fabrication, field_service.'],
    ['Plan B',
     'Mid-market customer tier. Has ERP (SAP, Tally, Excel). Python connector feeds '
     'same scheduling engine. Chemical / process industry enters here.'],
    ['Day 1 Simple Table',
     'Onboarding screen shown immediately after registration. Collects worker name + '
     'primary skill + worker_type, and machine name + machine_type. Nothing else -- '
     'no rates, no shift timings on Day 1. Introduced v5.16.'],
    ['Manager Check-in Flow',
     'WhatsApp input channel triggered by APScheduler at 7:00am. Manager reports '
     'attendance, machine status, and active orders. Writes to availability engine. '
     'Introduced v5.15.'],
    ['Owner Briefing',
     'WhatsApp output channel at 7:15am. Single clean signal generated from manager '
     'inputs: who present, who absent, skill gap, order at risk, one suggested action. '
     'No questions asked to owner. Introduced v5.15.'],
]
for row_vals in new_glossary:
    add_table_row(t21, row_vals)

# ===========================================================================
# 14. Footer para -- update version string
# ===========================================================================
last_para = doc.paragraphs[-1]
if 'SRS v4.0' in last_para.text or 'v5.9' in last_para.text:
    last_para.clear()
    last_para.add_run(
        'ZetaOps Copilot  |  SRS v5.0  |  Updated through v6.2  |  April 2026  |  End of Document'
    )

# ===========================================================================
# Save
# ===========================================================================
doc.save(DST)
print(f'Saved: {DST}')
print(f'Paragraphs: {len(doc.paragraphs)}')
print(f'Tables: {len(doc.tables)}')
