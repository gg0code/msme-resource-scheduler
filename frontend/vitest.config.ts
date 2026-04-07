// frontend/vitest.config.ts
import { defineConfig } from 'vitest/config'
import path from 'path'

export default defineConfig({
  test: {
    // Test environment - jsdom simulates a browser
    environment: 'jsdom',
    // Match test files in __tests__ folders or *.test.ts files
    include: ['src/**/__tests__/**/*.{ts,tsx}', 'src/**/*.{test,spec}.{ts,tsx}'],
    // Setup file run before each test file
    setupFiles: ['src/test-setup.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
