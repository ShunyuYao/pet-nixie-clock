# 辉光管时钟 / Nixie Clock

吐梨邦（Turi Topia）提供可聊天、互动和到朋友桌面串门的 AI 桌宠。

Turi Topia (吐梨邦) brings AI pets to the desktop, with conversation, interaction and visits between friends.

[官网 / Website](https://turitopia.com/) · [脚手架与指南 / Scaffold](https://github.com/ShunyuYao/create-pet-plugin) · [SDK 类型 / API types](https://github.com/ShunyuYao/pet-plugin-types) · [插件市场 / Registry](https://github.com/ShunyuYao/pet-plugin-registry)

这是吐梨邦的时钟插件。This clock plugin runs inside Turi Topia.

市场状态：**已上架，0.2.0**；核实日期 **2026-11-20**。[固定登记记录](https://github.com/ShunyuYao/pet-plugin-registry/blob/dca6b5b3a9511cc7397de2c00d687998a8f16f9b/registry/plugins.json)与[禁用清单](https://github.com/ShunyuYao/pet-plugin-registry/blob/dca6b5b3a9511cc7397de2c00d687998a8f16f9b/registry/blocklist.json)已核对；已在应用内从正式市场安装并运行。

Marketplace: **listed, version 0.2.0**, verified **2026-11-20** against the pinned registry and blocklist above. In-app marketplace installation and operation have been verified.

透明桌面辉光管时钟，默认北京时间，可切换时区、四管／六管、12／24 小时制、亮度与大小。木底座的三颗铜钮依次是时间／日期、提醒、设置。底座不显示时区铭牌。

当前插件版本 **0.2.0**，已在经过签名、公证的 **macOS Apple Silicon 正式宿主 0.33.0** 中验证安装、后台提醒和重启恢复。正式宿主 0.32.0 与测试宿主 0.30.2-internal.19 不兼容；其他平台需要对应的兼容宿主构建。

最低宿主版本为 **0.33.0**；本次构建验证针对 macOS Apple Silicon。插件启动还会核对三个桌面窗口接口，缺失时明确提示不兼容，并停止启动，不写配置或开启后台提醒。`apiVersion: 1` 本身不代表兼容。

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

兼容宿主必须支持 `entry.panel.desktop:true`、`ui.getPanelBounds`、`ui.setPanelBounds` 和 `ui.setPanelHitRegions`。低于版本门槛的宿主可能允许下载后安装，但会禁用插件，在已安装页显示所需版本，时钟和后台提醒均不会启动，仍可卸载。宿主仍仅通过受邀测试渠道提供。

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
PET_PLUGIN_HOST_DIR=/path/to/older-host/demo npm run test:native:incompatible
# 上架后核验真实市场入口、可见提示和下载后的版本禁用
PET_PLUGIN_HOST_DIR=/path/to/older-host/demo npm run test:native:market
```

浏览器测试通过真实输入覆盖草稿、时区、大小与提醒。后台逻辑覆盖重启、夏令时回拨去重、并发提醒与倒计时取消。真实 Electron 测试使用独立临时 profile 和账号夹具，验证正式安装、预加载 SDK、原生几何、后台气泡、重启和卸载。

隐藏测试不能证明 OS 鼠标穿透、窗口置顶、多个显示器及 Spaces；这些是可见验收项。当前插件只使用所在桌面，不额外请求跨 Space／全屏覆盖。

## 源码

- `prototype/index.html`：浏览器原型与正式插件共用的时钟视图。
- `plugin/host.js`：透明原生窗口、命中区域和持久化适配。
- `plugin/reminders.js`、`plugin/tool.js`：后台调度与持久化状态。
- `scripts/build.mjs`：从共享视图生成正式插件，打包只包含运行所需文件。
- `prototype/assets-src/render.py`：NumPy/Pillow 素材渲染器，木底座实体高度已压低约 25%。

No credentials, host code, or private conversation history belong in the distributable ZIP. Plugin 0.2.0 is verified against the signed and notarized macOS Apple Silicon host 0.33.0, including installation, background reminders and restart recovery. Older hosts remain incompatible; other platforms require a matching host build. Required desktop APIs are checked at activation. Hosts remain invitation-only; no npm publication is implied.

## 发布流程

GitHub Actions 在主分支更新、PR 或手动触发时运行单元测试、浏览器测试并构建 ZIP，产物保存在 `nixie-clock-package`。公开 CI 不访问私有宿主仓库；真实宿主安装、窗口生命周期和原生交互仍需单独验收。

发布前核对兼容状态、版本门槛与本页说明，再推送与插件版本一致的 `v<version>` 标签。标签构建校验版本和最低宿主声明后，直接将同一次 CI 构建的 ZIP 与 SHA-256 发布到 GitHub Release。市场登记使用该 Release 的摘要和权限；CI 构建成功本身不等于已经上架。兼容说明已依据宿主 0.33.0 的实际构建与发布回执更新；v0.2.0 的既有 ZIP 与摘要保持不变。
