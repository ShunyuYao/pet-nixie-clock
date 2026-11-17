# 辉光管时钟 / Nixie Clock

透明桌面辉光管时钟，默认北京时间，可切换时区、四管／六管、12／24 小时制、亮度与大小。木底座的三颗铜钮依次是时间／日期、提醒、设置。底座不显示时区铭牌。

当前版本 **0.2.0 开发候选**：正式插件已实现并通过真实桌宠的隐藏 Electron 验证。它依赖尚未发布的桌面面板 SDK；`apiVersion: 1` 不代表旧宿主兼容，尚未上架市场。

## 运行原型

```sh
npm ci
npm run dev
```

打开 http://127.0.0.1:47631。原型里的背景、演示条与静态宠物只用于浏览器预览，正式插件没有这些内容。素材已提交；预览和打包不需要 Python。

## 构建与安装

```sh
npm run build
```

输出 `dist/nixie-clock/`、`dist/nixie-clock-0.2.0.zip` 和 SHA-256 文件。通过兼容宿主的插件安装入口导入文件夹或 ZIP。启动插件时自动打开时钟；在设置里选择“隐藏”，后台提醒继续运行，从宿主插件管理或托盘可重新打开。

兼容宿主必须支持 `entry.panel.desktop:true`、`ui.getPanelBounds`、`ui.setPanelBounds` 和 `ui.setPanelHitRegions`。源码支持状态与已发布安装包是两回事；旧版会提示需要升级。未声明未经实际验证的最低发行版。

## 使用

- 时区和定时提醒都按所选时区计算；切换时区不会立即补报当前小时。
- 拖动时钟移动原生窗口；右下角拖动、捏合／Ctrl 或 ⌘ 滚轮、设置滑杆、键盘方向键均可缩放。
- 日期模式持续 5 秒；显示秒切换为六管。窗口位置、大小和设置可在重启后恢复。
- 整点、喝水、久坐、每日自定义提醒和倒计时由独立 tool 调度。同一时刻的提醒排队显示；关闭面板后继续，退出宿主期间不运行。重开宿主后到期倒计时、间隔提醒各合并为一次。
- “与桌宠联动”开启时通过真实宠物气泡提醒，关闭时仅保留时钟视觉信号。气泡显示与动作优先级服从宿主。
- 不申请网络、文件、账号或日历权限。只使用 `ui`、`storage`、`scheduler`、`pet`。
- 当前宿主对外部插件提供卸载入口；卸载停止后台调度并关闭窗口。关闭时钟窗口本身不会停止提醒。

## 验证

```sh
npm test
npm run build
PET_PLUGIN_HOST_DIR=/path/to/desktop-pet/demo npm run test:native
```

浏览器测试通过真实输入覆盖草稿、时区、大小与提醒。后台逻辑覆盖重启、夏令时回拨去重、并发提醒与倒计时取消。真实 Electron 测试使用独立临时 profile 和账号夹具，验证正式安装、预加载 SDK、原生几何、后台气泡、重启和卸载。

隐藏测试不能证明 OS 鼠标穿透、窗口置顶、多个显示器及 Spaces；这些是可见验收项。当前插件只使用所在桌面，不额外请求跨 Space／全屏覆盖。

## 源码

- `prototype/index.html`：浏览器原型与正式插件共用的时钟视图。
- `plugin/host.js`：透明原生窗口、命中区域和持久化适配。
- `plugin/reminders.js`、`plugin/tool.js`：后台调度与持久化状态。
- `scripts/build.mjs`：从共享视图生成正式插件，打包只包含运行所需文件。
- `prototype/assets-src/render.py`：NumPy/Pillow 素材渲染器，木底座实体高度已压低约 25%。

No credentials, host code, or private conversation history belong in the distributable ZIP. Marketplace publication must wait for a verified compatible host release.
