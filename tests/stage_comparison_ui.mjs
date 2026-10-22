import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const built = await build({
  entryPoints: ["src/StageComparison.tsx"],
  bundle: true,
  platform: "node",
  format: "cjs",
  write: false,
  external: ["react", "react-dom/server"],
});
const module = { exports: {} };
new Function("require", "module", "exports", built.outputFiles[0].text)(
  createRequire(import.meta.url),
  module,
  module.exports,
);
const render = (result, component = module.exports.default) =>
  renderToStaticMarkup(React.createElement(component, { result }));
const caption = (result) => render(result, module.exports.CostGapCaption);
const result = {
  hospitalCount: 3,
  gap: 0,
  metrics: { coveredPopulation: 95000, meanMinutes: 8.5 },
  searchScope: { nearestCandidatesPerFootprintClass: 12 },
  capacity: {
    totalBeds: 150,
    totalDoctors: 100,
    annualEquivalentCostTRY: 1027346000,
    finalPlanCostGap: 0.027346,
    priceBase: "Aralık 2024 TL",
    optimalityScope: "restricted_allocation_edges",
    referenceStage: {
      hospitalCount: 2,
      totalBeds: 200,
      totalDoctors: 130,
      coveredPopulation: 95000,
      coveragePercent: 95,
      meanMinutes: 15,
      annualEquivalentCostTRY: 1000000000,
      gap: 0,
      lowerBoundTRY: 1000000000,
      boundScope: "restricted_allocation_edges",
    },
    resourceCleanup: {
      applied: true,
      removedHospitalCount: 1,
      removedBeds: 50,
      removedDoctors: 30,
      annualCostReductionTRY: 12000000,
      allocationsPreserved: true,
      travelPreserved: true,
    },
  },
};
assert.equal(render(null), "");
assert.equal(render({ capacity: {} }), "");
let html = render(result);
assert.match(html, /<td>Hastane<\/td><td>2<\/td><td>3<\/td>/);
assert.match(html, /<td>%0<\/td><td>%2,7<\/td>/);
assert.match(html, /<td>15 dk<\/td><td>8,5 dk<\/td>/);
assert.match(html, /her yapı izi sınıfından en yakın 12 adayla/);
assert.match(html, /atamalar ve yolculuk süreleri korunarak/);
html = caption(result);
assert.match(html, /Son plan maliyet açığı: %2,7 \(daraltılmış aramada\)/);
assert.doesNotMatch(html, /%0/);

const old = structuredClone(result);
delete old.capacity.finalPlanCostGap;
delete old.capacity.referenceStage;
assert.equal(render(old), "");
assert.match(caption(old), /İlk maliyet aşaması açığı: %0/);
old.gap = null;
assert.match(caption(old), /İlk maliyet aşaması açığı: Hesaplanamadı/);
assert.doesNotMatch(caption(old), /%0/);

result.capacity.finalPlanCostGap = null;
assert.match(caption(result), /Son plan maliyet açığı: Hesaplanamadı/);
result.capacity.optimalityScope = "all_candidate_allocation_edges";
result.capacity.referenceStage.boundScope = "all_candidate_allocation_edges";
assert.match(caption(result), /örneklenen tam aday ağında/);
assert.doesNotMatch(caption(result), /daraltılmış/);
assert.match(
  render(result),
  /örneklenen adayların bütün talep bağlantılarını kullanan/,
);
assert.doesNotMatch(render(result), /en yakın 12 adayla/);
result.capacity.resourceCleanup.applied = false;
assert.match(
  render(result),
  /Sayısal tolerans nedeniyle ek kaynak temizliği uygulanmadı/,
);
assert.doesNotMatch(
  render(result),
  /atamalar ve yolculuk süreleri korunarak|hekim kaldırıldı/,
);
delete result.capacity.resourceCleanup.applied;
assert.doesNotMatch(render(result), /atamalar ve yolculuk süreleri korunarak/);
assert.doesNotMatch(
  render(result),
  /Sayısal doğrulama için önceki geçerli plan/,
);
result.capacity.numericalFallback = { selectedIncumbentValidated: true };
assert.match(
  render(result),
  /Sayısal doğrulama için önceki geçerli plan kullanıldı/,
);
result.capacity.numericalFallback = null;
assert.doesNotMatch(
  render(result),
  /Sayısal doğrulama için önceki geçerli plan/,
);
console.log(
  "Stage UI: absent history, initial/final gaps, null bounds, final hospital count and candidate-scope controls passed.",
);
