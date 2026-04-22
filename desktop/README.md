# coco-flow Desktop Launcher

最小可用的 Electron 桌面入口，目标是把现有 `coco-flow remote ...` CLI 包成一个可点按的启动器。

## 当前范围

- 展示已保存 remotes
- 新增 / 删除 remote
- Connect / Restart & Connect / Disconnect
- 查看单个 remote 的状态
- 流式展示 CLI 日志
- 连接成功后自动打开本地 Web URL

## 设计约束

- 继续直接调用已安装的 `coco-flow` 可执行文件
- 不重写 SSH、remote runtime、任务系统或 Web workflow
- 界面视觉按仓库根目录 [`DESIGN.md`](../DESIGN.md) 的暖色、衬线标题、低技术感方向实现

## 本地开发

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow/desktop
npm install
npm run dev
```

构建：

```bash
npm run build
npm run preview
```
