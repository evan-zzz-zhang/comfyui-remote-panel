# 项目诊断、修复计划与 TODO

更新日期：2026-08-25
适用版本：`0.1.0` 当前工作区  
文档状态：已完成代码与本机静态/自动化复核，并补充手机/Tailscale 实机结果；移动网络 Direct 已通过启用 IPv6 恢复，真实 ComfyUI/GPU 安全关闭仍待复验。

## 1. 结论摘要

项目主体结构完整，现有自动化检查全部通过，但当前仍处于待验收状态。seed 浏览器契约、wheel 资源、依赖下限、提交/取消 CAS、前端提交锁和预设检查请求治理均已完成代码修复；ComfyUI 安全关闭与新任务提交流程仍待当前生成任务结束后实机复验。

建议先建立 Git 基线，然后按以下顺序修复：

1. seed 字符串数据契约；
2. wheel 与依赖下限；
3. 任务状态 CAS 与前端提交重入；
4. 预设能力检查缓存和并发控制；
5. 事件循环阻塞与资源边界；
6. 前端增量更新、分页和恢复策略；
7. 完整自动化与实机发布验收。

## 2. 已核实现状

### 2.1 仓库与构建

- Git 仓库位于 `main`，但尚无任何提交；所有项目文件都是未跟踪文件。当前没有可比较、可回滚的代码基线。
- `config.toml`、`data/`、`dist/`、虚拟环境、缓存和生成媒体已被 `.gitignore` 排除。
- 当前源码可成功构建 sdist 和 wheel。
- 新构建的 sdist 和 wheel 均包含包内六套预设的 12 个工作流 JSON；wheel 隔离安装后可加载全部预设并启动到 `/healthz`。
- 外部 workflow 目录可覆盖同 ID 的包内预设，也可扩展新的预设。

### 2.2 自动化基线

在当前 Python 3.13 虚拟环境中：

- `python -m pytest -q`：初始基线 `58 passed`，本轮修复后 `72 passed`；
- `python scripts/check_repository.py`：通过；
- `python -m pip check`：通过；
- `python -m build --no-isolation`：sdist 和 wheel 均可构建；
- 当前环境实际使用 `aiohttp 3.14.3`、`setuptools 84.0.0`；最低版本验证已配置为独立 CI job，待推送后由远端执行。

现有测试覆盖了认证、跨域写入、任务创建/取消/重试、seed JSON 契约、Range 响应、文件类型与路径安全、数据库 CAS、提交/取消竞态、设备进程匹配、能力检查请求去重、Metrics single-flight、六个预设构图和 wheel 安装启动。尚未覆盖完整浏览器 DOM 行为、reconcile-vs-WebSocket 交错以及大文件下的事件循环响应性。

### 2.3 本机运行状态

- 机器专用配置可被正常解析，ComfyUI 输入/输出目录、工作流目录和数据目录均存在。
- 设备控制当前已启用。
- SQLite 数据库存在，聚合检查得到 7 个 `succeeded` 任务、15 条已登记文件记录。
- 初始检查时 `127.0.0.1:8188` 与 `127.0.0.1:8190` 均未监听；当前用户正在执行真实视频生成，因此本轮代码修复未重启或操作正在运行的 Remote Panel/ComfyUI。
- Tailscale CLI 已安装；家庭 WiFi direct 正常，移动 5G 已在启用 IPv6 后从 DERP(tok) 恢复 direct，并可查看生成视频。Serve、ACL 和登录身份配置仍待单独核对。

## 3. 问题清单与复核结论

### D-01（P0）64 位 seed 在浏览器中丢精度 — 已修复

后端用 `secrets.randbits(64)` 生成 seed，数据库以文本保存，但读出时转回 Python `int`，随后 API 和 SSE 把它序列化为 JSON number。JavaScript 的安全整数上限只有 `2^53-1`。

本机 Node.js JSON 往返结果：

```text
9007199254740993     -> 9007199254740992
18446744073709551615 -> 18446744073709552000
```

重试草稿把已舍入的值重新放回 seed 表单。因此随机 seed 大概率静默改变；uint64 最大值重试时会越界失败。

涉及位置：`jobs.py` 的随机 seed 与重试草稿、`db.py` 的 `_job_from_row()`、`app.js` 的重试表单赋值。

修复原则：数据库继续使用十进制文本；所有面向浏览器的 API/SSE 契约统一使用十进制字符串；只有构建 ComfyUI prompt 的最后边界才转换为 Python 整数。

处理状态（2026-08-25）：已按上述原则实现并覆盖安全整数边界、uint64 最大值、随机值、列表、详情、SSE 与重试往返测试。

### D-02（P1）wheel 与依赖声明不一致 — 已修复

1. wheel 不包含 `workflows/*.json`，独立 wheel 安装无法凭包内资源加载六个预设。需要明确选择并实现一种发布模型：
   - 推荐：把工作流移入 Python 包资源目录，通过 `importlib.resources` 取得内置默认值，同时允许配置目录覆盖；
   - 备选：明确只发布源码目录部署，不发布 wheel。此方案与当前 CI 构建 wheel 的行为不一致，不推荐。
2. `aiohttp>=3.10` 与代码中的 `aiohttp.ClientWSTimeout` 不兼容；该导出从 3.11 才存在。另有 multipart 内存问题影响 `aiohttp<=3.13.3`，修复版为 3.13.4，因此运行依赖应至少为 `aiohttp>=3.13.4,<4`。参考 [aiohttp 3.10.11 导出](https://raw.githubusercontent.com/aio-libs/aiohttp/v3.10.11/aiohttp/__init__.py)、[aiohttp 3.11.0 导出](https://raw.githubusercontent.com/aio-libs/aiohttp/v3.11.0/aiohttp/__init__.py) 和 [GHSA-3wq7-rqq7-wx6j](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-3wq7-rqq7-wx6j)。
3. 项目使用 SPDX `project.license` 和 `project.license-files`，但 build-system 只要求 `setuptools>=69`；官方文档说明这两项从 77.0.0 才支持。结合之后披露并在 83.0.0 修复的文件名规范化问题，最终安全下限设为 `setuptools>=83`。参考 [setuptools pyproject 配置说明](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html#configuring-setuptools-using-pyproject-toml-files)。

处理状态（2026-08-25）：工作流已进入包资源，依赖下限已收紧，wheel 构建、隔离安装、资源数量与 `/healthz` smoke test 通过，并新增最低依赖 CI 配置。

### D-03（P1）预设检查请求风暴与共享状态竞态 — 已修复

按当前六个 manifest 和 workflow 逐项计算，一轮六预设验证包含 165 个请求：每个预设重复版本检查，并分别请求其节点类型和模型类别。`MetricsService.collect()` 还先请求一次 `/system_stats` 和一次 `/queue`，所以一次完整收集通常是约 167 个请求；首次能力检查还会多一次定向取消探测。

跨预设合并后只有 26 种节点和 4 种模型类别。复用本轮已有的 system stats 后，能力请求可降至约 30 次，首次再加一次取消能力探测。

当前每 30 秒重新检查；并且 metrics 后台循环、`/api/metrics` 和 `/api/events` 在 snapshot 为空时都可能同时调用 `collect()`，没有 single-flight 锁，启动峰值可能成倍增加。

`validate_preset()` 在请求完成前先清空 `preset.model_overrides`，再逐项写回。与此同时任务提交可读取该对象，因而可能观察到空或半成品映射。

修复原则：一次采集内共享节点/模型缓存；为 collect 和能力刷新加 single-flight；局部构造完整验证结果后原子替换；只在启动、离线转在线、配置变化或手动刷新时重验，并保留合理 TTL 作为兜底。

处理状态（2026-08-25）：六预设共享节点/模型结果，复用 system stats，能力检查串行化，collect 使用 single-flight；启动、重连和 5 分钟 TTL 触发重验，状态在整轮结束后原子发布。

### D-04（P1）任务状态和提交按钮存在竞态 — 已修复

- `create()` 在 ComfyUI 提交返回后用无条件 `update_job(... status="queued")`；取消路径也用无条件 `update_job(... status="cancelled")`。若 `submitting` 任务在提交请求尚未返回时被列表接口发现并取消，后到的提交完成可把 `cancelled` 覆盖成 `queued`；提交异常同样可覆盖终态。
- `update_active_job()` 只防止覆盖任意终态，不能表达精确的期望前置状态。
- 前端提交时直接禁用按钮，但任意 metrics/SSE 更新都会调用 `updateSubmitAvailability()`，它没有 `isSubmitting` 条件，可在上传尚未完成时重新启用按钮并造成重复请求。

修复原则：数据库提供带期望状态集合的原子 CAS；提交只允许 `submitting -> queued|failed`；取消只允许活动态转为 `cancelled`，CAS 失败后重新读取并返回当前状态。前端增加 `state.isSubmitting` 和 submit handler 重入保护。

处理状态（2026-08-25）：CAS 与前端提交锁已实现；cancel-vs-submit-success/error、reconcile-vs-WebSocket 的确定性交错测试通过。浏览器中对延迟上传执行双击，并在 pending 期间触发 metrics 更新，服务端仍只收到一次 POST。

### D-05（P1/P2）同步 I/O 会阻塞 aiohttp 事件循环 — 已修复

高风险路径：

- 停止 ComfyUI 主进程的 `psutil.wait_procs()` 仍会同步等待配置的关闭超时，必要时再等待 5 秒；
- 重试可同步复制大量参考素材，按当前单文件上限理论总量可接近 1 GB；
- 图片验证同步解码最高 4000 万像素图片；
- 视频 Range 响应执行同步 `stat/open/seek/read`；
- SQLite 查询在事件循环线程中执行。

停止、复制和图片解码应列 P1。视频分块读取和当前规模下 SQLite 的实际阻塞时长尚无基准，先列 P2 并通过延迟测试决定是否迁移。

修复原则：使用有界专用执行器或 `asyncio.to_thread()` 隔离阻塞操作，避免无限并发；视频优先采用 aiohttp 的文件响应/sendfile 能力并保留单 Range 行为；增加事件循环延迟回归测试。

处理状态（2026-08-25）：进程身份检查/停止等待、素材复制、图片解码和视频 stat/open/seek/read 已移入有界 worker/default bounded executor。200、206、416、suffix Range 和文件名测试保持通过；模拟 150 ms 进程等待时，事件循环 50 ms 响应预算测试通过。SQLite 1k/10k 基准分别为：列表 1.0/1.1 ms、恢复查询 7.9/72.0 ms、聚合 0.9/0.9 ms；仅将超过预算的恢复查询移入 worker。

### D-06（P2）前端重复渲染、重复拉取且没有历史翻页 — 已修复

- 每个 job SSE 事件都会重建当前 Map 中的全部任务卡；采样进度事件频繁时，会反复销毁并创建所有 `<video preload="metadata">`。
- SSE 正常连接时仍固定每 10 秒同时请求 jobs 和 metrics；设备操作还会另开每秒 metrics 轮询。
- 初始 jobs 和 SSE snapshot 最多取 100 条。后端已有 `page/page_size`，但前端没有分页或“加载更多”，更旧任务无法从 UI 播放、重试或删除。

修复原则：按 job id 定位并更新单张卡片；视频进入可视区或用户点击后再加载；只有 SSE 断开时启用带退避的轮询；设备操作复用 SSE 状态或单一临时轮询；接入游标/页码并为新旧数据合并去重。

处理状态（2026-08-25）：job/job_deleted 事件只替换目标卡片；任务列表不再创建带 src 的 video，点击播放才赋值；SSE open 时停止轮询，error 后单一指数退避；设备监控只有一个 timeout 且可清理；历史按 20 条加载更多并去重。浏览器实测 20→25 条、无内嵌 video、SSE 健康 5 秒内 metrics 仅请求一次，375 px 视口无横向溢出。

### D-07（P2）输入、恢复和存储缺少长期边界 — 已修复

- 整体 multipart 上限为 1 GiB，文本字段调用 `part.text()`；prompt 没有独立长度限制，单字段可造成显著内存占用。升级 aiohttp 能修复已知框架漏洞，但不能替代应用级 prompt 限制。
- 所有“成功但未登记输出”的任务每 30 秒永久查询一次 ComfyUI history，没有退避、次数/年龄上限或明确的“输出丢失”状态。
- 系统展示磁盘剩余空间与已登记文件大小，但没有总配额、最低磁盘水位、提交前 admission check，也没有孤儿临时文件/任务目录清理策略。

修复原则：文本字段流式限长；输出恢复记录尝试次数和下次时间，指数退避并最终进入可解释终态；提交前检查保守空间预算；仅清理能够证明属于本应用且不在数据库登记中的文件。

处理状态（2026-08-25）：prompt 限 32 KiB/10000 字符，其他文本字段限 2 KiB/1000 字符；恢复状态写入 schema v3，最多 8 次或 24 小时后进入 `output_missing`，仍可人工重试；默认保留 512 MiB 最低水位和 1 GiB 输出预算，并支持可选总配额；孤儿扫描仅查看专用 UUID 目录和 `.upload` 临时文件，拒绝链接/重解析点，启动时只 dry-run 告警，执行删除必须显式调用且逐文件精确删除。

## 4. 实机验收发现

### D-08（P0）移动网络 Tailscale 无法建立 Direct 连接 — 已解决

现象与实测结果：

- 家庭 WiFi 下为 `direct`，延迟约 9 ms，页面、API、视频和文件传输正常；
- 中国移动 5G 和中国广电 5G 下均无法建立 direct connection；
- 移动网络持续通过 `relay DERP(tok)` 中继；
- DERP 下页面和 API 可用，但视频与大文件传输不可用。

已排除：

- PC 代理或 TUN 的影响；
- Tailscale DNS 的影响（关闭 DNS 后现象不变）；
- 家庭路由器或电脑网络不支持直连。

后续排查：

- 检查手机端 VPN、DNS 和 Android 网络限制；
- 检查手机运营商 NAT 类型；
- 检查移动网络下 Tailscale UDP 打洞条件；
- 必要时评估不改变本机部署安全边界的备用传输方案。

解决记录（2026-08-25）：启用 IPv6 后，5G 移动网络已能建立 Tailscale Direct 连接，原 DERP(tok) 持续中继问题消失。D-08 按本轮实机结果关闭；后续继续在 D-10 中观察长视频和大文件传输稳定性。

### D-09（P0）ComfyUI 生命周期控制安全边界问题 — 已完成

实机曾观察到远程关闭 ComfyUI 时其他用户程序被关闭，包括浏览器无痕窗口退出。原实现会递归枚举并终止 ComfyUI 进程树，且在缺少进程记录时允许按监听端口回退识别目标，关闭范围可能超过 Remote Panel 启动并记录的 ComfyUI 主进程。

安全处理原则：

- 禁止递归终止任何子进程；
- 只允许关闭 Remote Panel 已记录的 ComfyUI 主 PID；
- 必须同时精确匹配 PID、create time、executable 和 command line；
- 任一校验失败即拒绝关闭，不按端口或进程树猜测目标；
- 主进程退出后如有残留子进程，只记录警告，不自动处理；
- 未完成安全修复的部署应关闭远程 stop/restart，只允许启动或本机确认关闭。

处理状态（2026-08-25）：代码安全修复与真实 ComfyUI 实机复验均已完成。实测确认 PID、create time、executable、command line 四项一致后才执行关闭；记录的主 PID 退出、8188 停止监听、进程记录移除、Remote Panel 保持健康，浏览器进程未缺失。自动化测试另覆盖无记录拒绝关闭和残留后代不终止。核心原则是 Remote Panel 可以关闭失败，但不能关闭用户其他程序。

### D-10（P1）移动网络场景下视频传输需要单独优化 — 已完成

原移动网络视频加载失败的主要因素是流量经过 DERP 中继。启用 IPv6、恢复 Direct 后，手机已能查看生成的视频，本轮移动网络视频可用性验收通过。

断点续传、极大文件和低码率预览不再作为当前阻断项；如果后续实测再次出现卡顿或失败，再按具体证据单独立项。

## 5. 修复计划与 TODO

### 实机验收新增项

- [x] **T-008 恢复移动网络 Direct 连接。** 启用 IPv6 后，5G 移动网络已从 `relay DERP(tok)` 恢复为 direct；保留后续稳定性观察记录。
- [x] **T-009 复验 ComfyUI 安全关闭。** 真实环境已确认四重身份匹配、只关闭记录的主 PID、记录清理、服务离线与 Remote Panel 持续健康；浏览器进程未受影响。
- [x] **T-010 验收移动网络视频可用性。** IPv6 Direct 下已能查看生成的视频；高级 Range、断点续传和低码率降级按后续实际问题再立项。

验收：家庭 WiFi 和两种移动网络的链路类型、延迟及媒体行为均有可追溯记录；远程关闭不影响任何未记录进程。

### 阶段 0：建立可回滚基线

- [x] **T-000 建立首个 Git 基线。** 在确认 `git status --ignored` 不含身份、配置、数据库、模型或媒体后提交当前源码。
- [x] **T-001 保存本诊断基线。** 在首个修复 PR/提交中记录测试数、构建结果和已知未完成的实机验收项。

验收：工作树中的业务源码均可追踪，敏感/机器文件仍被忽略，能够通过提交精确比较每批修复。

完成记录（2026-08-24）：49 个候选文件通过忽略规则、敏感模式和重解析点检查；机器配置、数据、虚拟环境和构建产物保持忽略；基线为 58 项测试、仓库安全检查和当前源码构建通过，实机验收项仍保持未完成。

### 阶段 1：发布阻断项

- [x] **T-101 修复 seed 数据契约。** `public_job()`、retry API、jobs API 和 SSE 中的 `seed` 均返回十进制字符串；前端不执行 `Number()` 转换；后端验证 `0 <= seed <= 2^64-1` 后才转整数构图。
- [x] **T-102 增加 seed 契约测试。** 覆盖 `2^53-1`、`2^53+1`、`2^64-1`、随机 seed、jobs 列表、详情、SSE 和 retry 到再次提交的 JSON 往返。
- [x] **T-103 修复 wheel 资源布局。** 将六套 manifest/workflow 作为包资源安装，并使默认配置在 wheel 环境可找到；配置的外部 workflow 目录仍可覆盖或扩展。
- [x] **T-104 收紧依赖下限。** 设置 `aiohttp>=3.13.4,<4`、`setuptools>=83`，重新生成构建产物。
- [x] **T-105 新增发布物 smoke test。** 构建并隔离安装 wheel，验证可加载六个预设、启动到 `/healthz`，并检查 wheel 包含全部 12 个工作流 JSON。
- [x] **T-106 新增最低依赖 CI。** 增加最低版本约束文件和 Python 3.11 CI job，执行测试与无隔离构建。

验收：所有 uint64 seed 浏览器往返完全相等；wheel 独立安装可启动并加载六个预设；最低依赖环境通过；依赖扫描不再报告已知 aiohttp 公告。

### 阶段 2：并发一致性与请求治理

- [x] **T-201 实现数据库状态 CAS。** 提供 `update_job_if_status(job_id, expected, values)` 并返回是否更新/当前记录；提交完成/失败只允许从 `submitting` 转换，取消使用活动状态集合。
- [x] **T-202 增加并发状态测试。** 事件栅栏覆盖 cancel-vs-submit-success/error 和 reconcile-vs-WebSocket；迟到的 reconcile 不能覆盖 WebSocket 已写入的终态。
- [x] **T-203 增加前端提交锁。** `state.isSubmitting` 同时参与按钮可用性计算，handler 开头防重入，所有成功/失败路径可靠释放。
- [x] **T-204 增加前端重入测试。** 本地浏览器延迟 POST 烟雾测试在 Promise pending 期间触发 metrics 降级轮询并双击提交，服务端计数仍为一次。
- [x] **T-205 重构能力检查缓存。** 节点和模型类别跨预设共享请求结果，版本/取消能力检查每轮只做一次。
- [x] **T-206 原子发布预设状态。** 在局部对象构造 diagnostics 和 model overrides，整轮完成后一次替换。
- [x] **T-207 为 metrics/能力刷新加 single-flight。** 并发采集复用同一 Future；预设在启动、离线转在线和 5 分钟 TTL 时刷新，能力检查另有串行锁。
- [x] **T-208 增加请求预算测试。** 验证六预设一轮内 object/model 路径不重复，并发 collect 只执行一次底层采集。

验收：终态在所有交错顺序下不可回退；前端单次操作只提交一次；一次刷新不再进行 165 次重复检查；提交永远看不到半成品 override。

### 阶段 3：事件循环与资源边界

- [x] **T-301 隔离进程停止等待。** psutil 身份检查、枚举、终止和等待在 worker 中执行；仍只向四重匹配的主 PID 发信号。
- [x] **T-302 隔离素材复制和图片解码。** 复制/校验使用并发上限 2 的 worker，失败仍清理临时文件并保持任务一致性。
- [x] **T-303 优化视频发送。** stat/open/seek/read 线程化，保持 200、206、416、suffix Range、下载文件名和路径安全语义。
- [x] **T-304 测量 SQLite 阻塞。** 已提供可重复基准；10k 恢复查询为 72.0 ms，已单独移入 worker，列表和聚合保持同步简洁路径。
- [x] **T-305 限制文本字段。** prompt 和其他字段均按 UTF-8 字节/字符双重流式限长，超限返回 413。
- [x] **T-306 实现恢复退避。** schema v3 记录次数/下次时间/最后错误；指数退避，8 次或 24 小时后进入 `output_missing`，支持人工重试。
- [x] **T-307 增加存储 admission check。** 支持最低剩余空间、保守输出预算和可选总配额，提交解析前返回 507。
- [x] **T-308 设计安全孤儿清理。** 只扫描专用 UUID 目录和上传临时文件，拒绝链接/重解析点，默认 dry-run，执行时逐文件精确删除。
- [x] **T-309 增加响应性/资源测试。** 慢进程退出事件循环预算、最大上传拒绝/清理、线程化视频 Range 和恢复上限均进入回归测试。

验收：长 I/O 期间事件循环保持响应；超长文本被早期拒绝；恢复请求有上限；低磁盘情况下不接受新任务；清理不会越过专用目录。

### 阶段 4：前端效率与完整历史

- [x] **T-401 增量更新任务卡。** job/job_deleted 事件只替换或删除目标 job 卡片，初始加载、刷新和分页才重建有序列表。
- [x] **T-402 视频懒加载。** 列表默认没有 video/src；用户点击播放时才给弹窗播放器设置地址。
- [x] **T-403 SSE 断线降级。** open 停止轮询，error 启动单一 2–30 秒指数退避，恢复 SSE 后立即停止。
- [x] **T-404 合并设备状态监控。** 单一 timeout 在操作结束、150 次上限、页面隐藏或 SSE 可用时清理。
- [x] **T-405 接入历史分页。** 每页 20 条“加载更多”，按 job id 合并去重；轮询刷新最新页时保留已加载历史。
- [ ] **T-406 增加浏览器测试。** 本地真实浏览器已覆盖提交重入、SSE/轮询、视频懒加载、历史分页和 375 px 移动端；仍需把浏览器运行器接入 CI 后关闭此项。

验收：采样事件不会重建全部列表或重载所有视频；在线时只有 SSE；旧任务可完整管理；浏览器关键路径进入 CI。

### 阶段 5：发布验收

- [ ] **T-501 运行全量 CI。** Windows/Linux、Python 3.11/3.13、常规依赖和最低依赖、测试、安全扫描、sdist/wheel 构建、wheel smoke test 全部通过。
- [ ] **T-502 执行四种 FL2VA 输入模式实机验收。** 纯文字、首帧、尾帧、首尾帧分别核对参数、输出、播放、下载、取消和重试 seed。
- [ ] **T-503 执行 Ref2VA 实机验收。** 多图、视频及配对音轨、独立音频的上传、构图、生成、重试和删除。
- [ ] **T-504 执行恢复与压力验收。** 在 submitting/queued/running 重启面板；并发提交/取消；长视频 Range；大素材时 UI/SSE 保持可用。
- [ ] **T-505 执行网络与安全验收。** 确认只监听 loopback、无 Funnel/端口映射、错误/缺失身份头返回 403、跨域写入被拒绝、手机仅经 Tailscale HTTPS 完成全流程。
- [ ] **T-506 执行存储与清理验收。** 低磁盘拒绝、恢复终止、孤儿 dry-run、部分删除失败保留记录，均符合预期。
- [ ] **T-507 更新发布文档并签署结果。** 把日期、环境、ComfyUI 版本、GPU、浏览器、Tailscale 状态和失败证据写入 `docs/ACCEPTANCE.md` 或独立验收记录。

验收：所有自动化门禁和实机清单有可追溯结果，P0/P1 全部关闭后才创建发布版本。

## 6. 建议的提交拆分

为降低回归和审查成本，建议每组保持可独立验证：

1. `fix: preserve uint64 seeds across browser APIs`
2. `build: package workflows and raise dependency floors`
3. `fix: make job transitions compare-and-set`
4. `fix: prevent duplicate browser submissions`
5. `perf: deduplicate preset capability checks`
6. `perf: isolate blocking filesystem and process work`
7. `feat: bound prompt recovery and storage resources`
8. `perf: incrementally render jobs and paginate history`
9. `test: add wheel browser concurrency and soak gates`

## 7. 架构边界

当前不引入云服务器、FastAPI、Redis、PostgreSQL 或公网账号系统。继续保持以下访问与部署路线：

```text
手机
  ↓
Tailscale
  ↓
Remote Panel
  ↓
本机 ComfyUI
```

网络排查和备用传输方案必须优先服从这一架构与安全边界；如未来确需改变，单独评审，不在当前修复中扩展。

## 8. 发布判定

当前判定：**不具备发布条件**。

解除阻断的最低条件：T-101 至 T-106、T-201 至 T-208 全部完成；全量自动化通过；至少完成 T-502、T-503 和 T-505 的真实设备验收。阶段 3 和阶段 4 中涉及资源耗尽、事件循环冻结或旧任务不可管理的项目，若目标是长期无人值守使用，也应在首个公开版本前完成。
