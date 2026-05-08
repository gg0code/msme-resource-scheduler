*ZetaOps Copilot  |  Software Requirements Specification  |  v3.0*

**ZetaOps Copilot**

Multi-Industry AI-Powered Resource Scheduling Platform

Software Requirements Specification (SRS)

Version 6.6  |  Updated 2026-05-07; shipped through v6.3.17 (WhatsApp owner-bypass entity writes). Migration head 032. See CHANGELOG.md and DELIVERY_LEDGER.md for the per-version narrative across v6.3.1 through v6.3.17.

| **Version** | **Notes** |
| --- | --- |
| 1.0 | Original SRS — March 2026. Single-industry (printing/manufacturing) MSME scheduling platform. |
| 2.0 | Updated through V3.9 — March 2026. Feature flag architecture, release ladder, AI Copilot, bug fixes, known gaps. |
| 3.0 | Updated through v4.0.9 — March 2026. Multi-industry platform renamed ZetaOps Copilot. 5 industry verticals, industry-aware AI, demo seeder, CSS theme engine, onboarding checklist, knowledge graph roadmap. |
| **4.0** | Updated through v5.9 — April 2026. WhatsApp Copilot pipeline (v5.0-v5.9): AI simulator, phone linking, intent confirmation flow, scheduler v3 gap visualisation and priority push, proactive alerts. Schema context layer clarification (Section 17). AI Copilot query architecture updated. v6.0 Factory GPT path defined. |
| 5.0 | Updated through v6.2 -- April 2026. WhatsApp Copilot role limiting and 3-language support (v5.12). Day 1 Simple Table with source/worker_type fields (v5.16). Manager check-in flow and owner briefing (v5.15). RAG pipeline with industry templates (v6.1). Industry-aware dynamic UI labels and RegisterPage auth fix (v6.2). Migration head updated to 023. ERP Connector Strategy section added (Section 21). Test Environment section added (Section 22). Python version updated to 3.14. |
| 5.1 | Updated through v6.2.2-test-recovery (Apr 20 2026). Reshuffled v6.x roadmap after IDC Worldwide Intelligent ERP 2025 analysis: v6.3 KPI Baseline + Savings Summary (retention moat), v6.4 Material Estimator as standalone WhatsApp surface (acquisition wedge), v6.5 Compliance Tracker (pulled forward from v7.1), v6.6 GST E-Invoicing JSON. Old v6.3 RAG pgvector becomes v6.7. Old v6.5 Supervisor Agent becomes v6.8. Added Section 1.1 Version Strategy and Section 1.2 Current State. Added functional requirement Sections 6.24-6.27 for new v6.3-v6.6 features. Test suite recovered to 199 passing (v6.2.2-test-recovery). |
| **6.4** | Updated April 28, 2026 following v6.3.0-whatsapp-industry release. v6.4 strategy revised: WhatsApp is promoted to Primary Entry Gate -- a formally configurable signup-time routing decision (entry_mode field on Tenant). Top-tier role expands from single Owner to a role group covering Owner, Factory Manager, Co-Owner -- all with equal operational authority; commercial actions remain Owner-only. Configurable morning and evening daily push briefings dispatched on WhatsApp to top-tier users. New Section 6.28 (WhatsApp as Primary Entry Gate) covers signup changes, role expansion, and briefing dispatch. Material Estimator surface (previous v6.4) renumbered to v6.5; Compliance Tracker to v6.6; GST E-Invoicing to v6.7; RAG pgvector to v6.8; Supervisor Agent to v6.9. Migration 027 added (entry_mode, size_segment, briefing config, role enum extension). Re-baselined v6.4 acceptance criteria. Section 1.2 Current State updated. Section 16 Implementation Roadmap renumbered. |
| **6.5** | Updated April 29, 2026 during v6.3.4 in progress. Documentation-only release. (1) Adds Section 6.28.4 (UI Consolidation) reflecting the v6.3.5 iteration scope: drop the standalone /whatsapp page (functionality folded into a single Invite modal opened from Settings -- Team and Roles); redesign Team and Roles as a phone-shaped table where Phone and WhatsApp connection status are first-class columns and synthesised invite-XXX@invite.zetaops.com placeholders no longer leak into API responses (TeamMemberOut.email becomes Optional[str]); add a new InviteMemberModal with channel picker (WhatsApp / Desktop) that conditionally swaps the phone field for an email field; add a minimal post-signup landing page at /welcome for whatsapp_first proprietors per Section 6.28 spec, replacing the transitional /connect-whatsapp placeholder. (2) Documents migration 028 (events audit table introduced in v6.3.3) in Section 9.2 migrations table, and advances the migration head pointer in Section 1.2 and Section 5 from 023 to 028. (3) Corrects the stale "Current head: 020" callout in Section 9.2 to read 028. No new schema introduced by v6.5 itself, no new feature flag (whatsapp_entry_gate from v6.4 already covers the UI consolidation). Updates Section 16 Phase 8.5 to include v6.3.5 deliverables. |
| 6.6 | Updated May 7, 2026 covering v6.3.6 -- v6.3.17. (1) Section 1.2 header banner advanced to reflect shipped state through v6.3.17 (WhatsApp owner-bypass entity writes); single summary bullet added to the SHIPPED list pointing readers to CHANGELOG.md and DELIVERY_LEDGER.md for per-version detail. (2) Migration head pointer in Reference Documents advanced from 028 to 032 reflecting the chain that landed in this window: 029 extraction_candidates staging table (v6.3.13), 030 confirmation_state columns on extraction_candidates (v6.3.15 revised owner-confirmed promotion), 031 first_briefing_sent_at + engagement_ladder_state on tenants (v6.3.16 Day-7 First-Insight Gate), 032 source column on skills (v6.3.17 WhatsApp owner-bypass entity writes). (3) New audit-event namespaces introduced in this window: extraction.* (candidate promotion + owner-confirmation cycle), engagement.day7_owner_* (Day-7 gate sent / suppressed / failed), entity.owner_added (owner-bypass writes). (4) New entity-source value whatsapp_owner distinguishes owner-asserted writes from manager-typed (whatsapp) and bot-promoted (whatsapp_inferred) rows. Skill table now carries the same source column as Employee/Machine. No new functional requirement section added by this Document v6.6 -- per-version specs continue to live in CHANGELOG.md. |

# 1. Executive Summary

ZetaOps Copilot (formerly MSME Resource Scheduler) is a multi-tenant, cloud-based SaaS platform that enables small and medium enterprises across five industry verticals to maximise job profitability through intelligent assignment of resources, real-time availability tracking, and AI-powered scheduling assistance.

As of v5.9 (April 2026), the platform has evolved significantly beyond its original single-industry design. The v4.0 series introduced a multi-industry configuration layer. The v5.x series has added a WhatsApp Copilot channel — enabling AI-powered scheduling assistance over WhatsApp using the same tool-calling architecture as the web Copilot.

The platform is structured as a progressive release ladder — from a simple job board (V1) to a fully AI-powered, industry-aware scheduling copilot (V4). All tiers are controlled by a single feature flag configuration file with no code changes between tiers.

> **NOTE** The application is production-ready for V4 tier deployment as of v4.0.9. The WhatsApp Copilot pipeline is complete through v5.9 (scheduler v3, gap visualisation, proactive alerts in test). The schema context layer for AI multi-hop reasoning is documented in Section 17. Factory GPT (v6.0) is the next strategic milestone.

## 1.1 Version Strategy

This document uses two independent version number systems. Understanding the distinction prevents documentation drift.

Product Version (used in git tags, CHANGELOG, customer-facing communications). Format vMAJOR.MINOR.PATCH. MAJOR denotes product era: V5 = WhatsApp-first MSME platform, V6 = AI-first intelligent platform, V7 = ERP-connected mid-market platform. MINOR increments with each shipped feature release within that era. PATCH is used for non-feature releases such as bug fixes or test recovery. Current state as of this document: v6.3.0-whatsapp-industry (tagged April 22, 2026); next planned release v6.4 (WhatsApp as Primary Entry Gate, see Section 6.28).

Document Version (this SRS only). Format Document vX.Y. Independent of product version. This is SRS Document v6.5. It describes product releases v5.0 through v6.3.4 (shipped or in progress) and v6.3.5 through v7.2 (planned). v6.5 is a documentation release that adds Section 6.28.4 (UI Consolidation) reflecting the v6.3.5 iteration scope; no new product features beyond v6.4 are introduced.

Rule: where this document refers to a version number without a "Document" prefix, the reference is to a Product Version.

Note on other repository artifacts: the development prompt (ZETAOPS_DEV_PROMPT.md in the repository root) does not maintain an internal version number. Its edit history is tracked by git. When this SRS references it, the reference is to the current file in the repository, not to any version scheme.

## 1.2 Current State (as of 2026-05-07)

At-a-glance state of all features, reconciled against the actual git tag history on `origin/v5-whatsapp` as of HEAD `e74d264` (2026-05-07). For per-release detail (commit hashes, tests, acceptance criteria pass counts, deferred items), the authoritative sources are `CHANGELOG.md` (release narrative) and `DELIVERY_LEDGER.md` (current shipped state). Where this section, the CHANGELOG, and the ledger disagree, the **git tag and its commit message are ground truth**; the ledger wins for "is it shipped"; this SRS wins for "what is the spec." Migration head as of HEAD is **032**.

### Shipped (production-ready in mock mode; awaiting Meta go-live for real WhatsApp traffic)

V5 era — WhatsApp-first MSME platform (10 tagged releases):

- **v5.0-simulator-working** (Mar 29) — WhatsApp router working: fixed sync/async session mismatch, removed `created_at`/`updated_at` from model, simulator returning correct responses.
- **v5.2-voice-notes** (Mar 30) — voice note support: Groq Whisper transcription + simulate-voice endpoint.
- **v5.4-alerts-verified** (Mar 30) — proactive alerts verified: briefing, delays, conflicts all firing correctly.
- **v5.6-confirmation-flow** (Mar 29) — confirmation flow working: intent detection, sync DB writes, absent marking verified.
- **v5.7-ts-fixes** (Apr 3) — merged ZetaOps master prompt v1.1 from `v4-dev`.
- **v5.8-frontend-clean** (Apr 4) — `config.py` + `main.py` WhatsApp settings; 0 TypeScript errors across all frontend files.
- **v5.9-scheduler-v3** (Apr 7) — merged `requirements.txt` from `v4-dev`.
- **v5.10-proactive-alerts** / **v5.12-role-language** (Apr 7) — both tags point to the **same commit**: `whatsapp_alerts.py` v2.0 — fix `_get_conflicts`, add full file docs. Role limiting and 3-language support were folded into this commit alongside proactive-alerts hardening.
- **v5.15-manager-checkin** (Apr 10) — manager check-in flow + owner briefing from check-in.
- **v5.16-day1-onboarding** (Apr 9) — Day 1 onboarding: three entry paths, `source` + `worker_type` fields, CSV import.

V6 era — AI-first intelligent platform (33 tagged releases):

- **v6.1-rag-pipeline** (Apr 10) — combined v6.0 schema context + v6.1 RAG pipeline (industry-aware AI). Single tagged release covering both spec sections.
- **v6.2-ts-clean** (Apr 13) — resolved 39 TypeScript errors across 5 frontend files. Industry-aware dynamic UI labels and the RegisterPage auth fix described in earlier CHANGELOG entries land later in the v6.2.x series, not at this tag.
- **v6.2.1-scheduler-fixes** (Apr 14) — lock button, resource-availability endpoint, scheduler result panel, conflict dedup, health check, lock state sync in conflict panel.
- **v6.2.2-test-recovery** (Apr 20) — `StaticPool` for in-memory SQLite; fixes `test_skills.py` cross-connection state issues. 199 passing.
- **v6.2.3-test-audit** (Apr 22) — SRS v5.1 audit; 105 new tests; documents BUG-1 and BUG-2.
- **v6.2.4-bugfixes** (Apr 22) — tighten `start_date` and `end_date` to `date` type (BUG-2).
- **v6.2.5-cleanup** (Apr 22) — replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.
- **v6.2.6-registration-seed** (Apr 22) — wire up demo seeding on registration (BUG-3).
- **v6.2.7-industry-type** (Apr 22) — add `industry_type` to `RegisterRequest`; persist on Tenant (BUG-4).
- **v6.2.8-audit-closed** (Apr 22) — gitignore per-tenant `rag_data` folders.
- **v6.2.9-me-industry** (Apr 22) — return `industry_type` on `/auth/me` endpoint (BUG-5).
- **v6.3.0-whatsapp-industry** (Apr 22) — use tenant industry when linking phone (BUG-6). Foundation for the v6.3.x WhatsApp work that followed.
- **v6.3.1** (Apr 28) — WhatsApp entry gate foundation: schema + lookup helpers.
- **v6.3.2** (Apr 28) — signup flow wires `entry_mode` + `size_segment` + `phone` + `next_step`.
- **v6.3.2.1** (Apr 28) — split contexts into Provider + hook files for Vite Fast Refresh.
- **v6.3.2.2** (Apr 28) — quick set-state + exhaustive-deps fixes (5 lint problems eliminated).
- **v6.3.2.3** (Apr 29) — backend + frontend hygiene cleanup.
- **v6.3.2.4** (Apr 29) — fix AI prompt format-string crash (`'"mode"'` `KeyError`).
- **v6.3.3** (Apr 29) — top-tier role group + permission gating.
- **v6.3.4** (Apr 29) — daily push briefings dispatcher (cron + manual trigger).
- **v6.3.5** (Apr 29) — WhatsApp UI consolidation + 3 production bugs fixed via live E2E.
- **v6.3.6** (Apr 29) — dead-code sweep + 3 React 19 lint errors fixed.
- **v6.3.7** (May 3) — Meta Cloud API direct send + Phase 1 alerts refactor.
- **v6.3.8** (May 3) — Phase 2 Interakt removal + E.164 inbound normalization.
- **v6.3.9** (May 3) — Groq `tool_use_failed` retry + dev-script industry snapshot fix.
- **v6.3.10** (May 4) — Bootstrap UI trim + `tenant_id` join-table fix.
- **v6.3.11** (May 4) — pattern-aware briefing intelligence (signal evaluator framework).
- **v6.3.12** (May 5) — Day-1 onboarding sequence.
- **v6.3.13** (May 5) — `extraction_candidates` staging table.
- **v6.3.14** (May 5) — entity extractor service.
- **v6.3.15** (revised) (May 6) — owner-confirmed candidate promotion.
- **v6.3.16** (May 6) — Day-7 First-Insight Gate.
- **v6.3.17** (May 7) — WhatsApp owner-bypass entity writes. Current `HEAD` of `v5-whatsapp`.

### Blocked (external dependency — Meta Business portfolio review)

- **v5.11** WhatsApp Go-Live — Zero Zeta portfolio appeal in review. **No git tag exists**; this is a planning placeholder for the production cutover, not a shipped release. Note: v6.3.7 / v6.3.8 (May 3) shipped Meta Cloud API direct send and removed Interakt as a dependency — the architectural step that v5.11 was originally meant to gate has effectively been taken; what remains is the Meta portfolio approval itself.
- **v5.13** Voice Notes (Whisper transcription) — depends on v5.11. Note: a `v5.2-voice-notes` tag exists (Whisper transcription + simulate-voice endpoint), so the *implementation* is shipped; what's blocked is real inbound audio from production WhatsApp.
- **v5.14** Live End-to-End Test on real device — depends on v5.11 and v5.13.

### Next to build

V6 era — in progress / planned:

- **v6.3 KPI Baseline + Monthly Savings Summary** (Section 6.24). **No tag yet.** Capture in progress per `CLAUDE.md`. Builds on the v6.3.0-whatsapp-industry tenant-isolation foundation.
- **v6.3.18** message formatter, **v6.3.19** per-tenant push config — prerequisites for the v6.4.0 full engagement ladder per `CLAUDE.md`. **No tags yet.**
- **v6.4 WhatsApp as Primary Entry Gate** (Section 6.28) — formal entry-mode routing decision (small tenants land on WhatsApp, large tenants land on desktop), top-tier role expansion, configurable morning + evening daily push briefings on WhatsApp. Note: v6.3.1 / v6.3.2 / v6.3.3 / v6.3.4 already shipped the schema, signup wiring, role group, and dispatcher pieces of this — what remains for the v6.4 tag is integration and acceptance-criteria sign-off.
- **v6.4.0 full engagement ladder** — Day-1 ack, Day-3 rhythm, Day-7 manager mirror, conditional nudges; reuses and extends `tenants.engagement_ladder_state`.
- **v6.5 Material Estimator** as standalone WhatsApp surface — acquisition wedge. Backend already shipped in v3.9.8. See Section 6.25.
- **v6.6 Compliance Deadline Tracker** — pulled forward from v7.1. See Section 6.26.
- **v6.7 GST E-Invoicing JSON generation** — natural extension of v6.6. See Section 6.27.
- **v6.8 RAG pgvector migration** — infrastructure only.
- **v6.9 Supervisor Agent** — depends on v6.3 – v6.8.

V7 era — planned (mid-market, ERP-connected):

- **v7.0** ERP Connector Layer (SAP / Tally / Excel). Chemical / process enters here.
- **v7.1** Contractor Labour Layer (renumbered after compliance moved forward to v6.6).
- **v7.2** Reserved slot.

### Reference documents (in repository)

- `ZETAOPS_DEV_PROMPT.md` — build standards, architectural rules, session continuity protocol.
- `CHANGELOG.md` — per-release narrative.
- `DELIVERY_LEDGER.md` — current shipped state with feature flags, migrations, acceptance counts.
- `CLAUDE.md` — working context for AI sessions and humans new to the repo.
- Product version scheme: Section 1.1 of this document.
- Detailed feature specs: Sections 6.17 – 6.28 of this document.
- Migration chain truth: Section 9.2 of this document. Current head: **032**.

# 2. Business Context & Problem Statement

## 2.1 Industry Context

The platform targets MSME operators across four active verticals (Plan A): commercial printing, discrete manufacturing, metal fabrication, and field service. Chemical / process industry is reserved for Plan B (mid-market, ERP-connected customers) -- batch-first entry model differs from Plan A. The platform serves proprietors (Plan A, WhatsApp-first, no ERP) and managers/operators within each business.

## 2.2 Core Business Problems Addressed

- No centralised visibility of resource availability across overlapping job windows.

- Premium-skilled workers assigned to generic tasks, wasting capacity.

- Proprietors cannot quickly evaluate which jobs to accept based on resource availability and profit.

- Partial availability (machine downtime, employee leave) not accounted for in planning.

- No historical data for utilisation analysis or future capacity planning.

- Machine overbooking — multiple jobs on same machine with no conflict warning. **Fixed v3.7.1.**

- New users face blank screens with no direction. **Fixed v3.8 and v4.1.**

- Single-industry design limited addressable market. **Resolved v4.0 — 5 industry verticals.**

- AI responses used generic manufacturing terms regardless of industry. **Fixed v4.0.8.**

## 2.3 Solution Objectives

- Single-screen dashboard showing all jobs, resources, and availability status.

- Constraint-based scheduling with overbooking detection and named conflict messages.

- Profit maximisation by prioritising high-value jobs and recommending optimal resource assignments.

- Multi-industry support — one codebase, 5 industry verticals, configurable at registration.

- Industry-aware AI Copilot that uses correct terminology per tenant industry.

- Progressive product disclosure — V1 through V4 tiers controlled by feature flags.

- Guided onboarding — 8-step Getting Started checklist with auto-detection of completion.

# 3. Stakeholders & User Roles

| **Role** | **Description** | **Key Permissions** |
| --- | --- | --- |
| Super Admin (Platform) | Platform operator managing tenant provisioning and billing. | Create/suspend tenants, view platform-wide analytics, manage subscription plans. |
| Proprietor / Admin | MSME owner. Primary user of the application. | Full access: manage employees, machines, jobs, view reports, configure system. |
| Scheduler / Manager | Production manager delegated by proprietor. | Create/edit jobs, assign resources, view dashboards. Cannot manage billing. |
| Viewer | Read-only stakeholder (accountant, silent partner). | View jobs, reports, utilisation dashboards. No create/edit permissions. |

**v6.4 update -- Top-Tier Role Group. **Section 6.28 (v6.4 WhatsApp as Primary Entry Gate) expands the Proprietor / Admin tier into a role group of three roles with shared operational authority: Owner, Factory Manager, Co-Owner. All three have full operational rights (manage employees, machines, jobs, view reports, configure briefings, invite users). Commercial rights (billing, ownership transfer, tenant deletion) remain scoped to Owner only. Co-Owner has view-only commercial rights. This reflects real-world MSME structure where the operational head and the commercial head are often different people. Existing owner users remain role='owner' after migration -- no auto-promotion. See Section 6.28 for full details.

# 4. Multi-Industry Architecture (New in v4.0)

The v4.0 series introduced a configuration layer that allows ZetaOps Copilot to serve five industry verticals from a single codebase. Industry is selected at tenant registration and stored on the tenant record. All UI labels, AI terminology, demo data, colour themes, and onboarding steps adapt automatically.

## 4.1 Industry Verticals

| **Industry** | **Product Name** | **industry_type** | **Key Terminology** |
| --- | --- | --- | --- |
| Printing | PrintFlow Scheduler | printing | Jobs, Operators, Machines, Raw Materials |
| Manufacturing | ShopFloor Resource Planner | manufacturing | Production Orders, Operators, Work Centers, BOM Items |
| Fabrication | FabFlow Capacity Planner | fabrication | Work Orders, Fabricators, Work Centers, Materials |
| Chemical / Process (Plan B) | BatchFlow Process Scheduler (Plan B only) | chemical | Batch Orders, Operators, Reactors, Batch Inputs |
| Field Service | ServiceFlow Field Planner | field_service | Service Jobs, Technicians, Vehicles & Tools, Parts |

## 4.2 Industry Configuration Files

Each industry has a TypeScript configuration file at frontend/src/config/industries/{industry}.ts defining:

- **labels** — all UI strings: page titles, button labels, KPI names, nav items, form field names.

- **branding** — product name, short name, icon, tagline.

- **colours** — sidebar background, active state, primary button colour.

The IndustryContext provider reads the logged-in tenant's industry_type from /auth/me, loads the corresponding config, applies a theme-{industry} CSS class to <body>, and provides useLabels() and useIndustry() hooks to all components.

## 4.3 Industry-Aware Components (v4.0.3 — v4.0.8)

| **Component** | **Labels Applied** |
| --- | --- |
| Layout.tsx (sidebar) | Nav items: Jobs/Employees/Machines/Skills read from labels. ZeroZeta logo + 'ZetaOps Copilot' + industry product name subtitle. |
| Jobs.tsx | Page title, subtitle, New Job button, KPI cards, wizard steps, Raw Materials → labels.materials throughout. |
| Employees.tsx | Page title, subtitle, Add/Edit/Delete buttons, form titles, assignment rows, toasts. |
| Machines.tsx | Page title, subtitle, Add/Edit/Save buttons, table header, assignment rows. |
| Dashboard.tsx | KPI card labels, expanded job detail employee/machine labels, idle message, empty state description. |
| Skills.tsx | Page title, subtitle, loading/error/empty states. |
| GanttPage.tsx | Page title, tab labels (Jobs/Machines), column header. |
| Availability.tsx | Filter options (Employees/Machines Only), form tab labels, select placeholders. |
| CsvImport.tsx | Import modal title uses industry labels. Template download uses apiClient (not plain anchor — prevents 401). |
| AICopilot.tsx | Page suggestions use labels. Tools tab uses getAITools(labels) — all 50 prompts industry-aware. |

## 4.4 CSS Theme Engine (v4.0.7)

Full theme switching via CSS custom properties. index.css defines --brand-* variables per body.theme-{industry} class. Global button/link/badge overrides applied for all non-printing themes. IndustryContext applies body class on login.

| **Industry** | **Sidebar** | **Active State** | **Primary Colour** |
| --- | --- | --- | --- |
| Printing (default) | gray-900 #111827 | blue-600 #2563EB | Blue #2563EB |
| Manufacturing | slate-900 #0F172A | slate-600 #475569 | Slate #475569 |
| Fabrication | stone-900 #1C1917 | orange-600 #EA580C | Orange #EA580C |
| Chemical | green-950 #052E16 | green-600 #16A34A | Green #16A34A |
| Field Service | indigo-950 #1E1B4B | violet-600 #7C3AED | Purple #7C3AED |

# 5. Release Ladder & Feature Flag Architecture

## 5.1 Feature Flags

| **Flag** | **Default** | **Unlocks In** | **Feature** |
| --- | --- | --- | --- |
| `scheduler` | False | V2 | Auto-Scheduler + Scheduler Toolbar + Reschedule Needed badge |
| `gantt` | False | V2 | Production Timeline (Gantt Chart) nav item and page |
| `qr_scan` | False | V3 | QR Scan execution page + Print Job Card button in Jobs |
| `step_intelligence` | False | V3 | Step Intelligence panel inside job rows |
| `csv_import` | True | V4 | CSV / Excel Import button on Employees, Machines, Skills pages |
| `ai_copilot` | True | V4 | AI Copilot floating button, panel, Tools tab, page suggestions |
| whatsapp_copilot | True | V5 | WhatsApp Copilot channel, phone linking, intent confirmation, proactive alerts, voice notes |
| kpi_baseline | True | V6 | Daily tenant_kpi_snapshot capture + monthly savings summary to owner phone. Shipped in v6.3. |
| whatsapp_entry_gate | True | V6 | Master switch for v6.4 WhatsApp entry gate behaviour: signup-time entry_mode question, post-signup QR screen, PhoneTenantMap pre-creation, top-tier role group (Owner / Factory Manager / Co-Owner), and configurable daily push briefings. When False: signup behaves as v6.3.0 (no team-size question, no QR step, no role expansion, no briefings). Shipped in v6.4. |
| material_estimator_freemium | False | V6 | When True: first 10 material queries per month free for free-tier tenants. Shipped in v6.5 (renumbered from v6.4 after April 28, 2026 strategy revision). |
| compliance_tracker | False | V6 | Tenant-specific compliance item seeding, reminder scheduler, and document upload. Shipped in v6.6 (renumbered from v6.5). |
| einvoice_generator | False | V6 | Generate GSTN-compliant JSON from completed job data. No portal submission. Shipped in v6.7 (renumbered from v6.6). |

> **NOTE** As of v4.0.9 all flags are True by default in features_config.py. The flag system remains for per-tenant control in v5.

## 5.2 Product Tiers

| **Tier** | **Flags Enabled** | **User Value** |
| --- | --- | --- |
| V1 — Job Board | All False | Replace paper register. Jobs CRUD, employees, machines, manual assignment, dashboard. |
| V2 — The Planner | scheduler, gantt | Stop missing deadlines. Auto-schedule, production timeline, unavailability blocking. |
| V3 — Shop Floor | qr_scan, step_intelligence | Workers know what to do. QR scan, step tracking, print job cards. |
| V4 — Full Platform | csv_import, ai_copilot | Power user. Bulk import, industry-aware AI Copilot, 50 pre-built tools, full reporting. |

# 6. Functional Requirements

## 6.1 Tenant & Organisation Management

- Two-step registration: Step 1 selects industry vertical (5 options with icons and descriptions). Step 2 collects organisation name, email, password, slug.

- industry_type stored on Tenant record (DB column, migration 016). Default: 'printing'.

- Demo data auto-seeded on registration — industry-specific jobs, employees, machines, skills, steps and assignments. Idempotent. Never breaks registration.

- AI query limits tracked per tenant per day (Free: 50/day, Pro: 500/day, Enterprise: unlimited).

- Tenant settings: working hours per day, working days per week, currency, fiscal year start month.

## 6.2 Employee / Operator Master Data

Field names in UI adapt to industry (Employees/Operators/Technicians/Fabricators). All backend fields remain generic.

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| Full Name | Text | First and last name. |
| Department | Select | Production department or cost centre. |
| Employment Type | Select | Full-time / Part-time / Contract. |
| Base Availability % | Number 0-100 | Default availability across all working days. |
| Skills | Multi-select | One or more skills from the global skill catalogue. |
| Skill Level per Skill | Select per skill | Generic / Intermediate / Premium. |
| Hourly Rate (INR) | Number | Used for cost calculation per job. |
| Overtime Rate (INR) | Number | Rate for hours beyond standard shift. |
| Join Date | Date | Used for seniority and compliance. |
| Status | Toggle | Active / Inactive / On Leave. |

- Availability overrides: day-specific availability blocks auto-scheduler occupancy map.

- Bulk import via CSV and Excel (.xlsx) — leave columns included in template.

- Import modal title uses industry label (Import Operators, Import Technicians, etc.).

- CSV template download uses authenticated apiClient — not plain anchor tag (prevents 401).

## 6.3 Machine / Reactor / Work Center Master Data

Field names adapt to industry. Backend fields remain generic.

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| Machine Name | Text | Descriptive name (e.g. Reactor R-101, CNC Lathe #1). |
| Machine Type | Select | From configurable type catalogue. |
| Base Availability % | Number 0-100 | Default operational availability. |
| Required Skills | Multi-select | Skills an operator must possess to use this machine. |
| Min Skill Level Required | Select per skill | Generic / Intermediate / Premium. |
| Employees Required per Skill | Number | How many workers with each skill must be present. |
| Location / Bay | Text | Physical location on the shop floor or depot. |
| Hourly Rate (INR) | Number | Used for cost calculation per job. |
| Status | Toggle | Operational / Under Maintenance / Decommissioned. |

## 6.4 Skill / Qualification / Certification Catalogue

- Global skill catalogue per tenant. Skills reused across employees and machine requirements.

- Page title adapts to industry: Skills Catalogue / Qualifications Catalogue / Certifications Catalogue.

- Skills Catalogue subtitle shows industry labels: 'Master list of qualifications used by operators, reactors and batch orders.'

## 6.5 Job Definition & Management

Job entity fields remain generic in backend. UI labels adapt per industry (Jobs/Batch Orders/Production Orders/Service Jobs).

| **Field** | **Type** | **Description** |
| --- | --- | --- |
| Job Name | Text | Descriptive job title. |
| Customer / Client | Text | Associated customer name. |
| job_type | String (new v3.9.6) | Type of job — used for material estimate grouping. |
| Quantity | Float (new v3.9.6) | Quantity of units — used for material estimate scaling. |
| Start / End Date | Date | Proposed or confirmed job dates. |
| Estimated Hours per Day | Number | Daily working hours required. |
| Order Value (INR) | Number | Total billable value. |
| Raw Materials | JSON table | Name, quantity, unit, unit cost per material line. |
| Priority | Select | Low / Medium / High / Critical. |
| Status | Select | Draft / Pending Assignment / Scheduled / In Progress / Completed / Cancelled. |
| Start Mode | Select | Right Away / Pick a Date / Flexible. |
| Is Locked | Toggle | Locked jobs are fixed anchors — auto-scheduler works around them. |
| Invoice Number | Text | Invoice reference for completed jobs. |
| Payment Status | Select | Unpaid / Partial / Paid. |

## 6.6 Step Intelligence

- Gated behind step_intelligence feature flag. Enabled in V3 tier.

- Jobs broken into ordered steps: Setup, Production, Inspection.

- Steps unlock sequentially — completing one step automatically unlocks the next.

- Per-step resource overrides — a step can use different employees/machines than the job level.

- Step count visible in job row. Add/delete steps invalidates both steps and jobs query cache.

## 6.7 QR Scan & Print Job Cards

- Gated behind qr_scan feature flag. Enabled in V3 tier.

- Each step generates a JWT-based scan token (start + complete) with expiry.

- Scan page is auth-free (token-based) — designed for shop floor devices without login.

- Scan endpoint: POST /api/scan/execute — no auth, token-based.

## 6.8 Resource Availability Engine

- Machine Check: For each required machine, verify availability > 0% and not already allocated.

- Employee Skill Match: Identify employees with required skill level and availability > 0%.

- Employee Capacity Check: Confirm employees not already committed on any date in range.

- Conflict Report: Detailed named conflict message with specific dates and resource names.

- Feasibility Score: 0-100% representing proportion of requirements that can be fulfilled.

- Overbooking Check: Before saving assignment, queries existing assignments for date overlap.

## 6.9 Schedule Suggestions (v3.9.7)

- GET /api/jobs/{job_id}/schedule-suggestions — scans 30 days, scores by resource availability + deadline.

- Returns ranked date slots with feasibility scores.

- AI Copilot uses this endpoint to answer scheduling questions about specific jobs.

## 6.10 Material Estimate (v3.9.8)

- GET /api/jobs/{job_id}/material-estimate — finds completed jobs of same job_type.

- Calculates average material cost per unit, scales to current job quantity.

- AI Copilot uses this endpoint to answer material requirement questions.

## 6.11 Auto-Scheduler Engine

- Gated behind scheduler flag. Enabled in V2 tier.

- Greedy forward-scan — finds earliest gap where all assigned resources are free.

- Locked jobs are fixed anchors — scheduler never moves them.

- Jobs ranked: Critical > High > Medium > Low, then by order value descending.

- Employee leaves and machine downtimes block occupancy map same as locked jobs.

- Only reschedules jobs that have resources assigned.

## 6.12 Dashboard & Visualisation

- Live KPI cards: Active Jobs/Batch Orders/Production Orders (label from industry), Available Machines, Available Employees.

- Smart Alerts: conflicts, overdue jobs, idle floor, critical jobs not started, ending soon.

- Timer controls per job: Start, Pause, Resume, End. Tracks actual hours.

- Auto-polls every 30 seconds for conflict resolution detection.

- Job card expand (▼ button): fetches full job detail via GET /api/jobs/{id} to show assigned employees and machines. Falls back gracefully if missing.

- Dashboard subtitle, idle message, empty state description all use industry labels.

## 6.13 AI Copilot (v3.9 + v4.0.8 + v5.x)

- Gated behind ai_copilot flag. Enabled in V4 tier.

- Powered by Groq API — tool-calling architecture with 16 DB tools.

- LLM narrates real data — never computes business logic. All calculations in Python.

- Industry-aware system prompt (v4.0.8): injects correct terminology per tenant industry_type.

- All 50 pre-built tool prompts in Tools tab use getAITools(labels) — industry labels applied.

- Page-context aware: suggestions change based on current page and industry.

- Handles English and Hinglish naturally.

- Pre-fetches structured data from schedule-suggestions and material-estimate endpoints before AI call.

- Per-tenant daily query limits tracked. Warning at 90% usage.

- WhatsApp Copilot channel (v5.x): same tool-calling pipeline delivered over WhatsApp. User links phone number via LinkWhatsApp.tsx. Backend maintains session state via Upstash Redis. Mock mode (WHATSAPP_MOCK_MODE=True) enables dev/test without real Meta API. Router self-prefixes at /api/v1/whatsapp, registered in main.py with no prefix.

- Intent detection + confirmation flow (v5.6): write-operations (scheduling, assignment) require explicit user confirmation before DB commit. Read-only queries execute immediately. Sync SQLAlchemy Session used throughout WhatsApp services (never AsyncSession).

- Proactive alerts (v5.10): trigger endpoint fires morning briefing, conflict alert, and job-ending-soon messages to linked WhatsApp number without user query. Code exists, testing in progress. Gated behind whatsapp_copilot feature flag.

- Voice notes (v5.11): Whisper transcription converts voice messages to text before entering the existing AI pipeline. No pipeline changes required beyond transcription step.

- Schema context layer (v5.x): AI system prompt prefixed with a static entity-relationship map (app/knowledge_graph/schema_context.py) on every query. Resolves multi-hop reasoning failures without a graph database. See Section 17 for architecture decision and rationale.

## 6.14 Demo Data Seeder (v4.0.6)

- Auto-seeded on registration for every new tenant.

- 5 industry-specific seeders: printing, manufacturing, fabrication, chemical, field_service.

- Each seeder creates: 5 skills, 6 employees with skill assignments, 3 machines with skill requirements, 3 jobs with steps, raw materials, and assignments.

- Idempotent — skips existing records. Never breaks registration (try/except wrapper).

- Located at: backend/app/services/demo_seeder.py.

## 6.15 Getting Started Onboarding (v4.1)

- 8-step logical onboarding flow replacing the previous 5-step checklist.

- Steps: Add Skills → Add Employees → Add Machines → Create first Job → Assign resources → Run Auto-Schedule → Check Dashboard → Try AI Copilot.

- Auto-detects completion via TanStack Query cache for steps 1-4 and 6.

- Manual steps (5, 7, 8) marked done via localStorage on Go → button click.

- Industry-aware labels — shows 'Add Operators', 'Create first Batch Order' etc.

- Progress bar, collapse/dismiss/restart. Auto-dismisses when all 8 steps complete.

- Positioned bottom-left (z-20) so it does not block header toolbar or AI Copilot button.

- ? button in header resets tour at any time.

## 6.16 CSV / Excel Import

- Gated behind csv_import flag. Enabled in V4 tier.

- Employees, machines, and skills bulk import via .csv or .xlsx files.

- Template download uses authenticated apiClient — not plain anchor tag (prevents 401 error).

- Import modal title uses industry label (Import Operators, Import Reactors, etc.).

- Styled Excel templates downloadable from the UI.

- Single CsvImport component at frontend/src/components/common/CsvImport.tsx. Old duplicate at components/CsvImport.tsx removed.

## 6.17 WhatsApp Copilot -- Role Limiting (v5.12)

Three distinct WhatsApp roles constrain what each phone number can do.

owner -- full access: read schedule, approve actions, receive briefings.

manager -- operational access: attendance, machine status, job updates. Blocked from financial and tenant-level actions.

viewer -- read-only: status queries only, no write operations.

Role check runs in detect_write_intent() BEFORE the AI layer is called. Blocked actions never reach Groq API. Enforcement is structural, not prompt-based.

## 6.18 WhatsApp Copilot -- 3-Language Support (v5.12)

Every inbound WhatsApp message is classified once: detect_language(text) returns hindi | hinglish | en. The classification drives the LANGUAGE_INSTRUCTION injected into _build_system_prompt(). AI responds in the detected language throughout the conversation session.

Hindi -- Devanagari script detected (Unicode range).

Hinglish -- Latin-script marker words (aaj, kaam, nahi, theek) detected.

English -- default when neither Hindi nor Hinglish markers found.

## 6.19 Day 1 Simple Table (v5.16)

The first screen a new tenant sees after registration -- before the Gantt chart, before jobs. Designed for a proprietor with zero ERP and zero patience.

Input: worker name + primary skill (one word: welder, stitching, cutting, finishing) + worker type (permanent | contractor).

Input: machine name + machine type.

Nothing else -- no hourly rates, no availability percentages, no shift timings on Day 1.

Onboarding question: "Do you have employee/job data in SAP, Tally, or Excel?" Yes -> ERP path placeholder (v7.0). No -> proceed with this table.

Migration 023 adds source (VARCHAR 20, server_default=manual) to employees and machines, and worker_type (VARCHAR 20, server_default=permanent) to employees. These fields cost one column now. Removing them forces a full rewrite at v7.0.

## 6.20 Manager Check-in Flow (v5.15)

APScheduler triggers a WhatsApp message to the manager phone at 7:00am. The manager replies naturally; the system parses names against the Day 1 seed table.

"Aaj kaun kaun aaya?" -- manager lists present workers. Absent workers identified by diff against seed table.

Absent worker -> skill looked up -> substitute suggested immediately from available pool.

"Machines theek hain?" -- manager flags downtime. Writes to machine_downtimes table.

"Aaj ke main kaam kya hain?" -- manager states work. Maps to skill requirements.

All inputs write to the availability engine. Conversation ends: "Got it. Sahab ko summary bhej raha hoon."

## 6.21 Owner Briefing (v5.15)

At 7:15am a single clean briefing is generated FROM the manager inputs, not from scheduled data alone. Format: who is present, who is absent, skill gap, order at risk, one suggested action. No questions to owner -- signal only, zero input required from owner phone.

After one week of daily check-ins: real attendance patterns, skill usage, and machine reliability are all in the system passively.

## 6.22 RAG Pipeline (v6.1)

Industry-aware knowledge injected into every AI query via a flat-file Retrieval-Augmented Generation pipeline.

Folder: backend/rag_data/_templates/{industry}/ -- default knowledge per industry (4 verticals: printing, manufacturing, fabrication, field_service). Chemical excluded -- batch-first model differs.

Tenant override: backend/rag_data/{tenant_id}/ -- tenant-specific knowledge seeded at registration from the industry template.

_build_system_prompt() injects tenant RAG context before every AI query.

RAG data is tenant-isolated -- never read from another tenant folder.

Migration path: flat files (v6.1) -> pgvector (v6.3). Folder structure unchanged across migration.

## 6.23 Industry-Aware Dynamic Labels (v6.2)

All user-visible entity labels are driven by industry_type, never hardcoded.

IndustryContext.tsx reads industry_type from AuthContext at login.

useLabels() hook returns labels.jobs, labels.employees, labels.machines per industry.

Sidebar and page titles use useLabels() -- zero hardcoded "Jobs", "Employees", "Machines" strings in src/pages/ or src/components/.

Example: printing tenant sees "Print Jobs" / "Press Operators" / "Presses". Fabrication tenant sees "Fabrication Orders" / "Fitters" / "CNC Machines".

Verification: grep -r '"Jobs"\|"Machines"\|"Employees"' frontend/src/pages/ must return empty.

## 6.24 KPI Baseline and Monthly Savings Summary (v6.3)

Captures operational KPIs passively during the first week of every tenant lifecycle (the baseline), then reports monthly savings to the owner via WhatsApp. Proves ongoing ROI. Prevents churn from owners forgetting why they pay for ZetaOps.

New table tenant_kpi_snapshot (planned — migration number assigned at ship time): one row per tenant per day with operational metrics. is_baseline boolean flag distinguishes the first 7 days from subsequent measurement.

Baseline window: first 7 calendar days after tenant registration. Rows tagged is_baseline=True.

Capture service: backend/app/services/kpi_capture.py hooks into existing scheduler, whatsapp_alerts, and assignments endpoints. APScheduler job at 23:59 writes daily snapshot. No new user data collection.

Monthly summary: APScheduler job at 09:00 on the 1st of each month. Compares last 30 days vs baseline. 3-line WhatsApp message to owner in detected language: rupees saved, hours saved, one concrete highlight.

On-demand query: owner can ask "kitna save hua is month?" via WhatsApp; system returns live month-to-date summary.

Data retention: 13 months rolling. Aggregation tables for longer history.

Acceptance criteria: first 7 days produce baseline rows; Day 8 onwards tagged non-baseline; first monthly summary between Day 31 and Day 37; summary suppressed if fewer than 7 baseline days exist; tentative label on summaries with less than 30 days of post-baseline data. tenant_id isolation on every query.

## 6.25 Material Estimator as First-Class WhatsApp Surface (v6.5; was v6.4 prior to April 28, 2026 strategy revision)

Exposes existing material estimation capability (backend endpoint shipped in v3.9.8, RAG grounding shipped in v6.1) as a standalone WhatsApp entry point. Example query: "5000 brochures ke liye kitna paper chahiye" returns a grounded, industry-calibrated answer without requiring the user to create a job or understand the scheduler.

New WhatsApp intent: material_query. Detected in whatsapp_intent.py. Read-only -- bypasses confirmation flow.

Keyword triggers loaded from rag_data/_templates/{industry}/materials.txt per vertical. Printing: paper, ink, plates, binding, lamination. Manufacturing: steel, aluminum, threads, fasteners, coolant. Fabrication: MS plate, pipes, rods, welding rods, gas. Field service: spares, consumables, PPE, tools.

Reuses existing endpoint GET /api/jobs/{job_id}/material-estimate. Estimation math always in backend. AI only narrates -- never computes.

Response format (3 lines): quantity needed, estimated cost, confidence level. High = 3+ historical jobs. Medium = 1-2 historical or RAG-based. Low = pure inference.

Works for all three phone roles (owner, manager, operator) -- material estimation is operational, not financial.

Feature flag material_estimator_freemium (default False). When True: free-tier tenants get 10 queries per month free. Acquisition wedge.

Response cached per tenant per material for 24 hours. Target latency 4 seconds end-to-end.

Acceptance criteria: printing-industry query returns paper quantity, rupee estimate, and confidence level. Query on a fabrication tenant with printing-specific material returns a clarification or redirect. Query missing quantity returns clarifying question. Historical lookups use tenant-own jobs only, never cross-tenant data.

## 6.26 Compliance Deadline Tracker (v6.6; was v6.5 prior to April 28, 2026 strategy revision)

Tracks statutory and regulatory deadlines per tenant. Sends WhatsApp reminders at T-30, T-7, and T-1 days before each deadline. Accepts document upload via WhatsApp reply to mark compliance. Standalone-valuable -- delivers value even to tenants who do not use the scheduler. Pulled forward from v7.1 after IDC analysis identified compliance as the highest-ROI addition for MSMEs.

Scope (India, MSME-focused):

Statutory filings: GSTR-3B (20th monthly), GSTR-1 (quarterly), ESI (15th monthly), PF (15th monthly), TDS (quarterly), Professional Tax (state-varies).

Licenses: Factory License renewal, Pollution Control Board Consent to Operate, Fire Safety NOC, Trade License, MSME Udyam certificate.

Industry-specific items loaded from rag_data/_templates/{industry}/compliance.yaml per vertical.

Implementation:

A future migration (number assigned at ship time) will create three tables: compliance_item (tenant_id, item_type, item_name, renewal_frequency, last_filed_date, next_due_date, status, industry_default), compliance_document (compliance_item_id, tenant_id, filename, mime_type, uploaded_at, file_path, uploader_user_id), compliance_reminder_log (compliance_item_id, reminder_day, sent_at, channel).

Seeding at tenant registration: industry-appropriate items created. Owner can deactivate items that do not apply.

APScheduler daily at 08:00: compliance_reminder_job. Fires reminders at T-30, T-7, T-1 days. Idempotent via reminder_log check.

Document upload via WhatsApp reply: PDF, JPG, PNG up to 10 MB. Advances next_due_date by renewal_frequency. Confirms via WhatsApp.

Dashboard widget: Upcoming Deadlines card showing next 3 items with countdown.

Tenant-isolated storage. 5-year document retention (statutory audit window).

Out of scope for v6.5: e-invoice JSON generation (deferred to v6.6), submission to GSTN or any government portal (ZetaOps reminds, does not file), legal or tax advice.

Pricing implication: standalone-valuable. Consider unbundled tier at Rs 499/month or bundled with ZetaOps Core.

## 6.27 GST E-Invoicing JSON Generation (v6.7; was v6.6 prior to April 28, 2026 strategy revision)

Converts completed job data into GSTN-compliant e-invoice JSON. Sends to owner via WhatsApp and email for submission by the owner CA or accountant. ZetaOps does not submit to GSTN directly.

Service: backend/app/services/einvoice_generator.py. Produces JSON conforming to GSTN schema v1.1.

Endpoint: POST /api/einvoice/generate/{job_id}.

A future migration (number assigned at ship time) will add a gstin column (VARCHAR 15, nullable) to customers.

WhatsApp trigger: when manager marks job complete, system asks owner for customer GSTIN; on reply, generates JSON and sends to owner email plus WhatsApp.

compliance_item for e-invoicing auto-created when tenant turnover crosses threshold (Rs 5 crore as of 2026, decreasing annually).

Feature flag einvoice_generator (default False).

Out of scope: managing tenant GSTN credentials or API keys, reconciliation with bank statements, direct portal submission.

## 6.28 WhatsApp as Primary Entry Gate (v6.4)

Promotes WhatsApp from "one of several surfaces" to a formally configurable entry gate for new tenants, expands the top-tier role from a single Owner into a role group covering Owner / Factory Manager / Co-Owner with equal operational authority, and introduces configurable morning + evening daily push briefings on WhatsApp to top-tier users. Builds directly on v6.3.0-whatsapp-industry tenant-isolation foundation. Section 6.28 is the v6.4 release scope.

**Strategic intent.** WhatsApp is already a capable surface (v5.0-v5.16: pipeline, intents, confirmations, multilingual, role gating, voice transcription mock, Day 1 onboarding, manager check-in, proactive alerts via trigger endpoint). What is missing is the positioning -- telling the system "this tenant lives on WhatsApp by default, with these top-tier people authorised, getting these scheduled briefings." v6.4 establishes that primitive. Subsequent releases (Material Estimator surface in v6.5, Compliance Tracker in v6.6, etc.) become features on top of the named entry gate.

**Three bundled features.** v6.4 ships entry-mode routing, top-tier role expansion, and daily push briefings together. Bundling is justified because they are operationally coherent -- they describe how a small or medium business actually uses the product day-to-day on WhatsApp. None of the three is independently shippable as a coherent product story.

**Feature 1 -- Entry Mode Configuration.**

New columns on Tenant table: entry_mode (enum: whatsapp_first / desktop_first / hybrid, default desktop_first) and size_segment (enum: small / medium / large, nullable). Two new fields on the existing signup form: team size (radio: 1-15 / 16-50 / 51+) and phone number (E.164 format, required for whatsapp_first and hybrid). Team size drives entry_mode default. Email and password become optional for whatsapp_first signups; phone plus WhatsApp connection serves as identity. All other existing signup fields (business name, GST, address, industry_type, T&C, billing) remain unchanged.

Post-signup routing branches on entry_mode: desktop_first lands on existing dashboard (no change from current behaviour). whatsapp_first shows a Connect WhatsApp screen with QR code (with skip option), then a minimal landing page emphasising WhatsApp as home base. hybrid shows the QR screen and then the regular dashboard with a banner indicating both surfaces are available.

PhoneTenantMap pre-creation: when a tenant signs up with entry_mode != desktop_first and provides a phone number, immediately create a PhoneTenantMap row for the proprietor with status=invited and industry_type read from the new tenant via the v6.3.0-whatsapp-industry fix. Status flips to active on first WhatsApp interaction or YES reply to welcome message. For desktop_first signups, no row is created. This means: when the proprietor first messages the WhatsApp Business number, the system already knows who they are, which tenant they belong to, and which industry vocabulary to use. There is no "first-message identification" delay.

Settings page additions: change entry_mode after signup, change size_segment, connect or disconnect WhatsApp, set desktop password later for users who skipped at signup. Migration of existing tenants: default to desktop_first, no behaviour change.

**Feature 2 -- Top-Tier Role Group.**

The existing single owner role expands into a role group of three roles with shared operational authority. Owner has full operational and full commercial rights (billing, ownership transfer, tenant deletion). Factory Manager has full operational rights but no commercial rights. Co-Owner has full operational rights and view-only commercial rights (can see billing history, cannot change payment method).

Operational rights = create/edit/cancel work orders, manage crew, run auto-schedule, view financials and reports, configure entry_mode, configure briefings, invite users at lower tiers. Commercial rights = scoped to Owner only.

Implementation: User.role enum extends to {owner, factory_manager, co_owner, manager, operator}. New computed property User.is_top_tier returns True for owner, factory_manager, co_owner. Existing permission checks gated on "is owner-equivalent" switch to is_top_tier. The handful of commercial-only checks remain gated on role == 'owner'. The phone_role enum on PhoneTenantMap (migration 018) extends similarly. Existing 199 tests must continue to pass.

Cap: unlimited top-tier users per tenant. Small shops will naturally have one or two; large factories may have five or six (one Owner, multiple shift Factory Managers, perhaps a Co-Owner partner). Last-owner protection: cannot demote self if it would leave zero owners; system requires at least one owner per tenant.

Settings: Team and Roles section allows Owner to invite, promote, or demote users within and across tiers. Factory Manager and Co-Owner can invite or promote/demote within lower tiers (manager, operator) but cannot promote anyone to top-tier and cannot demote Owner.

**Feature 3 -- Daily Push Briefings.**

Two configurable scheduled WhatsApp briefings per day, sent to all top-tier users with active WhatsApp connection. Morning briefing is forward-looking (today's plan); evening briefing is backward-looking (today's actuals). Reuses v5.10 trigger-endpoint logic for content generation; v6.4 adds the scheduler, configuration, evening template, and recipient fan-out.

Morning briefing (default 7:30am tenant local time): today's date and weekday, jobs scheduled to start, jobs continuing from yesterday, crew expected, blockers requiring attention before start, one actionable next step. Evening briefing (default 6:30pm): jobs completed today, jobs paused or stopped early with reason, hours logged, attendance summary, blockers raised today, one suggested action for tomorrow. Both target 6-10 lines and fit a single WhatsApp screen without scrolling.

Configuration on Tenant: briefing_morning_enabled, briefing_morning_time, briefing_evening_enabled, briefing_evening_time, briefing_timezone (default Asia/Kolkata), briefing_working_days (ISO weekday string, default "1,2,3,4,5,6" for Mon-Sat). All briefings are opt-in -- new tenants and existing tenants default to disabled. Per-user overrides on User: briefing_time_override_morning, briefing_time_override_evening, briefing_subscribed.

Recipients: users where is_top_tier == True AND briefing_subscribed == True AND linked PhoneTenantMap.status == active. If no recipients qualify, the briefing job logs and skips silently (no error). Working-days pattern is checked: on excluded days, briefing is skipped with reason non_working_day logged.

Idle-floor handling: when there are no jobs to summarise, send an idle template ("Good morning! No active jobs scheduled today -- floor is idle." for morning; "Today was quiet -- no jobs ran." for evening) rather than silence. Idle messages still count as delivered for audit purposes.

Dispatch: APScheduler job runs every 5 minutes. For each tenant with briefings enabled, computes whether the configured local time falls within the next 5-minute window and the day is a working day. If yes, generates content using shared logic, identifies recipients, sends via WhatsApp API with stagger by tenant_id hash to spread send load across the briefing window. Each send logged to events with event_type briefing.sent. Failed sends retried up to 3 times with backoff before logging briefing.send_failed.

Manual trigger: top-tier users can request an on-demand briefing via WhatsApp ("morning briefing", "today's plan", "evening briefing", "today's summary"). Reuses the same content generation, dispatched only to the requester. Logged with event_type briefing.manual_trigger. Does not affect the scheduled send.

Industry awareness: briefing content uses tenant industry_type vocabulary (fabrication: fabricators, work centres; printing: operators, presses; manufacturing: operators, work centres; field service: technicians, vehicles). v4.0 IndustryContext mechanism on the backend supplies the labels. Cross-vertical hygiene: no fabrication-specific or printing-specific strings in the dispatcher itself.

**Migration.**

Migration 027 (single migration, idempotent backfill following v6.3.0-whatsapp-industry pattern): adds entry_mode (enum, NOT NULL, default 'desktop_first') and size_segment (enum, nullable) to tenants. Adds briefing_morning_enabled, briefing_morning_time, briefing_evening_enabled, briefing_evening_time, briefing_timezone, briefing_working_days to tenants with safe defaults. Adds briefing_time_override_morning, briefing_time_override_evening, briefing_subscribed (default true), phone_e164 (indexed, nullable) to users. Adds created_via (enum, default 'desktop_signup') to tenants and users. Extends User.role enum with factory_manager and co_owner. Extends phone_tenant_map.phone_role enum similarly.

Backfill script scripts/backfill_v6_4.py is idempotent. Existing tenants get entry_mode='desktop_first', briefings disabled, created_via='desktop_signup'. Existing owner users remain role='owner' -- no auto-promotion. Second run reports zero rows updated. Pattern same as scripts/backfill_phone_industry_type.py from v6.3.0-whatsapp-industry.

**Acceptance criteria.**

(1) whatsapp_first signup creates Tenant, User, and PhoneTenantMap rows in one transaction with industry_type correctly attributed (regression for BUG-6). (2) desktop_first signup creates Tenant and User but does not create PhoneTenantMap. (3) hybrid signup creates all three with the same industry attribution. (4) whatsapp_first signup without phone returns 400 with clear error; without password succeeds. (5) desktop_first signup without password returns 400. (6) Owner can invite, promote, demote within top-tier; Factory Manager and Co-Owner cannot; last-owner protection prevents zero-owner state. (7) Briefing dispatcher fires at configured time on working days; idle template used when no jobs; non-working day skipped with logged reason; no recipients = silent skip not error. (8) Per-user time override delivered correctly. (9) Manual trigger ("morning briefing" via WhatsApp) returns content immediately to requester only. (10) Migration runs cleanly on copy of production data; existing tenants emerge with entry_mode='desktop_first' and unchanged behaviour. (11) Backfill script idempotent. (12) Existing v6.3.0-whatsapp-industry test (BUG-6 regression) extended to cover signup-time creation of PhoneTenantMap and briefing dispatch industry vocabulary. (13) Cross-vertical hygiene: no industry-specific strings in entry-gate or briefing-dispatcher modules.

**Assumptions.**

WhatsApp Business API account is provisioned (production via Interakt) or v5.0 mock simulator is available -- v6.4 ships against whichever is active. Mock-vs-production distinction is orthogonal to entry-gate routing. Webhook receiver is reachable; outbound messages can be sent within seconds of trigger. Background scheduler (APScheduler) is operational. v6.3.0-whatsapp-industry isolation is correct and stable. Phone number is acceptable as primary identity for whatsapp_first tenants. Team-size buckets reasonably segment customers. Indian customers prefer Hindi or Hinglish messaging by default (v5.12 multilingual support). Existing tenants will not opt in to WhatsApp en masse during release window. Tenant local timezone is known or derivable (default Asia/Kolkata).

**Out of scope (deferred).**

Desktop UI redesign (KPI pills, alert bell, sidebar consolidation) -- deferred to a later release. Role-based desktop views -- deferred. Magic-link or OTP authentication -- deferred to v7.x. WhatsApp-native registration without desktop touch -- deferred. Mobile app -- deferred. Holiday calendar (only working-days pattern in v6.4) -- deferred. Per-user briefing customisation beyond time override -- deferred. Briefings to non-top-tier roles -- deferred. Briefings on channels other than WhatsApp -- deferred. Shift-aware briefings for 24-hour factories -- deferred.

**Risks.**

WhatsApp Business API approval delay (Meta/Interakt review): ship against mock if production blocked. Routing logic is independent of mock-vs-production. Migration on large tenant tables: use Alembic safe-add patterns to avoid locking. Phone-as-identity recovery: whatsapp_first user without password who loses WhatsApp access requires support intervention; v6.4 documents this in Settings, magic-link recovery deferred. Briefing fan-out at scale: 1000 tenants times 3 top-tier users at 7:30am = 3000 sends in seconds; mitigated by tenant_id hash stagger across the briefing window. Briefing fatigue: if briefings are noisy, users will mute or unsubscribe; mitigated by high-signal content and sparse idle messages. Role confusion: introducing factory_manager and co_owner alongside owner may confuse users expecting a single boss; mitigated by sensible defaults (most small shops will only use owner) and clear Settings copy.

## 6.28.4 UI Consolidation (v6.3.5 -- documented in SRS v6.5)

Reflects the iteration scope of v6.3.5, the iteration that delivers the user-facing surface for the v6.4 entry-gate strategy. Section 6.28.4 is documentation-only; it specifies UI-layer changes and a small backend schema refinement (TeamMemberOut.email becomes Optional[str]). No new database migration; no new feature flag (the existing whatsapp_entry_gate flag from v6.4 covers everything described here).

**Strategic intent. **v6.4 established the entry-gate as a configurable property on Tenant. v6.3.5 makes it visible. Today the proprietor sees a sidebar with a "WhatsApp" item that opens a standalone "Link a number" page; the Team and Roles page in Settings exposes a separate "Invite member" button; synthesised emails like +invite-1e9e6f8e@invite.zetaops.com leak into the Team and Roles table when WhatsApp-only members appear. These three artefacts predate the v6.4 strategy and now read as inconsistent with it. v6.3.5 collapses them: one Invite modal handles both desktop email invites and WhatsApp phone invites; the Team and Roles table is redesigned around phone as identity; whatsapp_first proprietors land on a minimal post-signup page that frames WhatsApp as the home base; the standalone /whatsapp page is removed.

**Change 1 -- Drop /whatsapp as a top-level route and sidebar item.**

The standalone LinkWhatsApp page (frontend/src/pages/LinkWhatsApp.tsx) and the transitional ConnectWhatsApp placeholder (frontend/src/pages/ConnectWhatsApp.tsx, introduced in v6.3.2 as a stub) are deleted. The "WhatsApp" sidebar item in frontend/src/components/Layout.tsx is removed. The /whatsapp and /connect-whatsapp routes are unregistered from frontend/src/App.tsx; direct visits return 404. The post-signup destination for whatsapp_first and hybrid tenants becomes the new minimal landing page at /welcome (Change 4 below) rather than /connect-whatsapp.

The backend WhatsApp router at /api/v1/whatsapp continues to serve the simulate, linked-phones, and webhook surfaces used by tests and scripts -- only the user-facing standalone page is removed. Backend client-only wrappers in frontend/src/api/api_endpoints.ts that are referenced solely by the deleted pages (linkPhone, linkedPhones, deactivatePhone) are audited and removed; ones still used by tests or other surfaces are kept.

**Change 2 -- Redesign Team and Roles as a phone-shaped table.**

The redesigned table at frontend/src/pages/settings/TeamAndRoles.tsx has five columns: Person, Phone, WhatsApp, Role, Actions. Person renders display name first, falling back to "(unnamed)" when no name is set, and never surfaces synthesised invite-XXX@invite.zetaops.com or *@whatsapp.local email strings -- those were placeholders for the schema, never real, and the previous UI exposed them as if they were the user's real email. Phone is its own first-class column with monospace formatting; for whatsapp_first tenants this is the canonical identity column. WhatsApp is a status column showing one of four states: "Active" (green dot), "Invited" (amber dot, with "X days ago" relative timestamp), "Disconnected" (red dot), "Not connected" (grey dot). Role uses the existing badge styling with the TOP-TIER tag for Owner / Factory Manager / Co-Owner. Actions provides per-row edit, resend invite, and remove buttons gated by the v6.3.3 role matrix.

Backend support: TeamMemberOut.email becomes Optional[str]; a server-side _synthesise_email_for_response helper in app/services/team_service.py returns None whenever the database holds a synthesised placeholder (matching '+invite-*@invite.zetaops.com' or '*@whatsapp.local'), so the placeholder never leaves the API boundary. TeamMemberOut gains a whatsapp_status field of Literal['active','invited','disconnected','none']. The PhoneTenantMap join is performed in a single SELECT (N+1 forbidden per Section 8.4 caching rules). Frontend introduces a TeamMemberView adapter type that derives a non-nullable displayEmail (empty string when email is null) so render code never has to null-check.

**Change 3 -- Single Invite modal as the only entry point for adding teammates.**

A new InviteMemberModal component at frontend/src/components/InviteMemberModal.tsx replaces both the v6.3.3-era inline invite form on Team and Roles AND the deleted standalone /whatsapp page. The modal opens from the "Invite member" button in the top-right of Team and Roles. It collects: channel (WhatsApp recommended / Desktop only, radio); phone or email (rendered conditionally based on channel choice -- WhatsApp shows phone, Desktop shows email); name (optional, used so the AI Copilot can address the invitee by name); role (one of Owner / Factory Manager / Co-Owner / Manager / Operator / Viewer, gated per the v6.3.3 role matrix); consent checkbox (required when channel is WhatsApp). Submit button label varies by channel choice ("Send WhatsApp invite" vs "Send email invite") so the action is honest.

Backend support: InviteRequest schema in app/schemas/team.py is extended with optional channel, consent_given (default False), and name fields. Back-compat is preserved -- the existing email_or_phone freeform field remains; a Pydantic model_validator derives an internal channel value from the field's format (E.164 phone implies channel='whatsapp', containing '@' implies 'desktop'). When channel is whatsapp, consent_given must be true; the validator returns 422 with "WhatsApp invites require explicit consent" otherwise. v6.3.3 callers continue to work for desktop invites; WhatsApp invites without consent are intentionally broken (the new business rule). Long-term cleanup: deprecate email_or_phone in v6.5+ in favour of explicit email and phone_e164 fields.

Welcome dispatch: a new helper at app/services/team_invite_whatsapp.py named send_invite_welcome composes and dispatches the consent-handshake message via the existing _send_alert path. In mock mode (WHATSAPP_MOCK_MODE=True) the message logs as [MOCK ALERT] to stdout; in production it is sent via Interakt. The handshake is the same one the proprietor went through at signup (Section 6.28 Feature 1) -- the invitee replies YES on WhatsApp; the YES handler in app/routers/whatsapp_router.py looks up the PhoneTenantMap row by phone_e164 and flips consent_given=True. v6.3.5 confirms or extends the existing YES handler to recognise invited members in addition to proprietor-linked numbers. An events row of type member.invited_whatsapp is written via the migration 028 events table (Section 9.2) for audit consistency with v6.3.3 role-change events; the row captures invitee_phone_e164, invitee_role, channel, consent_given, welcome_message_id (when Interakt returns one), and invited_by_user_id.

**Change 4 -- Minimal post-signup landing page at /welcome.**

A new page at frontend/src/pages/PostSignupLanding.tsx replaces the v6.3.2 ConnectWhatsApp placeholder. The signup endpoint continues to return next_step='connect_whatsapp' for whatsapp_first and hybrid signups (the value is not renamed in v6.3.5; deferred to a v6.5+ cleanup); the frontend RegisterPage.tsx routes that value to /welcome instead of /connect-whatsapp. The /welcome route is gated to authenticated users who just signed up (a session flag is set during the register endpoint); direct visits otherwise redirect to /dashboard so the page does not become a bookmarkable dead-end.

Page composition: a single hero card with the title "You're set up, {name}", subtitle "Your floor runs from WhatsApp now"; two primary CTAs ("Open WhatsApp" deep-linking via https://wa.me/<WHATSAPP_BOT_NUMBER>?text=Hi and "Bookmark dashboard" linking to /dashboard); a stats card showing today's headline numbers (jobs in progress, operators on shift, week revenue); demoted footer links ("View full dashboard", "View team", "Settings"). The "Open WhatsApp" CTA renders disabled with explanatory copy when WHATSAPP_BOT_NUMBER is empty in app/config.py, so the page degrades safely in dev environments without a configured bot number.

Configuration: WHATSAPP_BOT_NUMBER is added to app/config.py and .env.example with empty-string default. Distinct from any existing outbound-send number config -- the deep-link number may be the same as the outbound-send number in early production but is kept separate for future flexibility (a Meta Business Account can have multiple sender IDs).

**Acceptance criteria.**

(1) Direct visits to /whatsapp and /connect-whatsapp return 404. (2) Sidebar in Layout.tsx no longer shows a WhatsApp nav item. (3) Whatsapp_first signup routes to /welcome (not /dashboard, not /connect-whatsapp); /welcome renders the hero, CTAs, stats card, and footer links. (4) Direct visit to /welcome from a non-just-signed-up user redirects to /dashboard. (5) GET /api/team returns the redesigned shape: every member has whatsapp_status in {'active','invited','disconnected','none'}; every member's email is either null or a real email (no synthesised invite-XXX or whatsapp.local strings). (6) The Invite modal opens from Team and Roles, supports both channels, swaps phone and email fields based on channel choice, requires consent for WhatsApp, and submits to POST /api/team/invite. (7) WhatsApp invite without consent_given returns 422 with a clear error message; the existing v6.3.3 desktop invite path continues to work. (8) WhatsApp invite dispatches a [MOCK ALERT] log line in mock mode; the invitee row appears in /api/team with whatsapp_status='invited'. (9) Inbound YES from the invitee on the WhatsApp webhook flips consent_given=True and the invitee's whatsapp_status changes to 'active' on the next /api/team call. (10) An events row of type member.invited_whatsapp is written on welcome dispatch with rich payload. (11) BUG-6 regression test (industry_type read from Tenant ORM at signup-time PhoneTenantMap creation) and v5.12 role-limiting regression both still pass. (12) v6.3.4 briefing dispatcher and v5.10/v5.15 alert paths are not modified by v6.3.5 and continue to fire as expected.

**Out of scope (deferred).**

Renaming next_step value from 'connect_whatsapp' to 'post_signup_landing' (cleaner but requires a backend touch and regression test; deferred to v6.5+). Migrating InviteRequest schema from email_or_phone to explicit email/phone_e164 fields (deferred). Settings sub-pages for Entry Mode, Business Details, Billing (not in v6.3.5 scope; appear as not-shown in the sidebar, not as disabled stubs). Frontend component tests for the modal, table, and landing page (depend on @testing-library/dom which has been pending since v6.3.2; install in v6.3.5 if peer-dep tree cooperates within a one-hour time-box, otherwise ship backend-only tests and defer frontend tests to a follow-up). WhatsApp Briefings sub-page on Settings (planned for v6.3.6, shown as a disabled "Coming in v6.3.6" stub in v6.3.5).

**Risks specific to v6.3.5.**

(a) Missed reference to the deleted pages would break the build. Mitigated by deleting routes first, files second, with TypeScript and Vite build as the final gate. (b) InviteRequest shape change could break v6.3.3 callers if back-compat is not preserved. Mitigated by extending the schema with optional fields, deriving channel from the existing email_or_phone field via a Pydantic validator, and adding a v6.3.3 regression test that runs against the new schema. (c) TeamMemberOut.email becoming nullable propagates through every consumer of /api/team. Mitigated by introducing a TeamMemberView adapter type with a non-nullable displayEmail field at the type boundary, plus a property-based test that asserts no synthesised email leaks back into the response. Strict TypeScript null-checks catch the rest at compile time.

# 7. Bug Fixes & Issues Resolved

## 7.1 v3.x Bug Fixes (carried from SRS v2.0)

| **#** | **Issue** | **Fix** | **Release** |
| --- | --- | --- | --- |
| 1 | Machine overbooking — no warning | Overbooking check in create_assignment(). Named conflict message. | v3.7.1 |
| 2 | Generic clash message | check_job_availability queries clashing job name and date range. | v3.7.1 |
| 3 | Login broken — page stays on /login | LoginPage uses AuthContext.login() with in-memory tokenStore. | v3.8 |
| 4 | FeatureFlagProvider outside AuthProvider | Moved inside App.tsx ProtectedRoute scope. | v3.8 |
| 5 | AI router returning 404 | ai_chat router registered in main.py. | v3.9 |
| 6 | Feature guard returning 403 | Changed to warm 200 response with available:false. | v3.7 |
| 7 | Steps panel stale cache | Invalidates both [steps, jobId] and [jobs] on step add/delete. | v3.6 |
| 8 | scan router missing from main.py | Scan router registered in v3.6. | v3.6 |

## 7.2 v4.0 Bug Fixes

| **#** | **Issue** | **Fix** | **Release** |
| --- | --- | --- | --- |
| 9 | alembic_version 'overlaps' error | Stale 014 entry in alembic_version table. DELETE WHERE version_num='014' then upgrade head. | v4.0 |
| 10 | industry_type column does not exist | Migration 016 not applied. alembic upgrade head required. | v4.0.1 |
| 11 | GanttPage — useLabels not defined | Import was missing. IndustryContext import not found by Vite. | v4.0.5 |
| 12 | CsvImport template download 401 | Template used plain anchor <a href='http://localhost:8000'>. Changed to apiClient with responseType:blob. | v4.0.8 |
| 13 | Dashboard JobCard crash on expand | job.assigned_employees undefined for seeded jobs. Fixed: fetches GET /api/jobs/{id} on expand, falls back to ?? [] safe guard. | v4.0.9 |
| 14 | Layout sidebar shows 'Employees'/'Machines' for all industries | Layout.tsx on disk was not updated with v4.0.3 changes. Full replacement applied. | v4.0.9 |
| 15 | GettingStarted — hooks order violation | return null was before useEffect calls. Moved return null after all hooks. | v4.1 |
| 16 | Stale Layout.tsx — old MSME branding | Layout on disk had old hardcoded nav labels and 'MSME Resource Scheduler' branding. Replaced with full v4.0.8 version. | v4.0.9 |

# 8. Non-Functional Requirements

## 8.1 Performance

- Dashboard and Gantt chart load within 2 seconds for datasets up to 500 concurrent jobs and 100 employees.

- Auto-assignment for a single job completes within 5 seconds.

- Batch optimisation for up to 50 jobs completes within 60 seconds.

- 50 concurrent user sessions per tenant without degradation.

- AI Copilot tool-calling responses within 3 seconds on Groq infrastructure.

- Job card expand detail fetch (GET /api/jobs/{id}) within 300ms.

## 8.2 Scalability

- Architecture supports horizontal scaling to 10,000 tenants.

- Database accommodates 10 years of historical job and utilisation data per tenant.

- Feature flag system designed for future per-tenant flag management (currently global).

- Industry config layer designed for additional verticals — new industry added by creating one config file.

## 8.3 Security

- All data in transit encrypted using TLS 1.3 or above.

- All data at rest encrypted using AES-256.

- Tenant data isolated via row-level tenant_id filtering on every query.

- JWT tokens stored in memory only (tokenStore) — never localStorage.

- bcrypt password hashing — direct import, cost factor 12. (passlib incompatible with Python 3.12+)

- RBAC enforced at API layer via require_role dependency injection.

- Scan tokens are JWT-based with expiry — no auth required for shop floor QR scanning.

## 8.4 Availability & Reliability

- Target uptime: 99.5% (excluding planned maintenance).

- Automated daily database backups with 30-day retention.

- Graceful error handling — no unhandled exceptions exposed to end users.

- Feature flags allow instant rollback of features without code redeployment.

- Demo seeder wrapped in try/except — seeding failure never breaks registration.

## 8.5 Usability

- New user completes full onboarding (add employee, machine, job, assign, start) in under 3 minutes.

- 8-step Getting Started checklist with auto-detection guides users from zero to productive.

- Industry-aware labels throughout — no generic 'Employees' or 'Machines' shown to chemical or field service users.

- Support for desktop browsers: Chrome, Firefox, Edge, Safari.

- Empty states on all major pages guide users to the correct next action.

# 9. Data Model Summary

## 9.1 Core Entities

| **Entity** | **Key Attributes** | **v4.0 Changes** |
| --- | --- | --- |
| Tenant | id, name, slug, plan, is_active, industry_type, ai_queries_today | industry_type column added (migration 016). Stores selected industry vertical. |
| User | id, tenant_id, email, role, status | No changes. |
| Employee | id, tenant_id, full_name, department, employment_type, base_availability_pct, hourly_rate, overtime_rate, source (manual│whatsapp│erp_sync), worker_type (permanent│contractor) | source and worker_type added in migration 023 (v5.16). source tracks data origin for v7.0 ERP connector. worker_type enables contractor labour layer (v7.2). UI labels adapt per industry. |
| EmployeeSkill | employee_id, skill_id, skill_level | No changes. |
| EmployeeLeave | id, employee_id, tenant_id, start_date, end_date, reason | No changes. Blocks scheduler occupancy map. |
| Machine | id, tenant_id, name, machine_type, base_availability_pct, source (manual│whatsapp│erp_sync) | source added in migration 023 (v5.16). Tracks data origin for v7.0 ERP connector. UI labels adapt per industry. |
| MachineSkillRequirement | machine_id, skill_id, min_skill_level, employees_required | No changes. |
| MachineDowntime | id, machine_id, tenant_id, start_date, end_date, reason | No changes. |
| Skill | id, tenant_id, name, category, is_premium, is_active | No changes. |
| Job | id, tenant_id, name, customer, start_date, end_date, order_value, priority, status, job_type, quantity, raw_materials, timer_status | job_type (String) and quantity (Float) added in migration 015. Required for material estimate. |
| JobSkillRequirement | job_id, skill_id, min_skill_level, employees_required | No changes. |
| JobAssignment | id, job_id, employee_id (nullable), machine_id (nullable), allocation_pct, tenant_id | No changes. |
| JobStep | id, job_id, tenant_id, sequence_no, name, step_type, duration_minutes, status | No changes. |
| StepResource | id, step_id, tenant_id, resource_type, resource_id | No changes. |
| ScheduleEntry | id, tenant_id, job_id, step_id, scheduled_start, scheduled_end | No changes. |
| TenantKPISnapshot | tenant_id, snapshot_date, orders_delayed_count, orders_on_time_count, substitute_find_minutes_avg, overtime_hours_total, machine_idle_hours, conflicts_detected, conflicts_resolved_by_ai, is_baseline | *Planned for v6.3 — not yet on disk; migration number assigned at ship time.* One row per tenant per day. First 7 days tagged is_baseline=True. 13-month rolling retention. |
| ComplianceItem | tenant_id, item_type, item_name, renewal_frequency, last_filed_date, next_due_date, status, industry_default | *Planned for v6.6 — not yet on disk; migration number assigned at ship time.* Industry-appropriate items seeded at tenant registration. |
| ComplianceDocument | compliance_item_id, tenant_id, filename, mime_type, uploaded_at, file_path, uploader_user_id | *Planned for v6.6 — not yet on disk; migration number assigned at ship time.* 5-year retention. 10 MB file limit. PDF, JPG, PNG, XML supported. |
| ComplianceReminderLog | compliance_item_id, reminder_day, sent_at, channel | *Planned for v6.6 — not yet on disk; migration number assigned at ship time.* reminder_day in {30, 7, 1}. Idempotent send via log check. |

## 9.2 Migration Chain (v5.9)

| **Revision** | **Description** |
| --- | --- |
| 001 — 009 | Initial schema — tenants, users, employees, machines, skills, jobs, assignments, leaves, downtimes. |
| 010 | Scheduling tables — schedule entries. |
| 011 | Schedule entries — additional scheduling columns. |
| 012 — 013 | Scheduling tables refinements. |
| 014 | Schedule entries finalisation. |
| 015 | job_type (String) and quantity (Float) columns on jobs table. Required for material estimate (v3.9.8). |
| 016 | industry_type (String, default: 'printing') on tenants table. Required for v4.0 multi-industry support. |
| 017 | WhatsApp phone mapping tables -- phone_tenant_map (phone number E.164, tenant_id, user_id, is_active, consent_given, alert_preferences JSONB) and whatsapp_conversations (Factory GPT training data: role, content, language, session_id, consent_given). Introduced v5.0. |
| 018 | WhatsApp RBAC -- adds display_name (VARCHAR 100, nullable) and phone_role (VARCHAR 20, NOT NULL, default owner; values: owner │ manager │ viewer) to phone_tenant_map. Introduced with role limiting support. |
| 019 | AI usage tracking -- adds ai_queries_today (INT DEFAULT 0), ai_tokens_today (INT DEFAULT 0), ai_queries_date (DATE NULL), industry_type (VARCHAR 50 NULL) to tenants. Uses IF NOT EXISTS for safe re-runs. Introduced v4.0.9. |
| 020 | Unavailability and allocation -- adds allocation_pct (FLOAT NULL) to job_assignments; creates employee_leaves table (tenant_id, employee_id, start_date, end_date, reason); creates machine_downtimes table (tenant_id, machine_id, start_date, end_date, reason). Introduced v4.0.9. |
| 021 | Job locking -- adds is_locked (BOOLEAN NOT NULL DEFAULT FALSE) to jobs. Introduced v4.0.9. |
| 022 | Original dates -- adds original_start_date and original_end_date (DATE NULL) to jobs. Introduced v4.0.9. |
| 023 | Source and worker type -- adds source (VARCHAR 20, server_default=manual) to employees and machines; adds worker_type (VARCHAR 20, server_default=permanent) to employees. Introduced v5.16. |
| 024 – 026 | *Skipped — never used.* The chain goes directly from 023 to 027 (`027.down_revision = "023"`). These numbers are not reserved; future migrations continue from the current head. |
| **027** | WhatsApp Entry Gate -- adds entry_mode (enum: whatsapp_first / desktop_first / hybrid, NOT NULL, default 'desktop_first') and size_segment (enum: small / medium / large, nullable) to tenants. Adds briefing_morning_enabled, briefing_morning_time, briefing_evening_enabled, briefing_evening_time, briefing_timezone (default 'Asia/Kolkata'), briefing_working_days (default '1,2,3,4,5,6') to tenants. Adds briefing_time_override_morning, briefing_time_override_evening, briefing_subscribed (default true), phone_e164 (indexed, nullable) to users. Adds created_via (enum, default 'desktop_signup') to tenants and users. Extends users.role enum with factory_manager and co_owner. Extends phone_tenant_map.phone_role enum similarly. Required for v6.4. See Section 6.28. |
| **028** | Events audit table -- creates events table to back the role-change audit trail emitted by app/routers/team_management.py and to be consumed by briefing.* events from the v6.3.4 push-briefing dispatcher and additional event types in subsequent iterations. Columns: id (PK), tenant_id (FK to tenants.id, ON DELETE CASCADE), event_type (VARCHAR 50, dotted vocabulary like user.role_changed, briefing.sent), entity_type (VARCHAR 50, discriminator), entity_id (INTEGER nullable, no FK because events span entity types and must outlive their referent), actor_user_id (FK to users.id, ON DELETE SET NULL, NULL for system-generated events), source (VARCHAR 20, permissive String not DB enum so future sources like cron / erp_sync require no migration), payload (JSONB nullable, patched to JSON for SQLite test DB), created_at (TIMESTAMPTZ NOT NULL, server default now(), patched for SQLite via patch_now_defaults_for_sqlite autouse fixture). Indexes: idx_events_tenant_id (single column), idx_events_tenant_event_type (composite tenant_id + event_type, hot-path for "what role changes happened in this tenant"), idx_events_entity (composite entity_type + entity_id, per-entity history lookups). Invariants: append-only (no updated_at column, corrections are new rows referencing the prior); tenant isolation enforced at FK CASCADE level, application layer must additionally filter by tenant_id; downgrade drops indexes and table (acceptable because table is additive, contains no business-critical state). Introduced v6.3.3. |
| **029** | extraction_candidates staging table -- adds the staging table that holds entity candidates the entity-extractor service identifies from inbound WhatsApp messages before they're promoted into employees / machines / skills. File: `029_add_extraction_candidates_table.py`. Introduced v6.3.13. |
| **030** | Confirmation-state columns on extraction_candidates -- adds the four `confirmation_*` columns that gate candidate promotion behind explicit owner HAAN reply (the v6.3.15 revision retracted silent insertion). File: `030_add_confirmation_state_columns.py`. Introduced v6.3.15 (revised). |
| **031** | Day-7 engagement columns on tenants -- adds `first_briefing_sent_at` and `engagement_ladder_state` to tenants, supporting the Day-7 First-Insight Gate (a one-shot owner message on the seventh day of delivered morning briefings). File: `031_add_day7_engagement_columns.py`. Introduced v6.3.16. |
| **032** | source column on skills -- extends the `source` field pattern (already on Employee + Machine since migration 023) to Skill, supporting WhatsApp owner-bypass entity writes with the new `whatsapp_owner` source value. File: `032_add_source_to_skills.py`. **Current head.** Introduced v6.3.17. Next migration must use revision ID 033 and chain `down_revision = "032"`. |

> **NOTE** Always use 'alembic upgrade head' — not raw SQL files. The migration chain is managed by Alembic. Current head: 032.

# 10. System Architecture

## 10.1 Technology Stack

| **Layer** | **Technology** |
| --- | --- |
| Backend | FastAPI + Python 3.14 + Uvicorn + Gunicorn |
| ORM + Migrations | SQLAlchemy 2.0 + Alembic (migration head: 032) |
| Database | PostgreSQL 15/16 with row-level tenant_id isolation on all queries |
| Auth | JWT via python-jose, bcrypt direct import |
| Frontend | React 18 + TypeScript + Vite |
| State / Data Fetching | TanStack React Query (useQuery, useMutation) |
| Styling | Tailwind CSS + CSS custom properties for industry theme switching |
| Industry Config | TypeScript config files per industry in src/config/industries/ |
| AI Copilot | Groq API — tool-calling architecture — 16 DB tools — industry-aware system prompt |
| CSV / Excel | openpyxl (backend), papaparse (frontend), SheetJS (frontend) |
| Onboarding | localStorage per user, TanStack Query cache for auto-detection |
| QR Codes | qrcode.react — client-side only |
| **WhatsApp Channel** | Meta WhatsApp Business API (via Interakt in production, mock bridge in dev) + Upstash Redis (session state) + OpenAI Whisper (voice note transcription, v5.11) |

## 10.2 Architecture Rules (Critical)

- Every DB query must include tenant_id filter — enforced at service layer.

- Date columns return Python datetime — always call .date() before comparing.

- Auth token is in-memory (tokenStore) — use navigate() not window.open().

- bcrypt imported directly — never via passlib.

- React Query key conventions: ['jobs'], ['steps', jobId], ['employees'], ['machines'], ['dashboard'].

- After mutations affecting scheduling: call markDirty() from useSchedulerContext().

- New DB columns must be nullable or have a default — no breaking migrations.

- Industry labels accessed via useLabels() hook — never hardcoded strings in components.

- CSV template download uses apiClient with responseType:'blob' — never plain anchor tags.

## 10.3 Industry Context Architecture

The industry configuration layer flows as follows:

- On login: /auth/me returns industry_type from tenant record.

- IndustryContext loads config from getIndustryConfig(industryType).

- useEffect applies theme-{industry} class to <body> — CSS variables activate.

- All components call useLabels() — no component contains hardcoded UI strings.

- AI Copilot: ai_chat.py reads industry_type from tenant on every request, passes to _build_system_prompt(industry_type).

# 11. Optimisation Algorithm Specification

## 11.1 Problem Formulation

The scheduling problem is modelled as a variant of the Resource-Constrained Project Scheduling Problem (RCPSP) with profit maximisation objective.

- Decision variable: x_j = 1 if job j is scheduled, 0 otherwise.

- Objective: Maximise sum of (profit_j × x_j) for all jobs j.

- Machine constraint: For each date d, machine must have availability > 0 and not be assigned to another job.

- Employee constraint: For each skill s required, at least q_s employees with required level, available on date d, not fully committed.

## 11.2 Implemented Algorithm (Greedy Forward-Scan)

- Sort jobs: Critical > High > Medium > Low, then order value descending.

- For each job: find earliest start date where all assigned resources are free.

- Employee leaves and machine downtimes pre-loaded into occupancy map as blocked ranges.

- Locked jobs loaded as fixed windows — scheduler never modifies them.

- Once slot found: set job start/end date, mark resources occupied, persist to DB.

## 11.3 Known Algorithm Gaps

- % allocation not considered — 50% employee on two jobs currently flagged as conflict. Fix planned v4.1.

- What-if simulation not implemented. Priority + Lock provides manual workaround. Full simulation planned v4.2.

- Delivery date vs end date: field exists in DB but not yet used in scheduler feasibility. Fix planned v4.1.

# 12. Known Gaps & Planned Work

| **#** | **Pain Point** | **Status** | **Planned Fix** | **Target** |
| --- | --- | --- | --- | --- |
| 1 | Operator % allocation | **⚡ Partial** | 50%+50% flagged as conflict. Fix scheduler to respect allocation_pct. | v4.1 |
| 2 | Delivery date in scheduler | **⚡ Partial** | delivery_date field exists. Not yet used in scheduler feasibility. | v4.1 |
| 3 | Actual vs estimated hours feedback | **⚡ Partial** | actual_hours field exists. Feedback loop not yet built. | v4.1 |
| 4 | What-if simulation | **📋 Planned** | Full side-by-side scenario comparison. Priority+Lock is partial workaround. | v4.2 |
| 5 | Mobile optimisation | **📋 Planned** | Critical when QR scan goes to shop floor workers. | v4.2 |
| 6 | Audit log | **📋 Planned** | 3-year retention. Compliance for larger shops. | v4.2 |
| 7 | Machine utilisation report | **📋 Planned** | Needs historical data. AI Copilot covers conversationally today. | v4.2 |
| 8 | Email notifications | **📋 Planned** | Smart Alerts on Dashboard cover in-app today. | v4.2 |
| 9 | Per-tenant feature flags | **📋 Planned** | Currently global config file. Per-tenant flags needed for billing tiers. | v5.0 |
| 10 | ERP webhooks (Tally, Zoho) | **📋 Planned** | REST API exposed. Webhook support on job status change. | v5.0 |
| 11 | Knowledge graph layer (NetworkX) | **⚡ Partial** | Schema context layer (app/knowledge_graph/schema_context.py) chosen over full NetworkX graph for v5.x. Resolves multi-hop AI reasoning with zero infrastructure change. Full NetworkX graph (shortest path, community detection) targeted v6.0. | v5.x / v6.0 |
| 12 | Hindi language interface | **📋 Planned** | AI Copilot handles Hinglish today. Full UI translation planned. | v5.0 |
| **13** | Proactive alerts testing | DONE v5.10 | Morning briefing, conflict alert, job delay alert all live in mock mode. | v5.10 |
| **14** | Meta Business portfolio link | Blocked | Zero Zeta Business Portfolio appeal submitted Apr 8. In review. | Blocked -- Meta review |
| **15** | Interakt integration and production config | Blocked | Pending Meta approval. New SIM obtained, not on consumer WhatsApp. | Blocked -- Meta review |
| 16 | WhatsApp role limiting (owner/manager/viewer) | DONE v5.12 | phone_role enforcement in place. Blocked actions never reach AI. | v5.12 |
| 17 | 3-language support (Hindi / Hinglish / English) | DONE v5.12 | detect_language() in whatsapp_responses.py. LANGUAGE_INSTRUCTION in system prompt. | v5.12 |
| 18 | Day 1 Simple Table (seed worker + machine data) | DONE v5.16 | First screen after registration. source and worker_type fields in DB. | v5.16 |
| 19 | Manager check-in flow (7:00am WhatsApp input) | DONE v5.15 | APScheduler triggers check-in. Absent worker -> substitute suggestion. | v5.15 |
| 20 | Owner briefing (7:15am WhatsApp output) | DONE v5.15 | Single clean briefing generated from manager inputs. No questions to owner. | v5.15 |
| 21 | RAG pipeline with industry templates | DONE v6.1 | Flat file MVP. rag_data/_templates/{industry}/ seeded at registration. | v6.1 |
| 22 | Industry-aware dynamic UI labels | DONE v6.2 | useLabels() hook. Sidebar and page titles dynamic per industry_type. | v6.2 |
| 23 | RegisterPage auth bug (localStorage bypass) | DONE v6.2 | AuthContext.register() now called correctly. localStorage direct call removed. | v6.2 |
| 24 | Voice notes via WhatsApp (Whisper API) | Blocked | Blocked by Meta/Interakt go-live (v5.11). Needs real inbound audio. | v5.13 |
| 25 | RAG pgvector migration | Planned | Adds tenant_knowledge_base table with embeddings; migration number assigned at ship time. Flat file structure unchanged. | v6.8 |
| **25a** | **WhatsApp as Primary Entry Gate** | Planned | Entry-mode routing at signup, top-tier role expansion (Owner / Factory Manager / Co-Owner), configurable morning + evening daily push briefings on WhatsApp. Migration 027. Builds on v6.3.0-whatsapp-industry. See Section 6.28. | **v6.4** |
| 26 | Prove ROI to owner month-over-month | Planned | KPI Baseline + Monthly Savings Summary. Will create tenant_kpi_snapshot table; migration number assigned at ship time. See Section 6.24. | v6.3 |
| 27 | Material estimation as first-class WhatsApp entry point | Planned | Standalone WhatsApp surface for "kitna chahiye" queries. Backend already in v3.9.8. See Section 6.25. | v6.5 |
| 28 | Compliance deadline tracking (GST, ESI, PF, NOC) | Planned | Pulled forward from v7.1. WhatsApp reminders + document upload. Migration number assigned at ship time. See Section 6.26. | v6.6 |
| 29 | GST e-invoicing JSON generation | Planned | GSTN schema v1.1 JSON from completed jobs. Migration number assigned at ship time. See Section 6.27. | v6.7 |

# 13. User Interface Requirements

## 13.1 Navigation Structure

- Dashboard — Live job board, KPI cards, Smart Alerts, Getting Started checklist.

- Jobs / Batch Orders / Production Orders — List, Create (wizard), Edit, Expand detail, Assign resources, Timer controls.

- Employees / Operators / Technicians — List, Create, Edit, Unavailability panel, CSV import.

- Machines / Reactors / Work Centers — List, Create, Edit, Unavailability panel, CSV import.

- Skills / Qualifications / Certifications — Catalogue management.

- Production Timeline — Gantt chart. Gated behind gantt flag (V2 tier).

- AI Copilot — Floating panel, industry-aware suggestions, 50 industry-aware pre-built tools. Gated (V4 tier).

## 13.2 ZetaOps Copilot Branding (v4.0.3)

- Application name: ZetaOps Copilot (formerly MSME Resource Scheduler).

- ZeroZeta logo (PNG) in sidebar, login page, and registration page.

- Logo served from frontend/public/logo.png. Sidebar uses brightness-0 invert CSS to show white on dark background.

- Sidebar shows: ZeroZeta logo → 'ZetaOps Copilot' → industry product name subtitle.

- Page title in index.html: 'ZetaOps Copilot'.

- Login/Register pages: ZeroZeta logo + 'ZetaOps Copilot' heading.

## 13.3 Key Screen Specifications

### Job Creation Wizard

- Step 1: Basic info — name, customer, start mode, dates, order value, priority.

- Step 2: Machines & People — skill requirements with quantity and minimum level.

- Step 3: Materials & Confirm — raw materials, cost summary, confirm.

- Wizard step labels use industry terms: 'Job Details / Machines & People / Raw Materials & Confirm' → 'Batch Order Details / Reactors & People / Batch Inputs & Confirm'.

### Dashboard Job Card Expand

- Expand (▼) fetches full job detail via GET /api/jobs/{id}.

- Shows assigned employees/machines from full job response.

- Falls back to ?? [] safe guard if assigned arrays are undefined.

- Loading spinner shown while fetching detail.

### Getting Started Panel

- Fixed position bottom-left (z-20). Does not block header toolbar or AI Copilot button.

- 8 logical steps with Go → navigation buttons.

- Progress bar and completion percentage.

- Restart tour via footer button or header ? button.

# 14. Integration Requirements

- REST API exposed for potential ERP integration (Tally, Busy, Zoho Books). Planned v5.

- Webhook support on job status change — configurable URL. Planned v4.2.

- CSV / Excel import for bulk upload. Live in V4 tier.

- PDF and Excel export for all major reports. Planned v4.2.

- Google Calendar integration for exporting job schedules. Planned v5.

- Groq API integration for AI Copilot. Live in V4 tier. Industry-aware as of v4.0.8.

- Schema context layer (app/knowledge_graph/schema_context.py) live in v5.x. Fixes AI multi-hop reasoning. NetworkX resource graph planned v6.0. See Section 17.

# 15. Subscription & Billing Model

| **Plan** | **Price** | **Product Tier** | **Limits** | **Features** |
| --- | --- | --- | --- | --- |
| Starter | ₹1,999/mo | V1 — Job Board | 2 users, 30 employees, 20 machines, 50 jobs/month | Core scheduling, manual assignment, basic reports |
| Growth | ₹4,999/mo | V2 + V3 | 5 users, 80 employees, 50 machines, unlimited jobs | Auto-scheduler, Gantt, QR scan, step intelligence, API access |
| Enterprise | Custom | V4 — Full Platform | Unlimited users, employees, machines, jobs | CSV import, AI Copilot, industry themes, demo seeder, custom domain, dedicated support |

# 16. Implementation Roadmap

| **Phase** | **Status** | **Releases** | **Deliverables** |
| --- | --- | --- | --- |
| Phase 1 — Foundation | **✅ Complete** | v3.0 — v3.6 | Multi-tenant auth, jobs CRUD, employees, machines, skills, manual assignment, auto-scheduler, Gantt, AI Copilot, QR scan, step intelligence, unavailability, CSV import. |
| Phase 2 — V1 Ready | **✅ Complete** | v3.7 — v3.9 | Feature flag architecture, release ladder, machine overbooking fix, contextual help, getting started checklist, empty states, AI proactive greeting, login fix, schedule suggestions, material estimate, AI tool-calling. |
| Phase 3 — Multi-Industry | **✅ Complete** | v4.0.1 — v4.0.9 | Industry type on tenant, 5 industry config files, IndustryContext, useLabels(), ZetaOps Copilot branding, all page labels, demo seeder, CSS theme engine, industry-aware AI, industry-aware tools, onboarding checklist v2, bug fixes. |
| Phase 4 — V4.1 Fixes | **📋 Planned** | v4.1 | Delivery date in scheduler, % allocation fix, actual vs estimated hours feedback loop. |
| Phase 5 — V4.2 Enhancements | **📋 Planned** | v4.2 | What-if simulation, mobile optimisation, audit log, utilisation reports, email notifications. |
| Phase 6 — Factory GPT | **📋 Planned** | v5.0+ | Schema context layer (app/knowledge_graph/), proactive monitoring, multi-hop AI reasoning, ERP webhooks, Google Calendar, per-tenant feature flags, Hindi language. |
| **Phase 7 — WhatsApp Live** | Done (mock mode) | v5.12, v5.15, v5.16 | Role limiting + 3-language support (v5.12). Day 1 Simple Table with source/worker_type (v5.16). Manager check-in flow + owner briefing (v5.15). WhatsApp go-live blocked by Meta review. |
| **Phase 8 — Factory GPT** | Done | v6.0, v6.1, v6.2 | Schema context layer (v6.0). RAG pipeline flat file MVP, industry templates for 4 verticals (v6.1). Dynamic UI labels via useLabels() hook, RegisterPage auth fix (v6.2). |
| Phase 8.5 -- Entry Gate, Proof and Retention | Planned | v6.3 - v6.7 | v6.3: KPI Baseline + monthly WhatsApp savings summary (retention moat). v6.4 (NEW STRATEGY -- April 28, 2026): WhatsApp as Primary Entry Gate -- entry-mode routing, top-tier role expansion (Owner / Factory Manager / Co-Owner), configurable morning + evening daily push briefings on WhatsApp. Migration 027. See Section 6.28. v6.5: Material Estimator as first-class WhatsApp surface (acquisition wedge; was previous v6.4). v6.6: Compliance Tracker (was previous v6.5). v6.7: GST E-Invoicing JSON generation (was previous v6.6). Reshuffled after IDC Worldwide Intelligent ERP 2025 analysis (April 20, 2026) and again after v6.3.0-whatsapp-industry release (April 28, 2026). |
| Phase 9 -- ERP Connector | Planned | v7.0+ | Python connector for SAP / Tally / Excel. Pulls employee list, active orders, leaves and machine downtime. Daily sync at 6:30am. source field activated for erp_sync. Same scheduling engine -- zero changes. Contractor labour layer (v7.1, renumbered from v7.2 after compliance moved forward to v6.5 / Phase 8.5). |

# 17. AI Architecture Roadmap (v5.x to v6.0)

This section documents the AI architecture decisions made during v5.x and the strategic path to Factory GPT (v6.0). It covers three topics: (1) the schema context layer that fixes AI multi-hop reasoning today without a graph database, (2) the WhatsApp Copilot pipeline architecture, and (3) the v6.0 Factory GPT direction using NetworkX and SupervisorAgentBridge.

## 17.1 The AI Architecture Decision: Schema Context over Graph DB

The original roadmap specified NetworkX as the solution to AI multi-hop reasoning failures. After analysis, the root cause was identified as simpler: the LLM did not know the schema. It was guessing JOIN paths and getting them wrong. A full graph database was not required to fix this.

The chosen solution is a Schema Context Document: a static Python dict at app/knowledge_graph/schema_context.py that describes every entity, every FK relationship with exact column names, common multi-hop query patterns, and the tenant_id filter requirement. This is injected into the LLM system prompt before every query.

**Why not NetworkX for v5.x: **A KG is not auto-discovered. It requires the same intellectual work as maintaining an ERD, expressed differently. The schema context achieves 80% of the multi-hop benefit with 10% of the complexity, zero new infrastructure, and zero latency overhead. NetworkX adds genuine value only when queries require shortest-path algorithms, community detection, or user-defined runtime relationships — none of which ZetaOps v5.x requires.

## 17.2 Schema Context Layer: Files and Maintenance

- app/knowledge_graph/schema_context.py — Entity definitions and FK relationship strings with exact column names. Includes common multi-hop patterns and the tenant_id mandate. Generated from SRS + SQLAlchemy models. Reviewed and committed as a static file.

- app/knowledge_graph/context_builder.py — Reads schema_context.py and returns a compact string injected into the LLM system prompt before every AI Copilot query.

- Maintenance rule: if a migration adds a new table or FK, schema_context.py must be updated in the same commit. This is added to the pre-commit checklist (Section 8 of the master dev prompt).

- The context is static per deployment, not dynamic per query. Sub-millisecond overhead. No DB reads at query time.

## 17.3 WhatsApp Copilot Pipeline Architecture

The WhatsApp Copilot uses the identical tool-calling AI pipeline as the web Copilot. The only difference is the transport layer. Message arrives via Meta webhook, routes through whatsapp_bridge.py (async/sync bridge via run_in_executor), enters the same Groq tool-calling loop, and response is sent back via Interakt API (mock in dev, real in production).

- **Session state: **Upstash Redis stores conversation history per phone number. All WhatsApp services use sync SQLAlchemy Session — never AsyncSession. Router self-prefixes at /api/v1/whatsapp, registered in main.py with no prefix.

- **Confirmation flow: **Write-operations detected by intent classifier. User sent a confirmation prompt before DB commit. Read-only queries bypass confirmation and execute immediately.

- **Proactive alerts: **Trigger endpoint fires without user query. Three alert types: morning briefing (daily summary of active jobs and conflicts), conflict alert (triggered when scheduler detects overbooking), job-ending-soon (jobs ending within 24 hours with no completion status). Alert log in DB prevents duplicate sends.

- **Voice notes: **Whisper transcription step converts incoming voice message to text before the message enters the standard AI pipeline. No changes to pipeline required beyond the transcription shim.

- **Dev vs production: **WHATSAPP_MOCK_MODE=True in dev. All outbound messages logged to console, no Meta API calls made. WHATSAPP_MOCK_MODE=False in production with real Interakt key and Redis URL from .env via Settings.

## 17.4 Path to Factory GPT (v6.0)

Factory GPT is a one-line code change once the WhatsApp channel is live on real data. The swap is: GroqDirectBridge to SupervisorAgentBridge in the WhatsApp router. SupervisorAgentBridge adds a supervisor LLM layer that maintains continuous graph state, detects anomalies proactively, and routes complex multi-turn queries to specialist sub-agents.

- **NetworkX resource_graph.py: **Built on demand per tenant from Postgres. DiGraph nodes: job:{id}, emp:{id}, machine:{id}, skill:{id}. Edges: has_skill, requires_skill, assigned_to, uses_machine. Ephemeral — invalidated on data change. Pure Python, no new infrastructure (pip install networkx).

- **High-value v6.0 use cases: **Impact analysis (machine failure cascades to which jobs and operators — single graph traversal replaces 4 SQL queries). Skill concentration risk detection. Hypothetical job insertion — add temporary node, run connectivity check, remove to undo with no DB writes. Community detection for natural job clusters.

- **Scale limit: **NetworkX graph is in-memory per process. At tenant scale above 10,000 jobs, migrate to Neo4j or Apache AGE. This threshold is well beyond current addressable market.

# 18. Compliance & Regulatory Requirements

- Data stored on servers within India to comply with data localisation norms.

- GDPR-ready architecture: data export and deletion on request for all personal data.

- No sensitive financial data (bank details, PAN, Aadhaar) stored.

- Audit logs retained 3 years (Planned v4.2).

- Passwords hashed using bcrypt cost factor 12 or above.

- JWT tokens in-memory only — no persistent token storage in browser.

# 19. Assumptions & Constraints

- Each job has a fixed start and end date — mid-job rescheduling is a v4.2 feature.

- System does not handle shift-based scheduling within a day — all-day blocks only.

- Machines are single-instance — one physical machine per machine record.

- Optimisation engine does not guarantee global optimality — efficient heuristics within 60-second SLA.

- Internet connectivity required — offline mode is out of scope.

- Python 3.14 is the production runtime. Earlier versions (3.12, 3.11) are not tested. bcrypt is imported directly -- passlib is incompatible with Python 3.12+.

- Token is in-memory only — new browser tabs require re-login.

- Feature flags are currently global (all tenants share same config). Per-tenant flags planned v5.

- Industry configuration is immutable after registration — changing industry_type requires data migration.

- NetworkX graph is in-memory per process — at tenant scale above 10,000 jobs, move to Neo4j or Apache Age.

# 20. Glossary

| **Term** | **Definition** |
| --- | --- |
| ZetaOps Copilot | Product name as of v4.0.3. Formerly MSME Resource Scheduler. |
| MSME | Micro, Small & Medium Enterprise as defined under the MSMED Act, 2006. |
| industry_type | Tenant-level field storing selected industry vertical. Values: printing, manufacturing, fabrication, chemical, field_service. |
| IndustryContext | React context providing industry config, labels, and theme class to all components via useLabels() and useIndustry() hooks. |
| useLabels() | React hook returning industry-specific UI string labels. Used in every page and component. |
| Demo Seeder | Service (demo_seeder.py) that auto-creates industry-specific sample data on tenant registration. |
| Job | A discrete unit of production work with defined start/end dates, resource requirements, and profit value. |
| Tenant | A single organisation with its own isolated data environment within the platform. |
| Availability % | Proportion of a standard working day during which a resource is available for assignment. |
| Feature Flag | Boolean config value in features_config.py controlling whether a feature is visible. |
| Release Ladder | V1 → V2 → V3 → V4 product tier progression controlled entirely by feature flags. |
| Occupancy Map | Internal scheduler data structure tracking which resources are committed on which dates. |
| Knowledge Graph | NetworkX DiGraph built from Postgres data. Enables multi-hop reasoning across entities. |
| Factory GPT | Strategic vision: proactive AI that monitors the resource graph continuously and surfaces insights without user queries. |
| RCPSP | Resource-Constrained Project Scheduling Problem — the class of scheduling problem the engine addresses. |
| Greedy Forward-Scan | The auto-scheduler algorithm: finds earliest gap where all assigned resources are free. |
| Overbooking | Assigning the same machine to two overlapping jobs. Detected and blocked at assignment time. |
| Getting Started | 8-step onboarding checklist. Auto-detects completion via TanStack Query cache. Persisted in localStorage. |
| ZeroZeta | The company behind ZetaOps Copilot. Logo: green zeta symbol + 'Zero' (dark) + 'Zeta' (green). |
| **WhatsApp Copilot** | The AI Copilot delivered over WhatsApp using the Meta Business API. Uses the same tool-calling pipeline as the web Copilot. Introduced in v5.0. |
| **Schema Context** | A static Python dict (app/knowledge_graph/schema_context.py) describing all entity relationships and FK column names. Injected into the LLM system prompt before every AI Copilot query to enable correct multi-hop SQL generation. |
| **Confirmation Flow** | WhatsApp Copilot safety mechanism (v5.6). Write-operations (scheduling, assignment) trigger a confirmation prompt to the user before DB commit. Read-only queries bypass confirmation and execute immediately. |
| **GroqDirectBridge** | The current WhatsApp AI bridge. Single LLM call per message via Groq tool-calling. Used in v5.x. Swapped for SupervisorAgentBridge in v6.0 Factory GPT. |
| **SupervisorAgentBridge** | v6.0 Factory GPT AI bridge. Adds a supervisor LLM layer maintaining continuous graph state, proactive anomaly detection, and routing of complex queries to specialist sub-agents. One-line swap from GroqDirectBridge. |
| **Interakt** | Third-party WhatsApp Business API provider used in ZetaOps production. Connects the Meta app, handles webhook routing, and provides the outbound message API. Planned v5.13 (blocked on v5.12 Meta portfolio link). |
| source field | VARCHAR 20 column on Employee and Machine (migration 023). Values: manual (Day 1 Simple Table), whatsapp (captured via conversation), erp_sync (v7.0 ERP connector). Structural decision that keeps v7.0 a sprint not a rewrite. Never remove. |
| worker_type | VARCHAR 20 column on Employee (migration 023). Values: permanent (salaried staff), contractor (daily-rate labour pool). Enables contractor labour layer in v7.2. |
| Plan A | MSME customer tier. WhatsApp-first, no ERP. 4 active verticals: printing, manufacturing, fabrication, field_service. |
| Plan B | Mid-market customer tier. Has ERP (SAP, Tally, Excel). Python connector feeds same scheduling engine. Chemical / process industry enters here. |
| Day 1 Simple Table | Onboarding screen shown immediately after registration. Collects worker name + primary skill + worker_type, and machine name + machine_type. Nothing else -- no rates, no shift timings on Day 1. Introduced v5.16. |
| Manager Check-in Flow | WhatsApp input channel triggered by APScheduler at 7:00am. Manager reports attendance, machine status, and active orders. Writes to availability engine. Introduced v5.15. |
| Owner Briefing | WhatsApp output channel at 7:15am. Single clean signal generated from manager inputs: who present, who absent, skill gap, order at risk, one suggested action. No questions asked to owner. Introduced v5.15. |
| KPI Baseline | Operational metrics captured during the first 7 calendar days of a tenant lifecycle, used as the comparison base for monthly savings summaries (v6.3). Rows in tenant_kpi_snapshot tagged is_baseline=True. |
| Material Estimator (standalone) | First-class WhatsApp entry point for material quantity queries, backed by tenant historical data plus RAG industry norms (v6.5; was v6.4 prior to April 28, 2026 strategy revision). Read-only intent; bypasses confirmation flow. |
| Compliance Item | A tracked statutory or regulatory obligation with a recurring due date (v6.6; was v6.5 prior to April 28, 2026 strategy revision). Seeded per industry at tenant registration. Owner can deactivate. Reminders fire at T-30, T-7, T-1 days. |
| E-invoice IRP | Government of India Invoice Registration Portal. Mandatory for tenants with turnover above threshold (Rs 5 crore as of 2026, decreasing annually). ZetaOps generates compliant JSON (v6.7; was v6.6 prior to April 28, 2026 strategy revision) but does not submit to IRP directly. |
| **entry_mode** | Tenant-level enum field (migration 027) determining where new tenants land after signup. Values: whatsapp_first (small tenants, lands on WhatsApp QR connect), desktop_first (large tenants, lands on existing dashboard), hybrid (medium tenants, both). Default desktop_first. Drives PhoneTenantMap pre-creation, post-signup screen choice, and welcome message dispatch. Introduced v6.4. See Section 6.28. |
| **size_segment** | Tenant-level enum field (migration 027). Values: small (1-15 people), medium (16-50), large (51+). Captured at signup via team-size question. Drives entry_mode default. Reserved for future analytics, pricing tiers, and feature gating. Introduced v6.4. |
| **Top-Tier Role Group** | The expanded owner-equivalent role group introduced in v6.4: Owner, Factory Manager, Co-Owner. All three share full operational authority (create/edit/cancel work orders, manage crew, run auto-schedule, configure briefings, invite users). Commercial authority (billing, ownership transfer, tenant deletion) remains scoped to Owner only. User.is_top_tier computed property returns True for these three roles. See Section 6.28. |
| **Factory Manager** | Top-tier role introduced in v6.4. Operational head of the floor. Full operational authority equal to Owner. No commercial authority. Typical use: a relative or trusted operator running day-to-day operations while Owner handles customers, money, and billing. Receives daily push briefings. |
| **Co-Owner** | Top-tier role introduced in v6.4 for businesses with two equity partners. Full operational authority equal to Owner. View-only commercial rights (can see billing history, cannot change payment method, cannot delete tenant). Receives daily push briefings. |
| **Daily Push Briefing** | Configurable scheduled WhatsApp message dispatched twice daily to top-tier users (v6.4). Morning briefing (default 7:30am) is forward-looking: today's plan, expected crew, blockers requiring attention. Evening briefing (default 6:30pm) is backward-looking: jobs completed, hours logged, attendance, blockers raised. Per-tenant time and per-user override. Working-days pattern (default Mon-Sat). Opt-in. Idle-floor template used when no jobs to summarise. Reuses v5.10 trigger-endpoint logic for content generation. |
| **PhoneTenantMap pre-creation** | v6.4 behaviour change. For tenants signing up with entry_mode != desktop_first, a PhoneTenantMap row is created at signup time (not on first inbound WhatsApp message), with industry_type read from the new Tenant via the v6.3.0-whatsapp-industry fix. Status starts as invited; flips to active on first WhatsApp interaction or YES reply to welcome message. Eliminates the first-message identification delay. |
| **created_via** | Audit column on Tenant and User tables (migration 027). Values: desktop_signup, whatsapp_first_signup, whatsapp_invite, api, system. Default desktop_signup. Existing rows backfilled to desktop_signup. Distinct from the source field on Employee and Machine (which tracks data origin for ERP sync). |

# 21. ERP Connector Strategy

ZetaOps Copilot is structured as a two-plan product. Plan A (MSME, no ERP) uses WhatsApp as the primary data input channel. Plan B (mid-market, has ERP) uses a Python connector that feeds the same scheduling engine. The same briefing reaches the owner in both plans.

The connector pulls three things only: employee list with skills, active orders, and leaves / machine downtime. A daily sync job runs at 6:30am -- before the manager check-in and owner briefing window.

Supported systems (v7.0): SAP, Tally, Excel export.

source field (migration 023) activates erp_sync value when connector is live.

4 Plan A verticals x mid-market addressable without rebuilding the engine.

Chemical / process industry enters via Plan B (batch-first entry model).

The structural decision that makes v7.0 a sprint: source field on Employee and Machine added in migration 023. Removing it forces a full schema rewrite at v7.0.

# 22. Test Environment

Backend tests use a two-tier strategy: unit tests run against SQLite in-memory (StaticPool); integration tests require real PostgreSQL and are marked with @pytest.mark.integration.

Unit tier (pytest -m "not integration"): test_scheduler_engine.py, test_conflict_detection.py, test_skills.py, test_alembic_migrations.py. SQLite in-memory with StaticPool ensures DDL and DML share the same connection.

Integration tier (pytest -m integration): test_jobs_api.py, test_assignment_service.py. Hit real PostgreSQL. Skipped in CI. Run manually: pytest tests/ -m integration -v

PG-only column types (ARRAY, JSONB) are patched to JSON in conftest.py so SQLite can create tables for unit tests.

Test tenant: what@what.what / qazx1234 / tenant_id=12 / phone: +919876543210. Used for manual WhatsApp pipeline testing in WHATSAPP_MOCK_MODE=True.

Verification gates (must pass before any commit is merged):
npx tsc --noEmit -- zero errors.
python -m py_compile app/ -- zero errors.
pytest tests/ -m "not integration" -v -- zero failures.
alembic heads -- exactly one head (032).

ZetaOps Copilot  |  SRS v6.6  |  Updated through v6.3.17 (HEAD `e74d264`)  |  2026-05-07  |  End of Document

