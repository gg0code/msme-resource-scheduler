// src/pages/Skills.tsx
// --------------------
// Skills catalogue page. Lists all skills and allows adding new ones.
// Uses GET /api/skills/ to fetch and POST /api/skills/ to create.

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '../api/client'
import { useLabels } from '../context/IndustryContext'
import { CoachMark } from '../components/onboarding'
import CsvImport from '../components/common/CsvImport'
import { Plus, Loader2, AlertCircle, CheckCircle } from 'lucide-react'
import { SKILLS } from '../api/api_endpoints'

interface Skill {
  id: number
  name: string
  category: string
  is_premium: boolean
  description: string | null
  is_active: boolean
}

export default function Skills() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', category: 'generic', is_premium: false, description: '' })
  const [successMsg, setSuccessMsg] = useState('')
  const labels = useLabels()

  const { data: skills = [], isLoading, isError } = useQuery<Skill[]>({
    queryKey: ['skills'],
    queryFn: () => apiClient.get(SKILLS.list).then(r => r.data),
  })

  const createSkill = useMutation({
    mutationFn: (payload: typeof form) => apiClient.post(SKILLS.list, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['skills'] })
      setForm({ name: '', category: 'generic', is_premium: false, description: '' })
      setShowForm(false)
      setSuccessMsg('Skill created successfully!')
      setTimeout(() => setSuccessMsg(''), 3000)
    },
  })

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-800">{labels.skills} Catalogue</h2>
          <p className="text-sm text-gray-500 mt-0.5">Master list of {labels.skills.toLowerCase()} used by {labels.employees.toLowerCase()}, {labels.machines.toLowerCase()} and {labels.jobs.toLowerCase()}.</p>
        </div>
        <div className="flex items-center gap-2">
          <CsvImport resource="skills" onSuccess={() => qc.invalidateQueries({queryKey:['skills']})}/>
          <CoachMark id="skills-create" title="Define your skills" description="Skills link jobs to the right workers. Generic roles like Helper and Supervisor are pre-loaded." position="bottom" step={1} totalSteps={2}>
            <button
              onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg transition-colors"
            >
              <Plus size={16} /> Add Skill
            </button>
          </CoachMark>
        </div>
      </div>

      {/* Success message */}
      {successMsg && (
        <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-lg px-4 py-2 text-sm">
          <CheckCircle size={16} /> {successMsg}
        </div>
      )}

      {/* Add skill form */}
      {showForm && (
        <div className="bg-white border border-gray-200 rounded-xl p-5 space-y-4">
          <h3 className="font-semibold text-gray-700">New Skill</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Skill Name *</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. CNC Operation"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Category *</label>
              <select
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.category}
                onChange={e => setForm({ ...form, category: e.target.value, is_premium: e.target.value === 'premium' })}
              >
                <option value="generic">Generic</option>
                <option value="premium">Premium</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <input
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Optional description"
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => createSkill.mutate(form)}
              disabled={!form.name || createSkill.isPending}
              className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors"
            >
              {createSkill.isPending ? 'Saving...' : 'Save Skill'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm px-4 py-2 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Skills table */}
      {isLoading && (
        <div className="flex items-center gap-2 text-gray-500 justify-center py-10">
          <Loader2 className="animate-spin" size={18} /> Loading {labels.skills.toLowerCase()}...
        </div>
      )}
      {isError && (
        <div className="flex items-center gap-2 text-red-500 justify-center py-10">
          <AlertCircle size={18} /> Failed to load {labels.skills.toLowerCase()}.
        </div>
      )}
      {!isLoading && !isError && (
        <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr className="text-left text-gray-500">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Description</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {skills.map(skill => (
                <tr key={skill.id} className="border-b border-gray-50 hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-800">{skill.name}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${skill.is_premium ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-600'}`}>
                      {skill.is_premium ? 'Premium' : 'Generic'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{skill.description ?? '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${skill.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
                      {skill.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {skills.length === 0 && (
            <p className="text-center text-gray-400 py-8 text-sm">No {labels.skills.toLowerCase()} found. Add one above.</p>
          )}
        </div>
      )}
    </div>
  )
}
