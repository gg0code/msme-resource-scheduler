AUTO-GENERATED — frontend/src/config/industries/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/config/industries/
PURPOSE: Static industry configuration objects — branding, colours, and UI labels
         for each supported industry vertical.

FILES
  types.ts        — TypeScript interfaces: IndustryConfig, IndustryLabels,
                    IndustryBranding, IndustryColours. Branch: both.
  index.ts        — Barrel: imports all 5 configs, exports getIndustryConfig().
                    Branch: both.
  printing.ts     — PrintFlow Scheduler config (default/fallback). Branch: both.
  manufacturing.ts — ShopFloor Resource Planner config. Branch: both.
  fabrication.ts  — Fabrication Capacity Planner config. Branch: both.
  chemical.ts     — Process Batch Scheduler config. Branch: both.
  field_service.ts — Field Service Planner config. Branch: both.

ARCHITECTURE NOTES
Each industry file exports one IndustryConfig object. index.ts assembles them
into a lookup map and exports getIndustryConfig(industryType). IndustryContext.tsx
calls this function with user.industry_type from the JWT. The colour values in each
file back the theme-{id} CSS class in index.css — components never read colour
values directly, they use CSS variables (var(--brand-primary) etc).

DESIGN PRINCIPLES
Principle 11: All files are strictly typed against IndustryConfig. Adding a field
  to IndustryLabels in types.ts will cause tsc errors in all 5 industry files
  until every file is updated.

DEPENDENCIES
  This folder imports from:
    nothing — pure static data files, no external imports except types

  This folder is imported by:
    frontend/src/context/IndustryContext.tsx — getIndustryConfig()
    frontend/src/config/industries/index.ts — all 5 configs

GOTCHAS
1. IndustryLabels has no optional fields. Every field is required in every config.
   If you add a field to types.ts, update all 5 config files before committing.
2. printing is the fallback industry. getIndustryConfig() returns printing for
   any unknown or null industry_type. Keep printing.ts complete and correct.
3. Colours are not applied inline — they back CSS classes. Do not try to apply
   config.colours.primary as an inline style. Use CSS variables instead.
