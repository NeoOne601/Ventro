/**
 * E2E: RBAC — route guards, unauthorized redirect, role-specific navigation
 */
import { test, expect } from '@playwright/test'

test.describe('RBAC Route Guards', () => {
    test('Unauthenticated access to / redirects to /login', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/')
        await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
    })

    test('Unauthenticated access to /admin redirects to /login', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/admin')
        await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
    })

    test('Unauthenticated access to /bulk redirects to /login', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/bulk')
        await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
    })

    test('Login page is accessible without auth', async ({ page }) => {
        await page.goto('/login')
        await expect(page).toHaveURL('/login')
        await expect(page.locator('h1, h2').first()).toBeVisible()
    })

    test('Register page is accessible without auth', async ({ page }) => {
        await page.goto('/register')
        await expect(page).toHaveURL('/register')
        await expect(page.locator('text=Join your workspace')).toBeVisible()
    })

    test('Unauthorized page shows content', async ({ page }) => {
        await page.goto('/unauthorized')
        await expect(page.locator('body')).toBeVisible()
        // Should not be a blank page
        const text = await page.locator('body').innerText()
        expect(text.length).toBeGreaterThan(0)
    })
})
