# Remote Workflow 使用说明

## 导入

1. 先在本机 ComfyUI 中确认工作流能够正常运行。
2. 使用 ComfyUI 的“导出（API）”功能保存 JSON。
3. 打开 Remote Panel 的“工作流”页面，填写名称和 ID，选择 API JSON。
4. 勾选允许手机修改的字面输入、固定媒体加载节点以及主要输出。
5. 保存草稿并执行“测试”。测试会真实消耗 GPU，界面会再次确认。
6. 确认结果后启用工作流，它会出现在生成页的工作流选择器中。

连接到其他节点的输入默认不会被暴露。Remote Panel 只修改明确勾选的 node/input，不重新实现 ComfyUI 工作流。节点、输入和模型依赖只检查，不自动安装。

## 修订与历史

再次保存相同 ID 会创建新 revision。每个任务保存提交时的 workflow revision、完整快照和输入值，因此后续编辑或禁用工作流不会改变已有历史和重试依据。内置六个 H3 工作流也通过相同的 schema v2 Registry 登记。

## 媒体与输出

配置器可把现有 LoadImage、LoadVideo、LoadAudio 节点声明为固定上传槽位。内置 H3 Ref2VA 使用 schema v2 的声明式媒体集合，支持动态图片、视频和音频。输出绑定可以指向 SaveImage、SaveVideo 或其他文件输出节点；任务结果通过通用 artifact API 播放或下载，旧 H3 `/video` 地址继续兼容。

## 分享包

“导出”生成 ZIP，包含 `workflow-api.json`、`remote-config.json` 和 `metadata.json`。导入时会拒绝未知文件、绝对本地路径以及 password、token、secret、api_key 等密钥字段。分享包不得包含模型、LoRA、上传素材或生成结果。
