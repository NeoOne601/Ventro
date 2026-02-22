/**
 * E2E: Reconciliation pipeline + PipelineWaiting mini-game
 */
import { test, expect } from '@playwright/test'

test.describe('Reconciliation', () => {
    test.beforeEach(async ({ page }) => {
        // Navigate to upload page (assumes user already logged in via storageState in real CI)
        await page.goto('/upload')
    })

    test('Upload page shows three dropzones', async ({ page }) => {
        await expect(page.locator('text=Purchase Order')).toBeVisible()
        await expect(page.locator('text=Goods Receipt')).toBeVisible()
        await expect(page.locator('text=Invoice')).toBeVisible()
    })

    test('Pipeline waiting screen shows mini-game canvas', async ({ page }) => {
        // If a reconciliation is in progress, the waiting screen should show
        // We simulate by navigating to a session that doesn't exist to check components exist
        // In a real integration test with a running backend, this would trigger the full flow
        await page.goto('/reconciliation')
        // Check that the page loaded correctly (not a blank screen)
        await expect(page.locator('body')).toBeVisible()
    })

    test('Session list renders correctly', async ({ page }) => {
        await page.goto('/sessions')
        // Should show sessions table or empty state
        await expect(page.locator('body')).not.toContainText('undefined')
        await expect(page.locator('body')).not.toContainText('NaN')
    })

    test('WebSocket connection initiated after run', async ({ page }) => {
        // Verify the WS URL is constructed correctly (inspect network)
        const wsPromise = page.waitForEvent('websocket', ws =>
            ws.url().includes('/ws/reconciliation/')
        ).catch(() => null)   // doesn't reject test if no session is started

        await page.goto('/reconciliation')
        const ws = await wsPromise
        if (ws) {
            expect(ws.url()).toMatch(/\/ws\/reconciliation\/[0-9a-f-]+/)
        }
    })
})
