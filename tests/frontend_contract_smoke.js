const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const STATIC = path.join(ROOT, "src", "comfyui_remote_panel", "static");

class ClassList {
  constructor() { this.values = new Set(); }
  add(value) { this.values.add(value); }
  remove(value) { this.values.delete(value); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) {
    const next = force === undefined ? !this.values.has(value) : Boolean(force);
    if (next) this.values.add(value); else this.values.delete(value);
    return next;
  }
}

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentElement = null;
    this.dataset = {};
    this.classList = new ClassList();
    this.style = { display: "" };
    this.hidden = false;
    this.name = "";
    this.textContent = "";
    this.mutationCount = 0;
  }
  recordMutation() {
    if (this.parentElement) this.parentElement.mutationCount += 1;
    else this.mutationCount += 1;
  }
  append(...nodes) {
    for (const node of nodes) {
      if (!node) continue;
      if (node.parentElement) node.remove();
      node.parentElement = this;
      this.children.push(node);
      this.recordMutation();
    }
  }
  before(node) {
    this.parentElement?.insertBefore(node, this);
  }
  insertBefore(node, reference) {
    if (node.parentElement) node.remove();
    const index = this.children.indexOf(reference);
    node.parentElement = this;
    if (index < 0) this.children.push(node); else this.children.splice(index, 0, node);
    this.recordMutation();
  }
  remove() {
    if (!this.parentElement) return;
    const siblings = this.parentElement.children;
    const index = siblings.indexOf(this);
    if (index >= 0) siblings.splice(index, 1);
    this.parentElement.recordMutation();
    this.parentElement = null;
  }
  matches(selector) {
    return selector.split(",").some(item => {
      const value = item.trim();
      if (value === "label.field") return this.tagName === "LABEL" && this.classList.contains("field");
      if (value === ".v04-resolution") return this.classList.contains("v04-resolution");
      const data = value.match(/^\[data-([\w-]+)(?:="([^"]*)")?\]$/);
      if (data) {
        const key = data[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        return Object.prototype.hasOwnProperty.call(this.dataset, key)
          && (data[2] === undefined || String(this.dataset[key]) === data[2]);
      }
      const named = value.match(/^(select|input)\[name="([^"]+)"\]$/);
      return Boolean(named && this.tagName === named[1].toUpperCase() && this.name === named[2]);
    });
  }
  querySelector(selector) {
    if (selector.includes(" ")) {
      const [parentSelector, childSelector] = selector.split(/\s+/, 2);
      return this.querySelectorAll(parentSelector).map(parent => parent.querySelector(childSelector)).find(Boolean) || null;
    }
    return this.querySelectorAll(selector)[0] || null;
  }
  querySelectorAll(selector) {
    const result = [];
    const visit = node => {
      for (const child of node.children) {
        if (child.matches(selector)) result.push(child);
        visit(child);
      }
    };
    visit(this);
    return result;
  }
  closest(selector) {
    let current = this;
    while (current) {
      if (current.matches(selector)) return current;
      current = current.parentElement;
    }
    return null;
  }
}

class MutationObserverHarness {
  constructor(callback) { this.callback = callback; this.target = null; this.lastDelivered = 0; }
  observe(target) { this.target = target; this.lastDelivered = target.mutationCount; }
  deliver() {
    if (!this.target || this.target.mutationCount === this.lastDelivered) return false;
    this.lastDelivered = this.target.mutationCount;
    this.callback();
    return true;
  }
}

class Document extends Element {
  constructor() {
    super("document");
    this.listeners = {};
    this.selectorOverrides = new Map();
  }
  createElement(tagName) { return new Element(tagName); }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  querySelector(selector) { return this.selectorOverrides.get(selector) || super.querySelector(selector); }
}

class FormDataHarness {
  constructor(entries = {}) { this.entries = new Map(Object.entries(entries)); }
  get(name) { return this.entries.get(name) ?? null; }
  getAll(name) {
    const value = this.entries.get(name);
    return value === undefined ? [] : Array.isArray(value) ? value : [value];
  }
  delete(name) { this.entries.delete(name); }
  set(name, value) { this.entries.set(name, value); }
}

function loadScript(file, extra = {}) {
  const document = extra.document || new Document();
  const window = { localStorage: { getItem: () => null, setItem() {} } };
  const context = {
    window,
    document,
    state: { presets: new Map(), workflowItems: new Map(), metrics: { presets: {} } },
    applyPreset() {},
    uploadForm() {},
    loadPresets() {},
    loadWorkflows() {},
    updateSubmitAvailability() {},
    jobCard() {},
    upsertJob() {},
    selectedPreset() { return null; },
    apiAction() {},
    escapeHtml(value) { return String(value); },
    mediaKindFromRole() { return "image"; },
    Event: class Event {},
    MutationObserver: class MutationObserver {},
    queueMicrotask() {},
    CSS: { escape(value) { return String(value); } },
    ...extra,
  };
  vm.runInNewContext(fs.readFileSync(file, "utf8"), context, { filename: file });
  return { context, document, window };
}

function field(document, role, family, { hidden = false, display = "" } = {}) {
  const label = document.createElement("label");
  label.classList.add("field");
  if (role === "reference-resolution") label.classList.add("v04-resolution");
  label.hidden = hidden;
  label.style.display = display;
  label.textContent = {
    "generation-mode": "生成模式",
    "prompt-backend": "标准化提示词",
    "main-model": "主模型",
    "ollama-model": "Ollama 标准化模型",
    scheduler: "调度器",
    sampler: "采样器",
    steps: "迭代步数",
    "seed-policy": "种子策略",
    "seed-value": "种子",
    "reference-resolution": "参考图分辨率",
  }[role];
  const dataKeys = {
    "generation-mode": family === "ref2va" ? "v048Ref2vaGenerationModeField" : "v042ModeField",
    "prompt-backend": family === "ref2va" ? "v048Ref2vaPromptBackendField" : "v042StandardizerField",
    "main-model": family === "ref2va" ? "v048Ref2vaInferenceProfileField" : "v047InferenceProfileField",
    "ollama-model": family === "ref2va" ? "v048Ref2vaOllamaModelField" : "v045OllamaModelField",
  };
  if (dataKeys[role]) label.dataset[dataKeys[role]] = "true";
  const controls = {
    "generation-mode": ["select", ""],
    "prompt-backend": ["select", ""],
    "main-model": ["select", ""],
    "ollama-model": ["select", ""],
    scheduler: ["select", "scheduler"],
    sampler: ["select", "sampler"],
    steps: ["input", "steps"],
    "seed-value": ["input", "seed"],
    "reference-resolution": ["select", ""],
  };
  if (controls[role]) {
    const [tag, name] = controls[role];
    const control = document.createElement(tag);
    control.name = name;
    label.append(control);
  }
  if (role === "seed-policy") {
    const control = document.createElement("select");
    control.dataset.v04SeedPolicy = "true";
    label.append(control);
  }
  return label;
}

function makeLayout(document, family, backend, seedPolicy) {
  const grid = document.createElement("div");
  const mode = field(document, "generation-mode", family);
  const prompt = field(document, "prompt-backend", family);
  const main = field(document, "main-model", family);
  const ollama = field(document, "ollama-model", family, { hidden: backend !== "ollama" });
  const scheduler = field(document, "scheduler", family);
  const sampler = field(document, "sampler", family);
  const steps = field(document, "steps", family);
  const policy = field(document, "seed-policy", family);
  const seed = field(document, "seed-value", family, { hidden: seedPolicy === "randomize" });
  const resolution = field(document, "reference-resolution", family);
  grid.append(resolution, seed, policy, steps, sampler, scheduler, ollama, main, prompt, mode);
  return grid;
}

function visibleRoles(grid) {
  return grid.children
    .filter(item => !item.hidden && item.style.display !== "none" && !item.classList.contains("hidden"))
    .map(item => item.dataset.h3AdvancedRole);
}

function visibleSignature(grid) {
  return grid.children
    .filter(item => !item.hidden && item.style.display !== "none" && !item.classList.contains("hidden"))
    .map(item => [item.dataset.h3AdvancedRole, item.textContent, item.children.map(child => child.tagName)]);
}

const runtime = loadScript(path.join(STATIC, "configurator_v2_runtime.js"));
const normalize = runtime.window.ComfyRemoteCreationControls.normalize;
assert.equal(typeof normalize, "function");

const cases = [
  ["Raw/randomize", "raw", "randomize"],
  ["Ollama/randomize", "ollama", "randomize"],
  ["Ollama/fixed", "ollama", "fixed"],
  ["Ollama/increment", "ollama", "increment"],
  ["Qwen/randomize", "qwen35", "randomize"],
];
for (const [name, backend, seedPolicy] of cases) {
  const fl = makeLayout(runtime.document, "fl2va", backend, seedPolicy);
  const ref = makeLayout(runtime.document, "ref2va", backend, seedPolicy);
  normalize(fl);
  normalize(ref);
  assert.deepEqual(visibleRoles(fl), visibleRoles(ref), `FL2VA/Ref2VA layout mismatch: ${name}`);
  assert.deepEqual(visibleSignature(fl), visibleSignature(ref), `FL2VA/Ref2VA field contract mismatch: ${name}`);
  assert.equal(new Set(visibleRoles(fl)).size, visibleRoles(fl).length, `duplicate FL2VA roles: ${name}`);
  assert.equal(new Set(visibleRoles(ref)).size, visibleRoles(ref).length, `duplicate Ref2VA roles: ${name}`);
}

const idempotentGrid = makeLayout(runtime.document, "fl2va", "ollama", "fixed");
idempotentGrid.mutationCount = 0;
normalize(idempotentGrid);
assert.ok(idempotentGrid.mutationCount > 0, "first normalization must mutate an unordered DOM");
idempotentGrid.mutationCount = 0;
normalize(idempotentGrid);
assert.equal(idempotentGrid.mutationCount, 0, "second normalization must be mutation-free");

const convergenceGrid = makeLayout(runtime.document, "ref2va", "ollama", "randomize");
convergenceGrid.mutationCount = 0;
let observerCallbacks = 0;
const observer = new MutationObserverHarness(() => {
  observerCallbacks += 1;
  normalize(convergenceGrid);
});
observer.observe(convergenceGrid, { childList: true });
normalize(convergenceGrid);
let deliveries = 0;
while (observer.deliver()) {
  deliveries += 1;
  assert.ok(deliveries <= 2, "advanced-grid observer did not converge");
}
assert.equal(observerCallbacks, 1, "observer should run once for the corrective mutation");
assert.equal(observer.deliver(), false, "converged observer should have no follow-up mutation");

const expected = {
  "Raw/randomize": ["generation-mode", "prompt-backend", "main-model", "scheduler", "sampler", "steps", "seed-policy", "reference-resolution"],
  "Ollama/randomize": ["generation-mode", "prompt-backend", "main-model", "ollama-model", "scheduler", "sampler", "steps", "seed-policy", "reference-resolution"],
  "Ollama/fixed": ["generation-mode", "prompt-backend", "main-model", "ollama-model", "scheduler", "sampler", "steps", "seed-policy", "seed-value", "reference-resolution"],
  "Ollama/increment": ["generation-mode", "prompt-backend", "main-model", "ollama-model", "scheduler", "sampler", "steps", "seed-policy", "seed-value", "reference-resolution"],
  "Qwen/randomize": ["generation-mode", "prompt-backend", "main-model", "scheduler", "sampler", "steps", "seed-policy", "reference-resolution"],
};
for (const [name, backend, seedPolicy] of cases) {
  const grid = makeLayout(runtime.document, "fl2va", backend, seedPolicy);
  normalize(grid);
  assert.deepEqual(visibleRoles(grid), expected[name], `unexpected visible role sequence: ${name}`);
}

const document = new Document();
const mode = new Element("select");
mode.value = "v4step600";
mode.dataset.v048Ref2vaGenerationMode = "true";
const backend = new Element("select");
backend.value = "ollama";
backend.dataset.v048Ref2vaPromptBackend = "true";
const profile = new Element("select");
profile.value = "int8";
profile.dataset.v048Ref2vaInferenceProfile = "true";
const model = new Element("select");
model.value = "gemma4:e4b";
document.selectorOverrides.set("select[data-v048-ref2va-generation-mode]", mode);
document.selectorOverrides.set("select[data-v048-ref2va-prompt-backend]", backend);
document.selectorOverrides.set("select[data-v048-ref2va-inference-profile]", profile);
document.selectorOverrides.set("[data-v048-ref2va-ollama-model-field] [data-v045-ollama-model]", model);

const refControls = loadScript(path.join(STATIC, "v048_ref2va_ui.js"), { document });
const route = refControls.window.ComfyRemoteRef2vaControls.addRouting;
assert.equal(typeof route, "function");

const ollamaForm = new FormDataHarness({
  preset_id: "h3-ref2va-group",
  values_json: JSON.stringify({ seed_policy: "randomize" }),
});
route(ollamaForm);
assert.deepEqual(JSON.parse(ollamaForm.get("values_json")), {
  seed_policy: "randomize",
  generation_mode: "v4step600",
  prompt_backend: "ollama",
  inference_profile: "int8",
  ollama_model: "gemma4:e4b",
});

for (const backendValue of ["raw", "qwen35"]) {
  backend.value = backendValue;
  const form = new FormDataHarness({
    preset_id: "h3-ref2va-group",
    values_json: JSON.stringify({ ollama_model: "stale-model" }),
  });
  route(form);
  const values = JSON.parse(form.get("values_json"));
  assert.equal(values.prompt_backend, backendValue);
  assert.equal(Object.prototype.hasOwnProperty.call(values, "ollama_model"), false);
}

console.log("frontend contract smoke passed");
