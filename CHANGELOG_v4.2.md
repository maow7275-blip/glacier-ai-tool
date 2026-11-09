# Glacier AI v4.2

- 新增 `gpt-image-2.6`、`gpt-image-2.6-flare`、`gpt-image-2.6-sunburst` 图片模型。
- 图片统一使用 hfsyapi 当前异步图片接口：`POST /v1/image/create` 提交，`GET /v1/image/query/{id}` 查询。
- 同步图片尺寸、比例、参考图数量、透明背景和 5000 字提示词限制，修正 3:1 输出尺寸。
- 图片模型下拉改为系列分组子菜单；`gpt-image-2pro` 和 `gpt-image-2pro-4k` 并入 GPT Image 2 系列。
- 新增 `muse-video`，支持图片、视频、音频参考，比例 9:16 / 16:9，时长 4-30 秒。
- 视频查询兼容当前接口的 `result_url` 和 `fail_reason` 字段，素材引用统一为 `@image1`、`@video1`、`@audio1`。
- 修复视频参考图预览错误，并补充图片和视频模型切换、异步任务、失败重试的测试。
- 修正图片和视频任务查询的 HTTP 方法；视频使用 `GET /v1/video/query?id={id}`，查询遇到 401/403/404/405 等不可重试错误立即提示，不再持续显示生成中。
