AUTO-GENERATED — frontend/src/components/common/
Branch: v4-dev | v5-whatsapp (both)
────────────────────────────────────────────────────────────

FOLDER: frontend/src/components/common/
PURPOSE: Shared data-management UI components used across resource pages.

FILES
  CsvImport.tsx          — Template download + file upload widget for CSV/XLSX
                           bulk import of employees, machines, and skills.
                           Shows result modal with row counts and per-row errors.
                           Branch: both.
  UnavailabilityPanel.tsx — Leave/downtime period management panel. Shown inside
                           expanded rows on Employees and Machines pages.
                           Branch: both.

ARCHITECTURE NOTES
Both components are self-contained — they handle their own API calls and state
internally. CsvImport calls the parent's onSuccess() callback after a successful
import so the parent page can refetch its list. UnavailabilityPanel uses TanStack
Query internally and invalidates its own cache key on add/delete.

GOTCHAS
1. CsvImport posts to /import/{resource} WITHOUT the /api/ prefix. This is the
   one exception to Design Principle 4 in this folder.
2. XLSX import is only available for employees and machines — not skills.
3. UnavailabilityPanel query keys are ['emp-leaves', resourceId] and
   ['mach-downtimes', resourceId]. If you rename these, update any parent
   components that also invalidate these keys.
