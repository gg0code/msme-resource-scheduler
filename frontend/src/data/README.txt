AUTO-GENERATED - frontend/src/data/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/data/
PURPOSE: Static data files - no API calls, no React state, pure data definitions.

FILES
  aiTools.ts   - 50 pre-built AI prompt definitions for the Tools tab in AICopilot.
                 getAITools(labels) returns prompts with industry-specific terminology.
                 AI_TOOL_CATEGORIES defines the 8 category pills.
                 Branch: both.

ARCHITECTURE NOTES
aiTools.ts is the only file here. It is a pure data file - no hooks, no API calls,
no React imports. getAITools() is a plain function that takes IndustryLabels and
returns an array. AICopilot.tsx calls it with useLabels() on every render.

GOTCHAS
1. Always call getAITools(labels) with useLabels() - never with hardcoded labels.
   The AI_TOOLS constant at the bottom uses printing defaults and exists only for
   backward compatibility. New code should use getAITools(labels).
2. Tool ids must be unique (r1-r7, s1-s7 etc). Duplicate ids will cause React key
   warnings in AICopilot.tsx.
