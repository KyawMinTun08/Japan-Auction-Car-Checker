import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import process from 'node:process';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');

const LIVE_URL = process.env.JACC_LIVE_URL || 'https://kyawmintun08.github.io/Japan-Auction-Car-Checker/';
const SOURCE_INDEX = process.env.JACC_SOURCE_INDEX || 'index.html';
const ARTIFACT_DIR = process.env.JACC_ARTIFACT_DIR || 'artifacts/live-mobile-ui';
const VIEWPORT = { width: 375, height: 812 };
const INITIAL_DELAY_MS = positiveInteger(process.env.JACC_INITIAL_DELAY_MS, 60_000);
const RETRY_DELAY_MS = positiveInteger(process.env.JACC_RETRY_DELAY_MS, 30_000);
const MAX_ATTEMPTS = positiveInteger(process.env.JACC_MAX_ATTEMPTS, 10);

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function sleep(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function liveUrlWithCacheBust() {
  const url = new URL(LIVE_URL);
  url.searchParams.set('__jacc_live_mobile_check', Date.now().toString());
  return url.toString();
}

async function expectedAppVersion() {
  if (process.env.JACC_EXPECTED_APP_VERSION) return process.env.JACC_EXPECTED_APP_VERSION;

  const source = await fs.readFile(SOURCE_INDEX, 'utf8');
  const match = source.match(/const\s+APP_VERSION\s*=\s*['"]([^'"]+)['"]/);
  if (!match) {
    throw new Error(`APP_VERSION was not found in ${SOURCE_INDEX}`);
  }
  return match[1];
}

function normalizedErrors(errors) {
  return errors.filter(error => !/favicon\.ico/i.test(error.text || ''));
}

async function writeReport(report) {
  await fs.mkdir(ARTIFACT_DIR, { recursive: true });
  await fs.writeFile(
    path.join(ARTIFACT_DIR, 'live-mobile-ui-report.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8'
  );
}

async function inspectAttempt({ attempt, expectedVersion }) {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    serviceWorkers: 'block'
  });
  const page = await context.newPage();
  const errors = [];
  const prefix = `attempt-${String(attempt).padStart(2, '0')}`;

  page.on('console', message => {
    if (message.type() === 'error') {
      errors.push({ type: 'console', text: message.text() });
    }
  });
  page.on('pageerror', error => errors.push({ type: 'pageerror', text: error.message }));
  page.on('requestfailed', request => {
    const failure = request.failure();
    if (failure) errors.push({ type: 'requestfailed', text: `${request.url()} — ${failure.errorText}` });
  });

  try {
    await page.goto(liveUrlWithCacheBust(), { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForTimeout(1_500);

    const layout = await page.evaluate(() => {
      const mobileNavigation = document.querySelector('.mobile-bottom-nav');
      const desktopTabBar = document.querySelector('.tab-bar');
      const loginOverlay = document.getElementById('loginOverlay');
      return {
        appVersion: typeof APP_VERSION === 'string' ? APP_VERSION : null,
        viewport: [window.innerWidth, window.innerHeight],
        mobileNavigationPresent: Boolean(mobileNavigation),
        mobileNavigationDisplay: mobileNavigation ? getComputedStyle(mobileNavigation).display : null,
        desktopTabBarDisplay: desktopTabBar ? getComputedStyle(desktopTabBar).display : null,
        mobileTabs: [...document.querySelectorAll('.mobile-nav-item')].map(item => item.dataset.tab || ''),
        loginOverlayVisible: loginOverlay ? getComputedStyle(loginOverlay).display !== 'none' : null
      };
    });

    await page.screenshot({
      path: path.join(ARTIFACT_DIR, `${prefix}-login-gate.png`),
      fullPage: false
    });

    const navigation = await page.evaluate(() => {
      const chassisButton = document.querySelector('.mobile-nav-item[data-tab="chassis"]');
      chassisButton?.click();
      return {
        activeMobileTab: document.querySelector('.mobile-nav-item.active')?.dataset.tab || null,
        chassisPanelActive: document.getElementById('tab-chassis')?.classList.contains('active') || false,
        locationHash: window.location.hash
      };
    });

    await page.addStyleTag({
      content: '#loginOverlay,#loadingOverlay{display:none !important}'
    });
    await page.waitForTimeout(200);
    await page.screenshot({
      path: path.join(ARTIFACT_DIR, `${prefix}-mobile-ui-probe.png`),
      fullPage: false
    });

    const visibleErrors = normalizedErrors(errors);
    const passed =
      layout.appVersion === expectedVersion &&
      layout.mobileNavigationPresent &&
      layout.mobileNavigationDisplay === 'grid' &&
      layout.desktopTabBarDisplay === 'none' &&
      ['dashboard', 'explorer', 'chassis', 'trends'].every(tab => layout.mobileTabs.includes(tab)) &&
      navigation.activeMobileTab === 'chassis' &&
      navigation.chassisPanelActive &&
      visibleErrors.length === 0;

    return {
      attempt,
      checkedAt: new Date().toISOString(),
      passed,
      layout,
      navigation,
      errors: visibleErrors
    };
  } finally {
    await browser.close();
  }
}

async function main() {
  const expectedVersion = await expectedAppVersion();
  const attempts = [];

  await fs.mkdir(ARTIFACT_DIR, { recursive: true });
  console.log(`Expected APP_VERSION: ${expectedVersion}`);
  console.log(`Live URL: ${LIVE_URL}`);
  console.log(`Mobile viewport: ${VIEWPORT.width}x${VIEWPORT.height}`);

  if (INITIAL_DELAY_MS > 0) {
    console.log(`Waiting ${INITIAL_DELAY_MS}ms for GitHub Pages deployment propagation...`);
    await sleep(INITIAL_DELAY_MS);
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    try {
      const result = await inspectAttempt({ attempt, expectedVersion });
      attempts.push(result);
      await writeReport({
        status: result.passed ? 'passed' : 'retrying',
        expectedVersion,
        liveUrl: LIVE_URL,
        viewport: VIEWPORT,
        attempts
      });

      if (result.passed) {
        console.log(`Live mobile UI verification passed on attempt ${attempt}.`);
        return;
      }

      console.log(`Attempt ${attempt} did not match the expected deployed mobile UI.`);
    } catch (error) {
      const result = {
        attempt,
        checkedAt: new Date().toISOString(),
        passed: false,
        errors: [{ type: 'runner', text: error instanceof Error ? error.message : String(error) }]
      };
      attempts.push(result);
      await writeReport({
        status: 'retrying',
        expectedVersion,
        liveUrl: LIVE_URL,
        viewport: VIEWPORT,
        attempts
      });
      console.log(`Attempt ${attempt} failed to complete: ${result.errors[0].text}`);
    }

    if (attempt < MAX_ATTEMPTS) {
      console.log(`Retrying in ${RETRY_DELAY_MS}ms...`);
      await sleep(RETRY_DELAY_MS);
    }
  }

  await writeReport({
    status: 'failed',
    expectedVersion,
    liveUrl: LIVE_URL,
    viewport: VIEWPORT,
    attempts
  });
  throw new Error(`Live mobile UI did not reach expected version ${expectedVersion} after ${MAX_ATTEMPTS} attempts.`);
}

main().catch(error => {
  console.error(error instanceof Error ? error.stack : String(error));
  process.exitCode = 1;
});
