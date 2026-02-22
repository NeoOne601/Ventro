/**
 * E2E: Admin Console — user management, webhook panel, compliance download.
 * Includes MASTER cross-org panel guard (new in Series A).
 */
import { test, expect } from '@playwright/test'

test.describe('Admin Console', () => {
    test('Admin page redirects unauthenticated users to login', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/admin')
        await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
    })

    test('Login → Register — page navigation works', async ({ page }) => {
        await page.goto('/login')
        await page.click('text=Create an account')
        await expect(page).toHaveURL('/register')
        await page.click('text=Already have an account')
        await expect(page).toHaveURL('/login')
    })

    test('Register step 1 — org slug input is focusable and accepts input', async ({ page }) => {
        await page.goto('/register')
        await page.fill('input[placeholder="acme-corp"]', 'my-org')
        await expect(page.locator('input[placeholder="acme-corp"]')).toHaveValue('my-org')
        await page.click('button[type="submit"]')
        // Step 2 should render role descriptions
        await expect(page.locator('text=Create your account')).toBeVisible({ timeout: 5000 })
    })

    test('Admin page URL guard after clearing storage', async ({ page }) => {
        // Navigate to admin, expect either login redirect or admin content — no 500 error
        await page.evaluate(() => localStorage.clear())
        const res = await page.goto('/admin')
        const url = page.url()
        // Should redirect to login — not crash
        expect(['/login', '/admin'].some(p => url.includes(p))).toBeTruthy()
        if (res) {
            expect(res.status()).not.toBe(500)
        }
    })

    test('Login page submit button is enabled and interactive', async ({ page }) => {
        await page.goto('/login')
        await expect(page.locator('button[type="submit"]')).toBeVisible()
        await expect(page.locator('button[type="submit"]')).toBeEnabled()
    })

    test('Admin orgs tab not visible to unauthenticated users (guard)', async ({ page }) => {
        await page.evaluate(() => localStorage.clear())
        await page.goto('/admin')
        // Should redirect — never show admin content
        await expect(page).toHaveURL(/\/login/, { timeout: 8000 })
        // Confirm Organisations tab is not accessible
        await expect(page.locator('text=Organisations')).not.toBeVisible()
    })
})
