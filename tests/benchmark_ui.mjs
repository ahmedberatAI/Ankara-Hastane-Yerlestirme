import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({ entryPoints: ["src/Benchmark.tsx"], bundle: true,
  platform: "node", format: "cjs", write: false, external: ["react", "react-dom/server"] });
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports);
const Content = module.exports.BenchmarkContent;
const report = { date: "2026-10-23", planningVersion: "old-health", transitPackageId: "same-network", note: "fixture", cases: [] };
const render = (planningVersion, packageId = "same-network") => renderToStaticMarkup(
  React.createElement(Content, { report, planningVersion, packageId, busy: false, run: () => {} }));
for (const html of [render("new-health"), render(undefined), render("old-health", "other-network")]) {
  assert.match(html, /91 hastane karşılaştırması güncelleniyor/);
  assert.match(html, /ulaşım veya sağlık veri sürümü eşleşmiyor/);
  assert.doesNotMatch(html, /91 hastane yeterli mi/);
}
assert.match(render("old-health"), /91 hastane yeterli mi/);
console.log("Benchmark UI: current health identity required independently of unchanged transit package.");
