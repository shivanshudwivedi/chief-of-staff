// README images, captured from the running local product with Playwright.
import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { mkdir } from 'node:fs/promises';
await mkdir('docs/images', { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
await page.goto('http://127.0.0.1:8000');
await page.locator('.focus-tasks button').first().waitFor();
await page.screenshot({ path: 'docs/images/desk.png', fullPage: true });
await page.getByRole('button', {name:'Connectors',exact:true}).click();
await page.screenshot({ path:'docs/images/connectors.png', fullPage:true });
await page.setViewportSize({ width:390, height:844 });
await page.getByLabel('Open navigation').click();
await page.getByRole('button',{name:'My desk',exact:true}).click();
await page.screenshot({ path:'docs/images/mobile.png', fullPage:true });
await browser.close();
