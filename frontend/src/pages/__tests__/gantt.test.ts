// frontend/src/pages/__tests__/gantt.test.ts
// Unit tests for the Gantt bar rendering logic.
// Tests the segment grouping algorithm that produces solid bars + dashed gaps.

import { describe, it, expect } from 'vitest'

// Extracted grouping logic from renderBar — pure function, no React needed
function buildSegmentGroups(scheduledDates: string[]): Array<{ start: Date; end: Date }> {
  if (scheduledDates.length === 0) return []

  const sorted = [...scheduledDates].sort()
  const groups: Array<{ start: Date; end: Date }> = []
  let groupStart = new Date(sorted[0])
  let groupEnd   = new Date(sorted[0])

  for (let i = 1; i < sorted.length; i++) {
    const prev = new Date(sorted[i - 1])
    const curr = new Date(sorted[i])
    const diff = Math.round((curr.getTime() - prev.getTime()) / 86400000)
    if (diff <= 1) {
      groupEnd = curr
    } else {
      groups.push({ start: groupStart, end: groupEnd })
      groupStart = curr
      groupEnd   = curr
    }
  }
  groups.push({ start: groupStart, end: groupEnd })
  return groups
}

describe('buildSegmentGroups', () => {
  it('returns empty for no dates', () => {
    expect(buildSegmentGroups([])).toHaveLength(0)
  })

  it('returns single group for consecutive dates', () => {
    const dates = ['2026-04-13', '2026-04-14', '2026-04-15']
    const groups = buildSegmentGroups(dates)
    expect(groups).toHaveLength(1)
    expect(groups[0].start.toISOString().slice(0, 10)).toBe('2026-04-13')
    expect(groups[0].end.toISOString().slice(0, 10)).toBe('2026-04-15')
  })

  it('returns two groups when there is a gap', () => {
    // Apr 13-15 then Apr 24-28 (gap Apr 16-23 where B ran)
    const dates = [
      '2026-04-13', '2026-04-14', '2026-04-15',
      '2026-04-24', '2026-04-25', '2026-04-26', '2026-04-27', '2026-04-28',
    ]
    const groups = buildSegmentGroups(dates)
    expect(groups).toHaveLength(2)
    expect(groups[0].start.toISOString().slice(0, 10)).toBe('2026-04-13')
    expect(groups[0].end.toISOString().slice(0, 10)).toBe('2026-04-15')
    expect(groups[1].start.toISOString().slice(0, 10)).toBe('2026-04-24')
    expect(groups[1].end.toISOString().slice(0, 10)).toBe('2026-04-28')
  })

  it('handles single date correctly', () => {
    const groups = buildSegmentGroups(['2026-04-16'])
    expect(groups).toHaveLength(1)
    expect(groups[0].start).toEqual(groups[0].end)
  })

  it('handles unsorted input by sorting first', () => {
    const dates = ['2026-04-15', '2026-04-13', '2026-04-14']
    const groups = buildSegmentGroups(dates)
    expect(groups).toHaveLength(1)
    expect(groups[0].start.toISOString().slice(0, 10)).toBe('2026-04-13')
  })

  it('detects gap correctly — hasGaps is true for two groups', () => {
    const dates = ['2026-04-13', '2026-04-15'] // gap on Apr 14
    const groups = buildSegmentGroups(dates)
    expect(groups.length > 1).toBe(true) // hasGaps
  })

  it('no gap for adjacent days (diff=1)', () => {
    const dates = ['2026-04-13', '2026-04-14']
    const groups = buildSegmentGroups(dates)
    expect(groups).toHaveLength(1) // no gap
  })
})
