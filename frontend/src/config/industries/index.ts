/**
 * frontend/src/config/industries/index.ts — v4.0.9
 * Branch: v4-dev | v5-whatsapp (both)
 *
 * FILE PURPOSE
 * Barrel entry point for the industry configuration system. Imports all five
 * industry config objects, assembles them into a lookup map, and exports
 * getIndustryConfig() — the single function used by IndustryContext to load
 * the correct config for a tenant. Also re-exports all types for consumers
 * that need IndustryConfig, IndustryLabels, or IndustryBranding without
 * importing from types.ts directly.
 *
 * WHAT THIS FILE DOES — step by step
 * 1. Imports IndustryConfig type from ./types.
 * 2. Imports all 5 industry config objects.
 * 3. Builds INDUSTRY_CONFIGS record keyed by industry_type string.
 * 4. Exports getIndustryConfig(industryType?) — returns the matching config
 *    or falls back to printing if type is unknown or null.
 * 5. Re-exports all types and individual configs for direct access.
 *
 * KEY FUNCTIONS
 *
 * Name         : getIndustryConfig
 * Type         : function
 * Purpose      : Returns the IndustryConfig for the given industry_type string.
 *                Falls back to printing if type is null, undefined, or unrecognised.
 * Parameters   : industryType?: string | null
 * Returns      : IndustryConfig
 * Calls        : nothing — pure lookup
 * DB/API       : none
 * Side effects : none
 *
 * WHO CALLS THIS FILE
 * - frontend/src/context/IndustryContext.tsx — calls getIndustryConfig(user.industry_type)
 *
 * INTERN NOTES
 * - To add a new industry: create the config file, import it here, add to INDUSTRY_CONFIGS.
 *   Also add the industry_type to VALID_INDUSTRY_TYPES in backend/app/schemas/auth.py
 *   and to the Tenant.industry_type column comment in models/auth.py.
 * - The fallback to printing is intentional — it prevents a blank/broken UI if a
 *   tenant's industry_type is null or set to an unsupported value.
 * - Design Principle 11: industryType parameter is typed as string | null | undefined
 *   via the optional ?. Never cast it to any.
 */

// src/config/industries/index.ts — v4.0.9
import type { IndustryConfig } from './types'
import printing      from './printing'
import manufacturing from './manufacturing'
import fabrication   from './fabrication'
import chemical      from './chemical'
import field_service from './field_service'

export type { IndustryConfig }
export type { IndustryLabels, IndustryBranding, IndustryColours } from './types'

const INDUSTRY_CONFIGS: Record<string, IndustryConfig> = {
  printing,
  manufacturing,
  fabrication,
  chemical,
  field_service,
}

export function getIndustryConfig(industryType?: string | null): IndustryConfig {
  return INDUSTRY_CONFIGS[industryType ?? 'printing'] ?? printing
}

export { printing, manufacturing, fabrication, chemical, field_service }
