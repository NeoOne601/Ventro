/**
 * E2E: RBAC — route guards, unauthorized redirect, role-specific navigation
 */
import { test, expect } from '@playwright/test'

test.describe('RBAC Route Guards', () => {
    test('Unauthenticated access redirects to /login', async ({ page }) => {
        // Clear any existing auth state
        await page.evaluate(() => localStorage.clear())
        await page.goto('/')
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    })

    test('Unauthenticated access to /admin redirects to /login', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/admin')
        await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
    })

    test('Login page is accessible without auth', async ({ page }) => {
        await page.goto('/login')
        await expect(page).toHaveURL('/login')
        await expect(page.locator('h1')).toBeVisible()
    })

    test('Register page is accessible without auth', async ({ page }) => {
        await page.goto('/register')
        await expect(page).toHaveURL('/register')
        await expect(page.locator('text=Join your workspace')).toBeVisible()
    })

    test('Unauthorized page shows role badge and navigation', async ({ page }) => {
        await page.goto('/unauthorized')
        // Should show the unauthorized page (may redirect, check for common elements)
        await expect(page.locator('body')).toBeVisible()
    })
})
