# Development and release record

Version 0.2.0. The distributable ZIP contains only runtime plugin files. Private Claude history, reference photographs, local paths and host code are excluded. Source publication was authorized on 2026-11-20 as part of marketplace delivery. Dated decisions below preserve the publication sequence; the latest entry supersedes earlier restrictions for this task.

## Release sequence confirmed on 2026-11-17

先将时钟插件、宿主和三个 SDK 配套仓库的本批源码同步到远端。发版在本地验证成功后推进，当前不急于发布。已通过的隐藏 Electron 测试不代替尚未完成的实际置顶、鼠标穿透与本地运行环境验收。

Sync this batch of source changes first. Release follows successful local verification; do not rush publication or treat a source push as a release.

## Marketplace publication authorized on 2026-11-20

用户已授权上架时钟插件。核对时市场尚无此条目、仓库无 Release；正式宿主 0.32.0 与测试宿主 0.30.2-internal.19 的已发布源码均早于桌面面板支持。先补齐插件 CI 构建，兼容宿主实际发版并验证后再填写最低宿主版本和登记市场。插件上架授权不改变宿主仅通过受邀测试渠道分发的边界。

Plugin publication is authorized. Compatible host publication and verification remain prerequisites for the marketplace entry; no guessed minimum host version is declared.

## Plugin-first publication on 2026-11-20

用户随后明确改为：“先上架插件吧。如果版本不对，就说不兼容。”本条取代上面的等待兼容宿主再上架安排；本轮只发布插件，不发布宿主。市场与插件简介明确标注当前已发布宿主不兼容，预留 0.33.0 安装门槛排除现有版本，并在启动时再次检查所需接口。此门槛不是已发布兼容版本的声明；后续宿主实际发版仍需单独验证并更新说明。

The maintainer explicitly authorized plugin-first listing with incompatibility disclosure. Do not release the host in this task. The reserved version floor excludes current releases; API checks fail before reminders or persistence begin. This exception applies to this plugin and does not claim released-host compatibility.

## Compatible host verified and released on 2026-11-20

维护者随后授权打开本地正式环境、安装时钟，再发布兼容宿主。macOS Apple Silicon 正式宿主 0.33.0 已完成签名、公证、时钟 0.2.0 实际安装包验收及正式更新源摘要校验。此决定取代本任务此前暂不发布宿主的安排；宿主仍只通过受邀测试渠道分发。0.33.0 现在是经过验证的版本门槛；旧宿主继续禁用并提示不兼容。此源码提交只校正简介与兼容说明，不替换 v0.2.0 已发布 ZIP、摘要或权限。

The maintainer subsequently authorized host release after local Production validation. Signed/notarized macOS Apple Silicon host 0.33.0 has passed real plugin installation, background reminders and restart checks, and publication verification. This supersedes the earlier host deferral. Existing v0.2.0 assets remain immutable; source/registry metadata now describes the verified compatibility. Host distribution remains invitation-only.
