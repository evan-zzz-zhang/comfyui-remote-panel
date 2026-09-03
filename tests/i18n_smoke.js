const assert = require("node:assert/strict");

let storedLanguage = null;
global.localStorage = {
  getItem: key => key === "comfy-remote-language" ? storedLanguage : null,
  setItem: (key, value) => { if (key === "comfy-remote-language") storedLanguage = value; },
};
Object.defineProperty(globalThis, "navigator", {
  value: { language: "en-US", languages: ["en-US"] },
  configurable: true,
});
global.document = {
  body: null,
  documentElement: { lang: "" },
  addEventListener: () => {},
  querySelector: () => null,
};
global.window = { dispatchEvent: () => {} };
global.CustomEvent = class CustomEvent {
  constructor(name, options) { this.name = name; this.detail = options?.detail; }
};

require("../src/comfyui_remote_panel/static/i18n.js");

const i18n = window.ComfyI18n;
assert.equal(i18n.language, "en");
assert.equal(i18n.t("创作"), "Create");
assert.equal(i18n.t("工作站在线"), "Workstation online");
assert.equal(i18n.t("Graph · 高置信度 · 12.inputs"), "Graph · High confidence · 12.inputs");
assert.equal(i18n.t("1 × 图片"), "1 × Image");
assert.equal(
  i18n.t("运行兼容性测试：请上传参考图后生成。完成结果会写入 Runtime Preflight。"),
  "Compatibility test: upload Reference image and generate. The result will be written to Runtime Preflight."
);
assert.equal(i18n.t("需要上传：参考图、参考视频"), "Required upload: Reference image, Reference video");
assert.equal(i18n.t("已载入原参数，并沿用 1图、2视频"), "Original settings loaded; keeping 1 image, 2 videos");

i18n.setLanguage("zh-CN");
assert.equal(i18n.language, "zh-CN");
assert.equal(document.documentElement.lang, "zh-CN");
assert.equal(storedLanguage, "zh-CN");
assert.equal(i18n.t("创作"), "创作");

i18n.setLanguage("en");
assert.equal(document.documentElement.lang, "en");
assert.equal(storedLanguage, "en");
assert.equal(i18n.t("生成设置"), "Generation settings");
