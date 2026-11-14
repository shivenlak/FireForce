// Smoke test + screenshots. Usage: node e2e/smoke.mjs [baseUrl]   (requires `make dev` running)
import { chromium } from "playwright";

const base = process.argv[2] ?? "http://localhost:5173";
const out = new URL("../../docs/screenshots/", import.meta.url).pathname;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

async function shot(name, url, waitFor) {
  await page.goto(base + url);
  await page.waitForSelector(waitFor, { timeout: 60000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}${name}.png`, fullPage: true });
  console.log("ok", name);
}

await shot("01_calendar_counts", "/?aoi=bbox:-121.5,49,-118.5,52", ".calendar-panel canvas");
await shot("02_calendar_anomaly", "/?aoi=bbox:-121.5,49,-118.5,52&color=anomaly", ".calendar-panel canvas");
await shot("03_country_canada", "/?aoi=country:Canada", ".calendar-panel canvas");
await shot("04_raw_viirs", "/?aoi=bbox:-121.5,49,-118.5,52&mode=viirs", ".calendar-panel canvas");
await shot("05_methods", "/#/methods", ".kpis");
await shot("06_empty", "/?aoi=bbox:-30,-10,-29,-9", ".empty");
const text = await page.goto(base + "/?aoi=bbox:-121.5,49,-118.5,52").then(() => page.waitForSelector(".card")).then(() => page.textContent(".cards"));
console.log("cards:", text.slice(0, 200));
console.log(errors.length ? `ERRORS:\n${errors.join("\n")}` : "no console errors");
await browser.close();
process.exit(errors.length ? 1 : 0);
