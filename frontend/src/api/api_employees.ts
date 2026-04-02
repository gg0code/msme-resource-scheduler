/**
```typescript
/**
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * FILE PURPOSE
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 
 * This file provides the frontend API client functions for managing employee data in the
 * ZetaOps Copilot workforce scheduling system. It serves as the communication layer between
 * React components and the FastAPI backend's employee endpoints. This file has been part
 * of the system since early versions and exists in the v4-dev production-stable branch.
 * It sits in the frontend API layer, abstracting HTTP requests and providing type-safe
 * access to employee-related backend operations including CRUD operations, job assignments,
 * and CSV import/export functionality.
 * 
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * WHAT THIS FILE DOES — step by step
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 
 * 1. Imports the configured Axios client from './client' which handles authentication,
 *    token management, and base URL configuration for all API calls
 * 2. Imports TypeScript type definitions for Employee and ImportResult from the shared
 *    types file to ensure type safety across all employee operations
 * 3. Defines and exports an employeesApi object containing all employee-related API
 *    functions as methods, providing a clean namespace for employee operations
 * 4. Each method wraps Axios HTTP calls with proper endpoint URLs (all using /api/ prefix
 *    per design principle #4), extracts response data, and returns promises with correct types
 * 5. Handles both JSON requests (for CRUD operations) and FormData requests (for CSV uploads)
 * 6. Provides both data manipulation functions and utility functions like template downloads
 * 
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * KEY FUNCTIONS / CLASSES / COMPONENTS
 * ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 * 
 * Name         : employeesApi.list
 * Type         : function
 * Purpose      : Fetches all employees for the current tenant from the backend. This is used
 *                to populate employee lists in scheduling interfaces, assignment dialogs, and
 *                employee management screens. The backend automatically filters by tenant_id
 *                based on the JWT token, ensuring tenant isolation per design principle #2.
 * Parameters   : none
 * Returns      : Promise<Employee[]> - array of Employee objects containing id, tenant_id,
 *                full_name, base_availability_pct, hourly_rate and other employee fields
 * Calls        : apiClient.get() which uses the Axios instance from './client'
 * DB/API       : GET /api/employees/ - calls backend employee router list endpoint
 * Side effects : none - read-only operation
 * 
 * Name         : employeesApi.get
 * Type         : function
 * Purpose      : Fetches a single employee by ID for viewing detailed information or editing.
 *                Used in employee detail pages, edit forms, and when needing specific employee
 *                data for scheduling calculations. The backend ensures the employee belongs to
 *                the current tenant before returning data.
 * Parameters   : id: number - the unique employee ID to retrieve
 * Returns      : Promise<Employee> - single Employee object with all fields populated
 * Calls        : apiClient.get() with employee ID in the URL path
 * DB/API       : GET /api/employees/{id} - calls backend employee router get endpoint
 * Side effects : none - read-only operation
 * 
 * Name         : employeesApi.create
 * Type         : function
 * Purpose      : Creates a new employee record in the system. Used by employee creation forms
 *                to add new workforce members who can then be assigned to jobs and machines.
 *                The backend automatically sets tenant_id from the authenticated user's token.
 * Parameters   : payload: object - employee data including full_name, base_availability_pct,
 *                hourly_rate and other fields defined in the Employee Pydantic schema
 * Returns      : Promise<Employee> - the newly created Employee object with server-assigned
 *                ID and any computed fields populated by the backend
 * Calls        : apiClient.post() with the employee data as request body
 * DB/API       : POST /api/employees/ - calls backend employee router create endpoint
 * Side effects : creates new employee record in database, affects tenant's employee count
 * 
 * Name         : employeesApi.update
 * Type         : function
 * Purpose      : Updates an existing employee's information such as availability percentage,
 *                hourly rate, or personal details. Used by employee edit forms and bulk update
 *                operations. The backend validates that the employee belongs to the current tenant
 *                before allowing modifications.
 * Parameters   : id: number - the employee ID to update
 *                p: object - partial employee data with fields to update
 * Returns      : Promise<Employee> - the updated Employee object with all current field values
 * Calls        : apiClient.patch() with employee ID and update data
 * DB/API       : PATCH /api/employees/{id} - calls backend employee router update endpoint
 * Side effects : modifies existing employee record, may affect scheduling calculations if
 *                availability or skills are changed
 * 
 * Name         : employeesApi.delete
 * Type         : function
 * Purpose      : Removes an employee from the system permanently. Used when employees leave
 *                the company or are no longer part of the workforce. The backend may enforce
 *                referential integrity rules to prevent deletion of employees with active
 *                job assignments.
 * Parameters   : id: number - the employee
 */

import apiClient from './client'
import type { Employee, ImportResult } from '../types/types_index'

export const employeesApi = {
  list: ()                        => apiClient.get<Employee[]>('/api/employees/').then(r => r.data),
  get:  (id: number)              => apiClient.get<Employee>(`/api/employees/${id}`).then(r => r.data),
  create: (payload: object)       => apiClient.post<Employee>('/api/employees/', payload).then(r => r.data),
  update: (id: number, p: object) => apiClient.patch<Employee>(`/api/employees/${id}`, p).then(r => r.data),
  delete: (id: number)            => apiClient.delete(`/api/employees/${id}`),
  assignments: (id: number)       => apiClient.get(`/api/assignments/employee/${id}`).then(r => r.data),
  importCsv: (file: File)         => {
    const fd = new FormData(); fd.append('file', file)
    return apiClient.post<ImportResult>('/api/import/employees', fd).then(r => r.data)
  },
  downloadTemplate: ()            => apiClient.get('/api/import/template/employees', { responseType: 'blob' }),
}
