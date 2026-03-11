/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    extensions: ['.tsx', '.ts', '.jsx', '.js', '.mjs', '.json']
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
    coverage: {
      provider: 'v8',
      include: ['src/utils/**', 'src/api.ts', 'src/schemas/**'],
      reporter: ['text', 'lcov']
    }
  }
});
