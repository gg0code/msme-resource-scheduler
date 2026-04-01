// src/config/industries/index.ts — v4.0.9
// Central export for all industry configurations.
// Use getIndustryConfig(industryType) to load the right config.

import type { IndustryConfig } from './types'
import printing     from './printing'
import manufacturing from './manufacturing'
import fabrication  from './fabrication'
import chemical     from './chemical'
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

/**
 * Load industry config by industry_type string.
 * Falls back to printing if type is unknown or missing.
 */
export function getIndustryConfig(industryType?: string | null): IndustryConfig {
  return INDUSTRY_CONFIGS[industryType ?? 'printing'] ?? printing
}

export { printing, manufacturing, fabrication, chemical, field_service }
