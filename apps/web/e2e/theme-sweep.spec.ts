import { test, expect } from "@playwright/test";

// UI Phase 1B — whole-app theme sweep. For every route we assert, in DARK mode,
// that no large surface paints a near-white background (relative luminance
// must stay <= 0.8), and that body text keeps a WCAG AA contrast (>= 4.5:1) in
// BOTH themes. Screenshots land in the git-ignored test-results/screenshots dir.

const ROUTES = [
  "/dashboard",
  "/chat",
  "/tasks",
  "/agents",
  "/workflows",
  "/memory",
  "/desktop",
  "/research",
  "/settings",
  "/profile",
  "/alert",
];

type Violation = { sel: string; lum: number; bg: string };
type ContrastFail = { sel: string; ratio: number; color: string; bg: string };

async function auditTheme(
  page: import("@playwright/test").Page,
  dark: boolean,
): Promise<{ surfaces: Violation[]; text: ContrastFail[] }> {
  return page.evaluate((isDark) => {
    const parse = (c: string): [number, number, number, number] => {
      const m = c.match(/rgba?\(([^)]+)\)/);
      if (!m) return [0, 0, 0, 1];
      const p = m[1].split(/[ ,/]+/).map((n) => parseFloat(n));
      return [p[0] || 0, p[1] || 0, p[2] || 0, p[3] === undefined ? 1 : p[3]];
    };
    const chan = (v: number) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    const lum = (r: number, g: number, b: number) =>
      0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
    const contrast = (l1: number, l2: number) =>
      (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    const sel = (el: Element) =>
      el.tagName.toLowerCase() +
      (el.className && typeof el.className === "string"
        ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
        : "");

    // Effective opaque background of an element (walks up to first alpha=1).
    const effectiveBg = (el: Element): [number, number, number] => {
      let node: Element | null = el;
      while (node) {
        const [r, g, b, a] = parse(getComputedStyle(node).backgroundColor);
        if (a === 1 && !(r === 0 && g === 0 && b === 0 && node !== document.body)) {
          // treat fully-opaque non-transparent bg; body fallback below
          if (getComputedStyle(node).backgroundColor !== "rgba(0, 0, 0, 0)") {
            return [r, g, b];
          }
        }
        if (node === document.body) break;
        node = node.parentElement;
      }
      // Fall back to body background.
      const [r, g, b] = parse(getComputedStyle(document.body).backgroundColor);
      return [r, g, b];
    };

    const surfaces: Violation[] = [];
    const text: ContrastFail[] = [];

    for (const el of Array.from(document.querySelectorAll("*"))) {
      const rect = el.getBoundingClientRect();
      if (rect.width < 200 || rect.height < 80) continue; // ignore small chips/icons
      const style = getComputedStyle(el);
      const [r, g, b, a] = parse(style.backgroundColor);
      if (a < 1 || style.backgroundColor === "rgba(0, 0, 0, 0)") continue;
      if (rect.width * rect.height < 20000) continue;
      const l = lum(r, g, b);
      if (isDark && l > 0.8) {
        surfaces.push({ sel: sel(el), lum: Number(l.toFixed(3)), bg: style.backgroundColor });
      }
    }

    // Body text contrast — leaf text nodes with a real font size.
    for (const el of Array.from(document.querySelectorAll("p, span, li, label, h1, h2, h3, a, button, td, th"))) {
      const textContent = (el.textContent || "").trim();
      if (textContent.length < 3) continue;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) continue;
      const style = getComputedStyle(el);
      const fontSize = parseFloat(style.fontSize);
      if (fontSize < 12) continue; // helper micro-labels are excluded from AA body check
      const [tr, tg, tb] = parse(style.color);
      const [br, bg, bb] = effectiveBg(el);
      const ratio = contrast(lum(tr, tg, tb), lum(br, bg, bb));
      if (ratio < 4.5) {
        text.push({
          sel: sel(el) + ` "${textContent.slice(0, 24)}"`,
          ratio: Number(ratio.toFixed(2)),
          color: style.color,
          bg: `rgb(${br},${bg},${bb})`,
        });
      }
    }

    return { surfaces, text };
  }, dark);
}

for (const theme of ["dark", "light"] as const) {
  test.describe(`Theme sweep: ${theme}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.addInitScript((t) => {
        localStorage.setItem("aion-theme", t);
      }, theme);
    });

    for (const route of ROUTES) {
      const name = route.replace(/\//g, "") || "home";
      test(`${route} — surfaces & contrast`, async ({ page }) => {
        await page.goto(route);
        await expect
          .poll(() => page.evaluate(() => document.documentElement.dataset.theme), {
            timeout: 10_000,
          })
          .toBe(theme);
        await page.screenshot({
          path: `test-results/screenshots/${theme}-${name}.png`,
          fullPage: false,
        });

        const result = await auditTheme(page, theme === "dark");
        expect(
          result.surfaces,
          `bright surfaces in ${theme} on ${route}: ${JSON.stringify(result.surfaces)}`,
        ).toHaveLength(0);
        expect(
          result.text,
          `low-contrast body text on ${route} (${theme}): ${JSON.stringify(result.text)}`,
        ).toHaveLength(0);
      });
    }
  });
}
