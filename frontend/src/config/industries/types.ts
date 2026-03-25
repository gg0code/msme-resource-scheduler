// src/config/industries/types.ts — v4.0.2
//
// TypeScript interfaces for the industry configuration layer.
// Every industry config file must conform to IndustryConfig.
// UI components read labels from here via useLabels() hook.

export interface IndustryLabels {
  // Core entity names (singular)
  job:        string   // Job | Production Order | Work Order | Batch Order | Service Job
  jobs:       string   // Jobs | Production Orders | Work Orders | Batch Orders | Service Jobs
  employee:   string   // Employee | Operator | Fabricator | Operator | Technician
  employees:  string
  machine:    string   // Machine | Work Center | Work Center | Reactor | Vehicle/Tool
  machines:   string
  material:   string   // Raw Material | BOM Item | Material | Batch Input | Part/Consumable
  materials:  string
  skill:      string   // Skill | Skill | Skill | Qualification | Certification
  skills:     string
  step:       string   // Step | Operation | Operation | Phase | Task
  steps:      string

  // Page titles
  jobsPageTitle:       string  // "Jobs" | "Production Orders" | etc
  jobsPageSubtitle:    string  // "Production job board" | "Shop floor orders" | etc
  employeesPageTitle:  string
  machinesPageTitle:   string

  // Form field labels
  jobNamePlaceholder:  string  // "e.g. Corrugated Box Run" | "e.g. Shaft Machining" | etc
  jobTypePlaceholder:  string  // "e.g. Corrugated Box" | "e.g. CNC Part" | etc
  newJobButton:        string  // "New Job" | "New Order" | "New Work Order" | etc

  // KPI labels
  kpiJobs:       string  // "Active Jobs" | "Open Orders" | etc
  kpiOrderBook:  string  // "Order Book" | "Order Value" | etc
  kpiProfit:     string  // "Est. Profit" | "Est. Margin" | etc
}

export interface IndustryBranding {
  productName:   string   // PrintFlow Scheduler | ShopFloor Resource Planner | etc
  shortName:     string   // PrintFlow | ShopFloor | FabFlow | BatchFlow | ServiceFlow
  primaryColor:  string   // Tailwind color name: blue | slate | orange | green | purple
  icon:          string   // emoji icon
  tagline:       string   // one-line description
}

export interface IndustryConfig {
  id:       string          // printing | manufacturing | fabrication | chemical | field_service
  branding: IndustryBranding
  labels:   IndustryLabels
}
