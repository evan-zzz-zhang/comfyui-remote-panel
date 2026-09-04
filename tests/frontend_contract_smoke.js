const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.resolve(__dirname, "..");
const STATIC = path.join(ROOT, "src", "comfyui_remote_panel", "static");

class ClassList {
  constructor() { this.values = new Set(); }
  add(...values) { values.forEach(value => this.values.add(value)); }
  remove(...values) { values.forEach(value => this.values.delete(value)); }
  contains(value) { return this.values.has(value); }
  toggle(value, force) { const next = force === undefined ? !this.contains(value) : Boolean(force); if (next) this.add(value); else this.remove(value); return next; }
}

function dataKey(name) { return name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()); }
function attrValue(node, name) {
  if (name === "class") return [...node.classList.values].join(" ");
  if (name === "id") return node.id || "";
  if (name === "name") return node.name || "";
  if (name.startsWith("data-")) return node.dataset[dataKey(name.slice(5))];
  return node.attributes[name];
}
function simpleMatch(node, selector) {
  selector = selector.trim();
  if (!selector || selector === "*") return true;
  selector = selector.replace(/^:scope\s*/, "");
  const tag = selector.match(/^^[a-zA-Z][\w-]*/);
  if (tag && node.tagName !== tag[0].toUpperCase()) return false;
  for (const id of selector.matchAll(/#([\w-]+)/g)) if (node.id !== id[1]) return false;
  for (const cls of selector.matchAll(/\.([\w-]+)/g)) if (!node.classList.contains(cls[1])) return false;
  for (const attr of selector.matchAll(/\[([\w-]+)(?:=["']?([^\]"']+)["']?)?\]/g)) {
    const actual = attrValue(node, attr[1]);
    if (actual === undefined) return false;
    if (attr[2] !== undefined && String(actual) !== attr[2]) return false;
  }
  return true;
}
function selectorParts(selector) {
  return selector.trim().replace(/\s*>\s*/g, ">" ).replace(/\s+/g, " ").trim().split(/(?=[> ])|(?<=[> ])/).map(item => item.trim()).filter(Boolean);
}
function complexMatch(node, selector) {
  const parts = selectorParts(selector);
  if (!parts.length || !simpleMatch(node, parts[parts.length - 1])) return false;
  let current = node;
  let combinator = ">";
  for (let index = parts.length - 2; index >= 0; index -= 1) {
    const part = parts[index];
    if (part === ">") { combinator = ">"; continue; }
    if (combinator === ">") {
      current = current.parentElement;
      if (!current || !simpleMatch(current, part)) return false;
    } else {
      current = current.parentElement;
      while (current && !simpleMatch(current, part)) current = current.parentElement;
      if (!current) return false;
    }
    combinator = " ";
  }
  return true;
}

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase(); this.children = []; this.parentElement = null;
    this.dataset = {}; this.attributes = {}; this.classList = new ClassList();
    this.style = { display: "", setProperty: (key, value) => { this.style[key] = value; } };
    this.hidden = false; this.name = ""; this.id = ""; this.type = ""; this.value = "";
    this.checked = false; this.disabled = false; this.placeholder = ""; this.listeners = {};
    this._text = ""; this.mutationCount = 0; this._observers = [];
  }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  set textContent(value) { this._text = String(value ?? ""); this.children = []; }
  get firstElementChild() { return this.children[0] || null; }
  get nextElementSibling() { const siblings = this.parentElement?.children || []; const index = siblings.indexOf(this); return index < 0 ? null : siblings[index + 1] || null; }
  get isConnected() { return Boolean(this.parentElement) && (this.parentElement.isConnected || this.parentElement.tagName === "DOCUMENT"); }
  get options() { return this.children.filter(child => child.tagName === "OPTION"); }
  get selectedOptions() { return this.options.filter(option => option.value === this.value); }
  set innerHTML(html) { this._text = ""; this.children = []; parseHtml(String(html || ""), this); }
  get innerHTML() { return this.children.map(child => child.outerHTML()).join(""); }
  outerHTML() { return `<${this.tagName.toLowerCase()}>${this.textContent}</${this.tagName.toLowerCase()}>`; }
  setAttribute(name, value) { this.attributes[name] = String(value); if (name === "id") this.id = String(value); if (name === "class") String(value).split(/\s+/).filter(Boolean).forEach(item => this.classList.add(item)); if (name === "name") this.name = String(value); if (name === "type") this.type = String(value); if (name.startsWith("data-")) this.dataset[dataKey(name.slice(5))] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? (name === "id" ? this.id : name === "name" ? this.name : null); }
  removeAttribute(name) { delete this.attributes[name]; if (name === "title") delete this.title; }
  recordMutation() {
    this.mutationCount += 1;
    for (const observer of this._observers || []) observer.schedule();
  }
  append(...nodes) { for (const node of nodes) { if (!node) continue; if (node.parentElement) node.remove(); node.parentElement = this; this.children.push(node); this.recordMutation(); } }
  prepend(...nodes) { for (const node of [...nodes].reverse()) { if (node.parentElement) node.remove(); node.parentElement = this; this.children.unshift(node); this.recordMutation(); } }
  replaceChildren(...nodes) { this.children.forEach(node => { node.parentElement = null; }); this.children = []; this.recordMutation(); this.append(...nodes); }
  insertBefore(node, reference) { if (node.parentElement) node.remove(); const index = this.children.indexOf(reference); node.parentElement = this; if (index < 0) this.children.push(node); else this.children.splice(index, 0, node); this.recordMutation(); }
  insertAdjacentElement(position, node) { if (position === "afterend" && this.parentElement) this.parentElement.insertBefore(node, this.nextElementSibling); else this.parentElement?.append(node); }
  remove() { if (!this.parentElement) return; const parent = this.parentElement; const index = parent.children.indexOf(this); if (index >= 0) parent.children.splice(index, 1); this.parentElement = null; parent.recordMutation(); }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatchEvent(event) { event.target ||= this; (this.listeners[event.type] || []).forEach(callback => callback.call(this, event)); if (event.bubbles && this.parentElement) this.parentElement.dispatchEvent(event); return true; }
  matches(selector) { return selector.split(",").some(item => complexMatch(this, item)); }
  querySelectorAll(selector) { const result = []; const selectors = selector.split(",").map(item => item.trim()); const visit = node => { for (const child of node.children) { if (selectors.some(item => complexMatch(child, item))) result.push(child); visit(child); } }; visit(this); return result; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { let current = this; while (current) { if (current.matches(selector)) return current; current = current.parentElement; } return null; }
}
Object.defineProperty(Element.prototype, "className", { configurable: true, get() { return [...this.classList.values].join(" "); }, set(value) { this.classList.values = new Set(String(value || "").split(/\s+/).filter(Boolean)); } });
Object.defineProperty(Element.prototype, "value", { configurable: true, get() { return this._value ?? ""; }, set(value) { this._value = String(value ?? ""); } });

function parseHtml(html, root) {
  const stack = [root];
  const tokenRe = /<\/?([a-z]+)([^>]*)>|([^<]+)/gi;
  let token;
  while ((token = tokenRe.exec(html))) {
    if (token[3]) { stack[stack.length - 1]._text += token[3]; continue; }
    if (token[0][1] === "/") { if (stack.length > 1) stack.pop(); continue; }
    const node = new Element(token[1]);
    for (const attr of token[2].matchAll(/([\w-]+)(?:=["']([^"']*)["'])?/g)) node.setAttribute(attr[1], attr[2] ?? "");
    stack[stack.length - 1].append(node);
    if (!/^(input|option|br|img|path|svg)$/i.test(token[1])) stack.push(node);
  }
}

class Document extends Element {
  constructor() { super("document"); this.listeners = {}; this.head = new Element("head"); this.body = new Element("body"); this.append(this.head, this.body); }
  createElement(tagName) { return new Element(tagName); }
  addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); }
  dispatchEvent(event) { event.target ||= this; (this.listeners[event.type] || []).forEach(callback => callback.call(this, event)); return true; }
}
class MutationObserverHarness {
  constructor(callback) { this.callback = callback; this.targets = []; this.queued = false; }
  observe(target) { this.targets.push(target); target._observers ||= []; target._observers.push(this); }
  disconnect() { for (const target of this.targets) target._observers = (target._observers || []).filter(item => item !== this); this.targets = []; }
  schedule() {
    if (this.queued) return;
    this.queued = true;
    queueMicrotask(() => { this.queued = false; this.callback([]); });
  }
}
class FormDataHarness {
  constructor(entries = {}) { this.entries = new Map(Object.entries(entries)); }
  get(name) { return this.entries.get(name) ?? null; }
  getAll(name) { const value = this.entries.get(name); return value === undefined ? [] : Array.isArray(value) ? value : [value]; }
  delete(name) { this.entries.delete(name); }
  set(name, value) { this.entries.set(name, value); }
}
class EventHarness { constructor(type, options = {}) { this.type = type; this.bubbles = Boolean(options.bubbles); this.target = null; } }

function loadScript(context, name) {
  vm.runInNewContext(fs.readFileSync(path.join(STATIC, name), "utf8"), context, { filename: name });
}
function add(parent, tag, attrs = {}) { const node = new Element(tag); for (const [key, value] of Object.entries(attrs)) { if (key === "class") node.classList.add(...value.split(/\s+/)); else node.setAttribute(key, value); } parent.append(node); return node; }
function createBaseDom() {
  const document = new Document();
  const form = add(document.body, "form", { id: "job-form" });
  const promptField = add(form, "label", { class: "prompt-field" }); add(promptField, "textarea", { name: "prompt" });
  for (const [id, tag, attrs] of [["fl2va-media", "div", {}], ["ref2va-media", "div", {}], ["reference-section", "section", {}], ["generic-parameters", "div", {}], ["basic-settings", "section", {}], ["settings-chips", "span", {}], ["prompt-hint", "span", {}], ["reference-section-hint", "span", {}], ["active-preset-label", "span", {}], ["preset-description", "p", {}]]) add(form, tag, { id, ...attrs });
  const picker = add(form, "button", { id: "workflow-picker-button" }); add(picker, "strong"); add(picker, "small");
  const presetSelect = add(form, "select", { id: "preset-select" });
  const advanced = add(form, "details", { id: "advanced-settings" }); const grid = add(advanced, "div", { class: "advanced-grid" });
  for (const [label, tag, attrs] of [["调度器", "select", { name: "scheduler" }], ["采样器", "select", { name: "sampler" }], ["迭代步数", "input", { name: "steps", type: "number" }], ["种子", "input", { name: "seed" }]]) { const field = add(grid, "label", { class: "field" }); add(field, "span").textContent = label; add(field, tag, attrs); }
  const aspect = add(form, "select", { name: "aspect_ratio" }); add(aspect, "option", { value: "9:16" }).textContent = "9:16"; add(aspect, "option", { id: "reference-aspect-image-option", value: "reference_image" }).textContent = "参考图";
  add(form, "input", { name: "duration_seconds", type: "number" }).value = "5"; add(form, "input", { id: "megapixels-value", name: "megapixels", type: "hidden" }).value = "0.4";
  add(form, "textarea", { id: "prompt-hint" }); add(form, "button", { id: "submit-button" });
  add(document.body, "div", { id: "sheet-body" });
  return { document, form, grid, presetSelect };
}
function h3Preset(family, id, mode, backend) {
  return {
    family, id, name: id, output_kind: "video",
    parameters: { scheduler: { values: { beta: "", simple: "" }, default: "beta" }, sampler: { values: { euler: "", res_multistep: "" }, default: "euler" }, steps: { default: 8, minimum: 1, maximum: 50 } },
    input_bindings: { media: family === "fl2va" ? { type: "frame_pair", roles: { first: "first_frame", last: "last_frame" }, resolution_defaults: { first: { resolution_policy: "auto", target_megapixels: 1 }, last: { resolution_policy: "auto", target_megapixels: 1 } } } : { type: "collection", kinds: { images: { max: 9 } }, resolution_defaults: { image: { resolution_policy: "auto", target_megapixels: 1 } } } },
    generation_modes: family === "fl2va" ? { default: "v4_600step", values: { original: { preset_id: "fl2va_original_raw" }, lightx2v: { preset_id: "fl2va_lightx2v_raw" }, v4_600step: { preset_id: "fl2va_v4step600_raw" } } } : undefined,
    manifest: { model_profile: { main_model: { variants: { fp16_bf16: { available: true } } } } }, mode, backend,
  };
}
function buildContext() {
  const { document, form, grid, presetSelect } = createBaseDom();
  const state = { jobs: new Map(), presets: new Map(), workflowItems: new Map(), metrics: { presets: {} }, retryRoles: [], retryKeepRoles: [], mediaFiles: {}, isSubmitting: false };
  const storage = new Map();
  function baseApplyPreset(presetId, overrides = {}) {
    const preset = state.presets.get(presetId); if (!preset) return;
    presetSelect.value = preset.id;
    const parameters = preset.parameters || {};
    const fill = (name, values, selected) => { const select = form.querySelector(`select[name="${name}"]`); if (!select) return; select.replaceChildren(...values.map(value => { const item = new Element("option"); item.value = value; item.textContent = value; return item; })); select.value = String(selected ?? ""); };
    fill("scheduler", Object.keys(parameters.scheduler?.values || {}), overrides.scheduler ?? parameters.scheduler?.default);
    fill("sampler", Object.keys(parameters.sampler?.values || {}), overrides.sampler ?? parameters.sampler?.default);
    const steps = form.querySelector('input[name="steps"]'); if (steps) steps.value = String(overrides.steps ?? parameters.steps?.default ?? "");
    return preset;
  }
  const context = {
    document, state, form, CSS: { escape: value => String(value) },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, String(value)) },
    setTimeout: callback => callback(), requestAnimationFrame: callback => callback(),
    $: (selector, root = document) => root.querySelector(selector), $$: (selector, root = document) => root.querySelectorAll(selector),
    selectedPreset: () => state.presets.get(presetSelect.value),
    applyPreset: baseApplyPreset, updateSubmitAvailability() {}, uploadForm() {}, loadPresets() {}, loadWorkflows() {}, apiAction() {},
    escapeHtml: value => String(value ?? ""), aspectLabel: value => value, mediaKindFromRole: () => "image", queueMicrotask,
    MutationObserver: MutationObserverHarness, fetch: async () => ({ ok: true, json: async () => ({ items: [] }) }),
    Event: EventHarness, FormData: FormDataHarness,
  };
  context.window = context; context.globalThis = context; return { context, state, grid, presetSelect, storage };
}
function installProductionChain(context) {
  for (const name of ["workflow_ux.js", "h3_advanced_controller.js", "h3_ollama_service.js", "h3_creation_runtime.js", "h3_fl2va_adapter.js", "h3_ref2va_adapter.js"]) loadScript(context, name);
}
function seedProductionState(state) {
  const modes = ["original", "lightx2v", "v4step600"], backends = ["raw", "ollama", "qwen35"];
  for (const family of ["fl2va", "ref2va"]) {
    for (const mode of modes) for (const backend of backends) {
      const id = `${family}_${mode}_${backend}`; const preset = h3Preset(family, id, mode, backend); state.presets.set(id, preset); state.workflowItems.set(id, { id, status: "enabled", manifest: preset.manifest }); state.metrics.presets[id] = { available: true };
    }
  }
  state.presets.set("h3-ref2va-group", h3Preset("ref2va", "h3-ref2va-group", "v4step600", "raw"));
  state.presets.set("h3-fl2va-group", h3Preset("fl2va", "h3-fl2va-group", "v4_600step", "ollama"));
  state.workflowItems.set("h3-ref2va-group", { id: "h3-ref2va-group", status: "enabled" });
}
function roles(grid, visible = true) {
  return grid.children.filter(field => field.dataset.h3AdvancedRole && (!visible || (!field.hidden && field.style.display !== "none" && !field.classList.contains("hidden")))).map(field => field.dataset.h3AdvancedRole);
}
function signature(grid) {
  return grid.children.filter(field => field.dataset.h3AdvancedRole && !field.hidden && field.style.display !== "none" && !field.classList.contains("hidden")).map(field => [field.dataset.h3AdvancedRole, field.querySelector(":scope > span")?.textContent, field.querySelector("select,input")?.tagName]);
}
function contract(grid) {
  return grid.children.filter(field => field.dataset.h3AdvancedRole).map(field => [
    field.dataset.h3AdvancedRole,
    field.querySelector(":scope > span")?.textContent,
    field.querySelector("select,input")?.tagName,
    field.hidden,
    field.style.display,
    field.classList.contains("hidden"),
  ]);
}
async function renderCase(env, family, backend, seedPolicy) {
  const { context, state, grid, presetSelect } = env;
  presetSelect.value = family === "fl2va" ? "h3-fl2va-group" : "h3-ref2va-group";
  const mode = family === "fl2va" ? "v4_600step" : "v4step600";
  context.applyPreset(presetSelect.value, { generation_mode: mode, prompt_backend: backend, seed_policy: seedPolicy, seed_value: seedPolicy === "randomize" ? "" : "17", scheduler: "beta", sampler: "euler", steps: "8" });
  await new Promise(resolve => queueMicrotask(resolve));
  assert.equal(new Set(roles(grid, false)).size, roles(grid, false).length, `${family} duplicate roles: ${backend}/${seedPolicy}`);
  const expected = ["generation-mode", "prompt-backend", "main-model"];
  if (backend === "ollama") expected.push("ollama-model");
  expected.push("scheduler", "sampler", "steps", "seed-policy");
  if (seedPolicy !== "randomize") expected.push("seed-value");
  expected.push("reference-resolution");
  assert.deepEqual(roles(grid), expected, `${family} visible sequence: ${backend}/${seedPolicy}`);
  const expectedLabels = { "generation-mode": "生成模式", "prompt-backend": "标准化提示词", "main-model": "主模型", "ollama-model": "Ollama 标准化模型", scheduler: "调度器", sampler: "采样器", steps: "迭代步数", "seed-policy": "种子策略", "seed-value": "种子", "reference-resolution": "参考图分辨率" };
  assert.deepEqual(signature(grid).map(item => [item[0], item[1]]), expected.map(role => [role, expectedLabels[role]]), `${family} labels: ${backend}/${seedPolicy}`);
  assert.equal(grid.querySelector('[data-h3-advanced-role="ollama-model"]').hidden, backend !== "ollama", `${family} Ollama visibility: ${backend}`);
  assert.equal(grid.querySelector('[data-h3-advanced-role="seed-value"]').hidden, seedPolicy === "randomize", `${family} seed visibility: ${seedPolicy}`);
  return { roles: roles(grid), signature: signature(grid), contract: contract(grid), state: context.ComfyRemoteH3AdvancedSettings.getState() };
}

(async () => {
  const env = buildContext(); installProductionChain(env.context); seedProductionState(env.state);
  const lifecycle = buildContext(); installProductionChain(lifecycle.context); seedProductionState(lifecycle.state);
  lifecycle.presetSelect.value = "h3-ref2va-group";
  lifecycle.context.applyPreset("h3-ref2va-group", { generation_mode: "v4step600", prompt_backend: "ollama", seed_policy: "randomize" });
  await new Promise(resolve => queueMicrotask(resolve));
  assert.ok(lifecycle.grid.mutationCount > 0, "first H3 normalization must repair the base order");
  lifecycle.grid.mutationCount = 0;
  lifecycle.context.ComfyRemoteH3AdvancedSettings.normalize(lifecycle.grid);
  assert.equal(lifecycle.grid.mutationCount, 0, "golden H3 order must be idempotent");
  let observerCallbacks = 0;
  const convergenceObserver = new lifecycle.context.MutationObserver(() => {
    observerCallbacks += 1;
    lifecycle.context.ComfyRemoteH3AdvancedSettings.normalize(lifecycle.grid);
  });
  convergenceObserver.observe(lifecycle.grid, { childList: true });
  const managed = lifecycle.grid.children.filter(field => field.dataset.h3AdvancedRole);
  lifecycle.grid.insertBefore(managed[managed.length - 1], managed[0]);
  await new Promise(resolve => queueMicrotask(resolve));
  await new Promise(resolve => queueMicrotask(resolve));
  const settledMutations = lifecycle.grid.mutationCount;
  await new Promise(resolve => queueMicrotask(resolve));
  assert.ok(observerCallbacks >= 1, "observer convergence test must execute the callback");
  assert.equal(lifecycle.grid.mutationCount, settledMutations, "observer callback must converge without churn");
  convergenceObserver.disconnect();
  const cases = [["raw", "randomize"], ["ollama", "randomize"], ["ollama", "fixed"], ["ollama", "increment"], ["qwen35", "randomize"]];
  for (const [backend, seedPolicy] of cases) {
    const fl = await renderCase(env, "fl2va", backend, seedPolicy);
    const ref = await renderCase(env, "ref2va", backend, seedPolicy);
    assert.deepEqual(fl.roles, ref.roles, `FL2VA/Ref2VA role mismatch: ${backend}/${seedPolicy}`);
    assert.deepEqual(fl.signature, ref.signature, `FL2VA/Ref2VA signature mismatch: ${backend}/${seedPolicy}`);
    assert.deepEqual(fl.contract, ref.contract, `FL2VA/Ref2VA hidden/display contract mismatch: ${backend}/${seedPolicy}`);
  }
  const grid = env.grid; const before = grid.mutationCount; env.context.ComfyRemoteH3AdvancedSettings.sync(env.state.presets.get("h3-ref2va-group"), { generation_mode: "v4step600", prompt_backend: "ollama", scheduler: "beta", sampler: "euler", steps: "8", seed_policy: "fixed", seed_value: "17" }); assert.equal(grid.mutationCount, before, "second identical render must be structurally mutation-free");
  const retry = env.context.ComfyRemoteH3AdvancedSettings;
  retry.sync(env.state.presets.get("h3-ref2va-group"), { generation_mode: "original", prompt_backend: "ollama", inference_profile: "fp16_bf16", ollama_model: "retry-model", scheduler: "simple", sampler: "res_multistep", steps: "20", seed_policy: "fixed", seed_value: "42", media_resolution: { image: { policy: "auto", target_megapixels: 1.5 } } });
  const retryState = retry.getState(); assert.equal(JSON.stringify(retryState), JSON.stringify({ family: "ref2va", generationMode: "original", promptBackend: "ollama", mainModel: "fp16_bf16", ollamaModel: "retry-model", scheduler: "simple", sampler: "res_multistep", steps: "20", seedPolicy: "fixed", seedValue: "42", referenceResolution: { image: { policy: "auto", target_megapixels: 1.5 } } }), "retry snapshot must win over live/local defaults");
  await new Promise(resolve => queueMicrotask(resolve)); assert.equal(retry.getState().seedValue, "42", "microtask delivery must not overwrite retry state");
  for (const family of ["fl2va", "ref2va"]) {
    const preset = env.state.presets.get(family === "fl2va" ? "h3-fl2va-group" : "h3-ref2va-group");
    const originalMode = family === "fl2va" ? "original" : "original";
    const v4Mode = family === "fl2va" ? "v4_600step" : "v4step600";
    env.context.applyPreset(preset.id, { generation_mode: originalMode, prompt_backend: "raw", inference_profile: "int8", scheduler: "simple", sampler: "res_multistep", steps: "20", seed_policy: "randomize" });
    const originalContract = contract(grid);
    const originalState = env.context.ComfyRemoteH3AdvancedSettings.getState();
    env.context.applyPreset(preset.id, { generation_mode: v4Mode, prompt_backend: "raw" });
    env.context.applyPreset(preset.id, { generation_mode: originalMode, prompt_backend: "raw" });
    assert.deepEqual(contract(grid), originalContract, `${family} mode round-trip contract`);
    assert.deepEqual(env.context.ComfyRemoteH3AdvancedSettings.getState(), originalState, `${family} mode round-trip state`);
  }
  for (const [backend, seedPolicy] of cases) { await renderCase(env, "fl2va", backend, seedPolicy); await renderCase(env, "ref2va", backend, seedPolicy); }
  for (const backend of ["raw", "ollama", "qwen35"]) {
    env.presetSelect.value = "h3-ref2va-group";
    env.context.applyPreset("h3-ref2va-group", { generation_mode: "v4step600", prompt_backend: backend, inference_profile: "int8", seed_policy: "randomize" });
    const formData = new env.context.FormData({ preset_id: "h3-ref2va-group", values_json: JSON.stringify({ existing: true }) });
    env.context.uploadForm("/api/jobs", formData);
    const values = JSON.parse(formData.get("values_json"));
    assert.equal(values.prompt_backend, backend, `Ref2VA routing backend: ${backend}`);
    assert.equal(values.inference_profile, "int8");
    assert.equal(values.generation_mode, "v4step600");
    assert.equal(values.existing, true);
    assert.equal(Object.prototype.hasOwnProperty.call(values, "ollama_model"), backend === "ollama");
    assert.equal(formData.getAll("ollama_model").length, 0, "ollama routing must stay in values_json");
  }
  console.log("frontend production-flow contract smoke passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
