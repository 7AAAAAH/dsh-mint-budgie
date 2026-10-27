# DSH Mint Budgie 桌宠

给 DeepSeek Harness（DSH）桌面端使用的悬浮桌宠。它不会在 DSH 窗口里再显示一只，只在 Windows 桌面悬浮，展示当前项目名和正在执行的工作内容。

## 功能

- 工作状态浮窗固定在宠物旁，深灰半透明、圆角，项目名在上，当前工作内容在下。
- 长工作内容自动横向循环滚动；空闲时不显示“空闲”或任务浮窗。
- 单击或双击宠物播放一次 `peek` 歪头姿态，播放结束后回到站立姿势。
- 双击会恢复/最小化任务浮窗，并打开或聚焦 DSH。
- 右键打开设置或隐藏宠物。
- 设置支持宠物大小、透明度、滑杆和数值输入，窗口本身可调整大小。
- 支持双屏及不同缩放比例的 Windows 虚拟桌面，宠物可以拖到另一块屏幕。

## 安装

### 从 DSH 插件市场

在 DSH 中打开 **插件 → 发现**，搜索 `dsh-mint-budgie`，安装后重启 DSH。安装包已带 `desktop/mint-budgie.exe`，通常不需要额外安装 Python。

### 从 npm 安装

```powershell
dsh plugin --profile desktop add dsh-mint-budgie
```

安装后重启 DSH。插件 Host 会自动启动 `desktop/pet-window.pyw`。

### 可选：Python 运行方式

插件优先运行 `desktop/mint-budgie.exe`。只有删除该文件、改用源码模式时，才需要：

```powershell
py -m pip install Pillow
```

如果 Python 不在 `PATH` 中，可以设置 `DSH_PET_PYTHON` 为 `pythonw.exe` 的完整路径。

## 使用

- 拖动宠物可跨屏移动。
- 单击切换歪头动作。
- 双击打开 DSH，并恢复/收起任务浮窗。
- 右键选择“设置”调整大小与透明度，或选择“隐藏宠物”。

## 说明

- 当前仅支持 Windows。
- 桌宠进程会读取 DSH Host 写入的 `desktop/state.json`，因此 DSH 与桌宠必须使用同一个插件安装目录。
- 隐藏宠物后，DSH Host 不会自动重新启动它；再次双击 DSH 中的桌宠入口或重新启用插件即可恢复。

## 许可证

MIT
