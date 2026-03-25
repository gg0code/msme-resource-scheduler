// src/config/industries/manufacturing.ts — v4.0.2
// ShopFloor Resource Planner — Manufacturing industry configuration

import type { IndustryConfig } from './types'

const manufacturing: IndustryConfig = {
  id: 'manufacturing',

  branding: {
    productName:  'ShopFloor Resource Planner',
    shortName:    'ShopFloor',
    primaryColor: 'slate',
    icon:         '⚙️',
    tagline:      'Production order scheduling for manufacturers',
  },

  labels: {
    job:        'Production Order',
    jobs:       'Production Orders',
    employee:   'Operator',
    employees:  'Operators',
    machine:    'Work Center',
    machines:   'Work Centers',
    material:   'BOM Item',
    materials:  'Bill of Materials',
    skill:      'Skill',
    skills:     'Skills',
    step:       'Operation',
    steps:      'Operations',

    jobsPageTitle:      'Production Orders',
    jobsPageSubtitle:   'Shop floor order board',
    employeesPageTitle: 'Operators',
    machinesPageTitle:  'Work Centers',

    jobNamePlaceholder:  'e.g. Shaft Machining, Gear Assembly…',
    jobTypePlaceholder:  'e.g. CNC Part, Assembly, Fabrication…',
    newJobButton:        'New Order',

    kpiJobs:      'Open Orders',
    kpiOrderBook: 'Order Value',
    kpiProfit:    'Est. Margin',
  },
}

export default manufacturing
