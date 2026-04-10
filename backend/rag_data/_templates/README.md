# RAG Templates — ZetaOps Copilot v6.1

## What is this?
These .txt files are the DEFAULT industry knowledge base for the AI Copilot.
They contain **approximate Indian industry averages** — not real data.

## How it works
When a new tenant registers, their industry template is copied to:
  rag_data/{tenant_id}/

The AI reads from the TENANT folder, not from here.
Tenants can customise their copy without affecting other tenants.

## Data accuracy
These numbers are reasonable starting points for Indian MSMEs (2025).
They are NOT your factory's actual specs. Before going live with a real
tenant, edit their files in rag_data/{tenant_id}/ with actual:
  - Machine throughput and setup times
  - Real supplier paper/material rates
  - Actual job time measurements from your shop floor

## Industries covered
  printing/       — paper rates, machine specs, job times
  manufacturing/  — BOM standards, machine specs, cycle times
  fabrication/    — material grades, weld times, machine specs
  field_service/  — vehicle specs, SLA standards, parts catalog

## Migration path
v6.1 — flat .txt files (current)
v6.3 — pgvector embeddings (folder structure unchanged)
