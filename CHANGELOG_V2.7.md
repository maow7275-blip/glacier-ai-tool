# GlacierAI V2.7 更新说明

发布日期：2026-05-22

## 重点变更

### 参考图改用文件上传接口

旧版本（V2.6 及以前）的参考图是把本地图片以 base64 dataURI 的形式嵌进生成请求 JSON 里，
图片越大，请求体越大，容易触发网关上限或超时。

V2.7 改为先调用 `/v1/files/image-upload` 上传图片拿到 url，
生成请求里只携带 url，请求体大幅缩减。

- 上传接口：`POST https://www.hfsyapi.cn/v1/files/image-upload`（multipart/form-data，字段名 `file`）
- 返回结构：`{ success, message, data: { url, name, filename, size } }`
- 生成请求字段保持不变：图片用 `reference_images: [url, ...]`，视频用 `images: [url]`

### 新流程

1. 用户在工具里选参考图（图片最多 4 张，视频 1 张）
2. 后台并行上传到 `/v1/files/image-upload`
3. 上传期间界面显示"上传中..."占位，期间无法点击生成
4. 上传完成后保留 url，下次生成直接用，不再重复上传
5. 任意一张上传失败会弹窗提示并自动从列表里剔除

### 其他

- 缩略图仍由本地图片字节渲染，预览速度不变
- 上传过程会写入 `debug_output.log` 的 `[UPLOAD]` 行，便于排查
- 选图前如果没填 API Key，会先弹窗提示

## 文件改动

- `app.py`
  - 新增常量 `FILE_UPLOAD_URL`
  - 新增 `UploadRefImageThread`（QThread，后台 multipart 上传）
  - `_pick_ref_image` / `on_pick_img_ref` 改为异步上传
  - `_img_ref_data_list` 元素由 dataURI 字符串改为 `{url, bytes, name, uploading, error}` 字典
  - `_refresh_img_ref_preview` 适配新结构，加上"上传中"占位
  - `on_generate` 增加"参考图正在上传"拦截，传给生成线程的是 url 列表
  - 三处版本号 V2.6 → V2.7
- `GlacierAI.spec`：输出名 `GlacierAI_V2.6` → `GlacierAI_V2.7`

## 兼容性

- 后端字段未变，旧的 dataURI 形式仍然可被服务端接受，但不再使用。
- 历史记录格式无变化，旧版本生成的历史记录可正常打开。
