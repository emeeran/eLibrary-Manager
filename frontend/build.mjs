// esbuild build script for eLibrary Manager frontend.
//
// Today the app serves classic <script> files directly. This build step is an
// opt-in milestone in the modernization roadmap (see docs/frontend-modernization.md):
// it bundles the new ES-module helpers under static/js/lib/ and, as monoliths are
// refactored into modules, will progressively take over production asset builds.
//
// Usage:
//   node build.mjs           # one-shot production build (minified)
//   node build.mjs --watch   # rebuild on change during development
//
// The legacy monoliths (reader-icecream.js, library.js, tts.js) continue to be
// served as-is until each is migrated; they are intentionally not bundled here.

import { mkdir, rm } from "node:fs/promises";

const watch = process.argv.includes("--watch");
const outDir = "static/js/dist";

// Entry points: new, modular entry bundles. Add entries here as monoliths are split.
const entries = [
  // "lib/index.js",  // <-- uncomment as the first module entry is ready
];

if (entries.length === 0) {
  console.log("[build] No module entries registered yet — nothing to bundle. (see docs/frontend-modernization.md)");
  process.exit(0);
}

// Lazily import esbuild only when there is work to do, so this script can be
// run (and report its no-op state) before `npm install` has been executed.
const { build, context } = await import("esbuild");

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const common = {
  bundle: true,
  format: "iife", // matches the current classic-script consumption model
  target: "es2020",
  logLevel: "info",
  outdir: outDir,
  sourcemap: watch,
  minify: !watch,
};

if (watch) {
  const ctx = await context({ ...common, entryPoints: entries });
  await ctx.watch();
} else {
  await build({ ...common, entryPoints: entries });
}
