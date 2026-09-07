const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const STATIC = path.join(ROOT, "src", "comfyui_remote_panel", "static");

class FormDataHarness {
  constructor(entries = {}) { this.entries = new Map(Object.entries(entries)); }
  get(name) { return this.entries.has(name) ? this.entries.get(name) : null; }
  getAll(name) {
    if (!this.entries.has(name)) return [];
    const value = this.entries.get(name);
    return Array.isArray(value) ? value : [value];
  }
  delete(name) { this.entries.delete(name); }
  set(name, value) { this.entries.set(name, value); }
}

function loadAdapter(filename) {
  let adapter = null;
  const context = {
    console, JSON, Map, Set,
    state: { presets: new Map(), workflowItems: new Map(), metrics: { presets: {} } },
    window: null,
    ComfyRemoteH3AdvancedSettings: { registerAdapter() {} },
    H3CreationRuntime: { registerAdapter(value) { adapter = value; } },
  };
  context.window = context;
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, filename), "utf8"), context, { filename });
  assert.ok(adapter, `${filename} must register its adapter`);
  return adapter;
}

function assertSeedContract(filename, entryId) {
  const adapter = loadAdapter(filename);
  const baseUi = {
    promptBackend: "raw", mainModel: "int8", scheduler: "beta", sampler: "euler", steps: "8",
  };

  const random = new FormDataHarness({ preset_id: entryId, seed: "123456", values_json: "{}" });
  adapter.augmentFormData(random, { ...baseUi, seedPolicy: "randomize", seedValue: "" });
  assert.equal(random.get("seed"), null, `${filename}: randomize must remove the previous resolved seed`);
  const randomValues = JSON.parse(random.get("values_json"));
  assert.equal(randomValues.seed_policy, "randomize");
  assert.equal(Object.prototype.hasOwnProperty.call(randomValues, "seed_value"), false);

  const fixed = new FormDataHarness({ preset_id: entryId, seed: "123456", values_json: "{}" });
  adapter.augmentFormData(fixed, { ...baseUi, seedPolicy: "fixed", seedValue: "123456" });
  assert.equal(fixed.get("seed"), "123456", `${filename}: fixed must preserve the explicit seed field`);
  assert.equal(JSON.parse(fixed.get("values_json")).seed_value, "123456");
}

assertSeedContract("h3_fl2va_adapter.js", "h3-fl2va-group");
assertSeedContract("h3_ref2va_adapter.js", "h3-ref2va-group");

let observedRoles = "";
let observedKeepRoles = "";
const runtimeState = {
  presets: new Map([["h3-fl2va-group", { id: "h3-fl2va-group", family: "fl2va" }]]),
  retryRoles: [], retryKeepRoles: [],
};
const runtimeContext = {
  console, Map, Set,
  state: runtimeState,
  applyPreset() {
    observedRoles = runtimeState.retryRoles.join(",");
    observedKeepRoles = runtimeState.retryKeepRoles.join(",");
  },
  loadPresets: async () => {},
  loadWorkflows: async () => {},
  uploadForm: () => {},
  updateSubmitAvailability: () => {},
  selectedPreset: () => runtimeState.presets.get("h3-fl2va-group"),
  document: {
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: () => {},
  },
  window: null,
};
runtimeContext.window = runtimeContext;
vm.runInNewContext(
  fs.readFileSync(path.join(STATIC, "h3_creation_runtime.js"), "utf8"),
  runtimeContext,
  { filename: "h3_creation_runtime.js" },
);
runtimeContext.H3CreationRuntime.registerAdapter({
  family: "fl2va",
  entryId: "h3-fl2va-group",
  physicalPresetIds: new Set(),
  refresh() {},
  isEntry: preset => preset?.family === "fl2va",
  mapPreset: (presetId, overrides) => ({ presetId, overrides }),
});
runtimeContext.applyPreset("h3-fl2va-group", {
  input_roles: ["first", "last"],
  retry_keep_roles: ["first"],
});
assert.equal(observedRoles, "first,last", "Retry roles must be restored before the base render path");
assert.equal(observedKeepRoles, "first", "Retry keep roles must be restored before the base render path");

const css = fs.readFileSync(path.join(STATIC, "ux_refinements.css"), "utf8");
assert.match(css, /#jobs-list button\[data-action="retry"\]:disabled/);
assert.match(css, /content:\s*"载入中…"/);

console.log("H3 retry contract smoke passed");
