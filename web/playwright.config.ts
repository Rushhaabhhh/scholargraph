import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./tests',testMatch:'**/*.e2e.ts',workers:1,use:{baseURL:process.env.WEB_URL || 'http://127.0.0.1:3000',headless:true,launchOptions:{executablePath:process.env.CHROMIUM_PATH || undefined}}});
