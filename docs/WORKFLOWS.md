# Comfy Remote Workflows / Configurator 2.0

**English** | [简体中文](WORKFLOWS.zh-CN.md)

## Design principles

Comfy Remote does not try to reimplement ComfyUI on a phone, and it does not require every workflow to have the same structure.

A workflow should first be tuned and successfully run in local ComfyUI. Comfy Remote then analyzes the capabilities it actually has, maps inputs that are appropriate for remote editing into the mobile UI, and preserves the real API Workflow graph for submission.

Default flow:

```text
ComfyUI workflow
→ Export API Workflow
→ Configurator 2.0 analysis
→ User confirms a few uncertain items
→ Preflight
→ Save / enable
→ Runtime Test
→ Use on the Create page
```

### H3 Ref2VA runtime notes

- The Create page selects the virtual `h3-fl2va-group` entry by default; physical asset IDs remain implementation details.
- When a Ref2VA job uses the source video's aspect, the selected ratio is derived from that video. A value such as `9:16` in a generated prompt is an aspect ratio, not a timestamp.
- Ollama prompt standardization must use the current H3 Prompt Writer plugin. After updating that plugin, restart ComfyUI so its validator changes are loaded.

Core rules:

- `width`, `height`, and `batch_size` are not mandatory.
- A node ID, model, LoRA, or Sampler appearing in JSON does not automatically make it a mobile-facing parameter.
- The workflow graph is not silently rewritten to fit the UI.
- When automatic recognition is uncertain, Configurator surfaces candidates/confidence or asks for explicit mapping instead of pretending certainty.

## Import an API Workflow

1. Confirm the target workflow runs correctly in local ComfyUI.
2. Export JSON using ComfyUI's **API Format**. A normal UI Workflow JSON is a different format.
3. In Comfy Remote, open **Settings → Workflows → Import workflow**.
4. Select the API Workflow JSON.
5. Configurator 2.0 analyzes node schema, connections, input/output semantics, and editable parameters.
6. Confirm or manually map multiple candidates, low-confidence cases, or complex custom nodes.
7. Save and enable the workflow.
8. Run a real Runtime Test.

If the current ComfyUI frontend does not show an API-format export action, you usually need to enable Dev Mode / Developer Mode Options in Settings. Exact wording varies between ComfyUI frontend versions.

## How Configurator 2.0 recognizes a workflow

v0.3 does not rely only on hard-coded node-name rules. It combines three kinds of evidence.

### Schema

Configurator reads current node definitions from ComfyUI `/object_info` to understand:

- input names and types;
- numeric ranges / step values;
- enums;
- whether an input is connected or literal;
- schema exposed by custom nodes.

This lets Configurator distinguish a random string field named `width` from an integer dimension input actually declared by a node schema.

### Graph

Configurator analyzes API Workflow connections to determine things such as:

- where a sampler's positive / negative conditioning comes from;
- how LoadImage / LoadVideo / LoadAudio nodes enter the generation path;
- whether latent size/dimensions are inherited from input media;
- which nodes actually participate in the path to the primary output;
- how SaveImage / SaveVideo / other output nodes relate to the main artifact.

As a result, img2img does not need to be forced into a txt2img structure containing `EmptyLatentImage`.

### Heuristic fallback

When schema and graph evidence still cannot uniquely determine semantics, Configurator may use a conservative heuristic fallback.

Fallback does not mean “guess and treat the result as truth.” Uncertain results should expose confidence and allow the user to confirm or override them with advanced mapping.

## Capabilities and parameters are different things

Configurator 2.0 tries to distinguish:

- **Workflow capability** — what inputs the workflow requires, what it produces, and whether its capability is image/video/audio/mixed.
- **Editable parameter** — which literal inputs are appropriate for a remote user to change.

For example:

- An img2img workflow may require one image but expose no editable `width / height` because dimensions come from the input image.
- A video custom node may manage dimensions and duration internally and expose only a prompt plus reference video.
- A workflow can have no `batch_size` at all and still be completely valid and usable.

The mobile UI should be assembled from actual capabilities and explicitly editable parameters, not the other way around.

## Preflight

Compatibility checks use `PASS / WARN / FAIL` across several layers:

1. **JSON / Structure** — whether the API Workflow parses and has a valid node structure.
2. **Nodes** — whether every `class_type` exists in current ComfyUI `/object_info`.
3. **Inputs** — whether required media slots, connected inputs, and literal inputs are coherent.
4. **Parameters** — whether automatically detected or manually mapped parameters conform to schema.
5. **Outputs** — whether a traceable primary artifact output can be determined.
6. **Runtime** — whether a real submission completes and produces the expected result.

`WARN` means uncertainty, an optional dependency, or a condition worth noticing. `FAIL` means the current configuration has a blocking issue.

A successful import only proves that static analysis completed. It **does not prove that models, VRAM, paths, or third-party nodes will succeed at runtime**.

## Media inputs

A normal custom workflow can detect/declare fixed media slots such as:

- image;
- video;
- audio;
- file.

Required media slots are validated before submission. If a required input is missing, the Create page does not pretend the workflow can run normally.

Bundled H3 Ref2VA workflows use their own schema-v2 media collection capability, but normal workflows are not required to follow that structure.

## Prompts

For common sampling graphs, positive/negative prompts are traced upstream from the sampler's `positive` / `negative` graph connections instead of being inferred only from two identically named CLIPTextEncode nodes or node order.

If a custom node encapsulates a prompt in its own schema, that input can still become editable through schema analysis or advanced mapping.

## Dimensions, aspect ratio, and batch

`width / height / batch_size` are common parameters, not protocol requirements.

They should appear on the Create page only when the workflow actually contains corresponding inputs that can be safely edited.

If size comes from uploaded media, a latent connection, custom-node strategy, or another node, Configurator can treat that as part of the workflow capability without inventing fake width/height fields.

## Advanced · Manual node mapping

Automatic recognition cannot cover every third-party Custom Node.

Advanced mapping lets the user explicitly choose **literal inputs** that should be editable remotely. Inputs connected to other nodes are not arbitrarily disconnected just because advanced mode is open, and model paths, internal file paths, or sensitive fields should not automatically become mobile parameters.

Advanced mapping is a compatibility fallback, not a requirement that ordinary users understand every node ID.

## Outputs and artifacts

Runtime results are registered as artifacts and can include:

- image;
- video;
- audio;
- file.

Single-image jobs use a result layout suited for viewing; multi-output jobs can preserve gallery behavior. Video continues to support browser playback, Range requests, and download.

If a workflow has several possible outputs, Configurator should confirm the primary output instead of treating every output as the main result.

## Runtime Test

The **Test** action really submits the current workflow revision to local ComfyUI and consumes actual GPU/model resources.

Runtime Test catches problems static analysis cannot prove away, such as:

- missing model files;
- custom-node runtime exceptions;
- CUDA OOM;
- output nodes that do not produce the expected artifact;
- local path/node environment differences from the workflow.

Runtime results are tied to a specific workflow revision. Editing or importing a new revision must not inherit an old revision's Runtime PASS.

## Workflow revisions and historical jobs

Every saved change creates a revision. Jobs preserve the workflow ID / revision / snapshot / submitted input values they used, so later edits, renames, or disabling a workflow do not rewrite historical job provenance.

Bundled workflows cannot be deleted but their front-end display names can be changed. Custom workflows can be edited, copied, exported, and deleted.

## Remote Workflow Package

An exported Package ZIP may contain:

- `workflow-api.json`
- `remote-config.json`
- `metadata.json`

A Package should not contain models, LoRAs, real uploaded media, generated outputs, tokens, passwords, API keys, or machine-specific absolute paths.

Import limits unknown files and obvious sensitive fields, but you should still review a package manually before sharing it publicly.

## Seed — simple v0.3 rule

v0.3 does not yet have a separate Seed Policy.

Current behavior:

- blank seed: random;
- explicit number, including `0`: fixed to that number.

Policies such as `randomize / fixed / increment` are planned as a separate future design rather than being encoded through magic seed values.

## The role of H3

The six bundled MiniMax H3 workflows are Bundled / Verified examples that provide a validated video-workflow experience and regression samples.

**H3 is not an architectural requirement for Comfy Remote.**

Without H3 custom nodes or models, those bundled workflows may show `WARN` / unavailable, while ordinary ComfyUI API Workflows should still import, test, and generate normally.

## Report a compatibility problem

Run:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

Then use the GitHub **Workflow Compatibility** Issue template.

Do not publicly upload an unreviewed workflow, real prompts, media, configuration files, databases, or full logs. An API Workflow may itself contain model names, machine paths, or business prompts, so inspect it before sharing.
