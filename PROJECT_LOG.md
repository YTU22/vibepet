# VibePet 项目工作日志 (PROJECT_LOG.md)

> 本文件用于记录本项目此后的所有开发工作。每次修改请在「工作日志」一节**追加新条目**（最新的放最上面），并同步更新「当前状态」。
>
> ⚠️ 本文件与 `DEVLOG.md`（历史开发日志，已停止更新）和 `CHANGELOG.md`（面向用户的版本更新日志）区分开：本文件记录**过程**，CHANGELOG 记录**结果**。

---

## 一、项目概述

- **名称**：VibePet（Windows 桌面宠物）
- **作者**：YTU22 | **仓库**：https://github.com/YTU22/vibepet
- **当前版本**：v1.2.14（2026-07-20）
- **定位**：Windows 桌面宠物应用，集软件使用时长监测、健康提醒、系统监控、待办便签、统计看板于一体
- **技术栈**：Python + PyQt6（UI）+ PyQt6-Charts（图表）+ SQLite3（存储）+ psutil/win32api（系统监控）+ win10toast（通知）+ PyInstaller（打包）

## 二、架构与模块地图

入口为 `main.py`：单实例锁（QLockFile）→ 日志/异常钩子 → ConfigManager / DatabaseManager / ReminderManager → PetWindow → MonitorThread（后台监控线程，信号驱动 UI）。

| 文件 | 行数 | 职责 |
|------|------|------|
| `main.py` | 200 | 启动入口、单实例锁、首次运行快捷方式、组件装配与信号连接 |
| `core/config.py` | 263 | 配置管理（`config.json`）、mtime 热重载、缺失键填充 |
| `core/database.py` | 424 | SQLite（`usage.db`）、使用时长聚合、todo 表、30 天清理 + VACUUM |
| `core/monitor.py` | 314 | 后台监控线程：前台进程追踪（WinEventHook）、空闲检测、动态采样间隔 |
| `core/reminder.py` | 393 | 健康提醒规则引擎（安全 eval）、随机情绪系统、待办念读 |
| `core/sys_monitor.py` | 275 | CPU/内存/磁盘/网络/GPU 采样（NVML/win32pdh） |
| `ui/pet_window.py` | 1666 | 桌宠主窗口：动画（GIF/QMovie）、气泡、拖拽、贴边隐藏、Snipaste 避让 |
| `ui/settings_dialog.py` | 2682 | 设置面板（6 Tab）、检测更新/下载线程、镜像测速 |
| `ui/stats_dialog.py` | 1329 | 统计看板：柱状图/饼图/待办清单/待办日记、CSV 导出 |
| `ui/todo_window.py` | 626 | 便签待办浮窗：拖拽、主题、边缘吸附 |
| `ui/tray_icon.py` | 184 | 系统托盘菜单与悬停提示 |
| `utils/helpers.py` | 134 | 路径、快捷方式、开机自启、资源定位 |
| `utils/updater.py` | 142 | 更新辅助逻辑 |
| `build_release.py` | 105 | PyInstaller 打包发布脚本（含隐私数据过滤） |

**关键数据文件**（运行时生成，勿打包分发）：`config.json`、`usage.db`、`vibe_pet.log`、`vibe_pet.lock`。

## 三、工作约定

1. **版本号**分散在 `ui/pet_window.py`、`ui/settings_dialog.py`、`ui/tray_icon.py` 的 `APP_VERSION` 及 `build_release.py`，升级时需同步。
2. **数据库 schema 变更**必须在 `init_db()` 中用 `PRAGMA table_info` 检测并 `ALTER TABLE` 无感迁移（见 v1.1.6 教训）。
3. **打包发布**前必须确认 zip 内不含 `config.json` / `usage.db` / `vibe_pet.log` / `vibe_pet.lock`（见 v1.2.2 教训）。
4. 阻塞操作（网络请求、VACUUM）一律放后台线程，不得占用 GUI 主线程。
5. 每次工作完成后：在下方追加日志条目（时间、版本、触发原因、改动内容、涉及文件、验证结果），如有用户可见变更同步更新 `CHANGELOG.md`。

## 四、当前状态

- 版本 v1.2.14，功能完整，无已知未修复缺陷。
- 已有分发产物：`dist/VibePet-v1.2.14.zip`（含双皮肤）。
- **注意**：v1.2.13+v1.2.14 已推送远程 main（至 `e6c8a2d`），v1.2.14 Release 尚未创建（zip 已就绪）。
- 历史日志见 `DEVLOG.md`（截至 v1.2.11）、`CHANGELOG.md`、`archives/walkthrough.md`。

---

## 五、工作日志

<!-- 新条目追加在本节顶部，格式：
### YYYY-MM-DD HH:MM | 版本 vX.Y.Z（若升级）
- **触发**：用户/任务来源
- **改动**：做了什么、为什么
- **文件**：涉及哪些文件
- **验证**：如何验证、结果
-->

### 2026-07-20 15:40 | 版本 v1.2.14
- **触发**：用户提供参考图 `C:\Geminiproject\d9f12e03623fc514309b97b927d207db.jpg`（羊毛毡质感深蓝灰小猫、翠绿大眼），要求：①参考此形象设计桌宠；②不要删除老设计，便于恢复；③保留按状态展示不同形态的能力。
- **方案**：皮肤化架构——果冻史莱姆移入 `assets/skins/slime/`（完整保留），新形象放 `assets/skins/cat/`，配置项 `pet_skin` + 设置面板下拉切换，双皮肤 paddings 各自实测锚定。
- **改动**：
  1. 新增 `tools/generate_cat_assets.py`：噪声扰动边缘的绒毛剪影（双层：绒毛光晕+本体渐变+噪点纹理）、翠绿渐变大眼（瞳孔+双高光）、粉内耳、胡须、贝塞尔曲线串球尾巴（可摇摆/翘起）；6 状态 24 帧循环动画，含飞机耳（angry）、垂耳（tired）等猫系语言。
  2. 资产迁移：`assets/{state}.gif|pet_*.png` → `assets/skins/slime/`；`tools/generate_pet_assets.py` 输出路径同步改为 skins/slime，其图标输出降级为皮肤内备份（根目录 icon 由默认皮肤 cat 生成）。
  3. `ui/pet_window.py`：新增 `_asset_path()`（skins/<skin>/ 优先，根目录回退）与模块级 `SKIN_PADDINGS` 双皮肤锚定表；`reposition_components` 按皮肤查表。
  4. `core/config.py`：新增 `"pet_skin": "cat"` 默认值（旧配置自动补齐，默认启用小猫）。
  5. `ui/settings_dialog.py`：外观 Tab 新增「宠物形象」下拉（墨团小猫/果冻史莱姆），load/save/reset 三处接线；皮肤切换经 `on_settings_changed → set_pet_size → load_animation` 链路自动生效。
  6. 图标更换为小猫形象；版本号 v1.2.13 → v1.2.14（四处同步），CHANGELOG 更新。
- **文件**：`tools/generate_cat_assets.py`（新增）、`tools/generate_pet_assets.py`、`assets/skins/**`、`assets/icon.*`、`ui/pet_window.py`、`ui/settings_dialog.py`、`core/config.py`、`ui/tray_icon.py`、`build_release.py`、`CHANGELOG.md`
- **验证**：`tools/preview_cat.png` 六状态 QA 预览 + 全分辨率局部复检通过（绒毛/大眼/耳/须/尾细节到位）；`py_compile` 全量通过。

### 2026-07-20 14:10 | 版本 v1.2.13
- **触发**：用户反馈桌宠形象不美观（尤其部分状态）、动效少且单一，要求升级优化；提供了 `C:\Geminiproject\hatch-pet`（另一 agent 的桌宠生成 skill）作为参考。
- **方案决策**：hatch-pet 是 Codex 专用的 8x11 雪碧图工作流，依赖其平台私有的 `$imagegen` 图像生成技能与 Codex 运行时，本环境不可用，且其雪碧图格式与 VibePet 的 6 状态 GIF/PNG 体系不兼容。因此仅借鉴其"逐状态生成 + QA 预览图"思路，改用 **numpy + PIL 程序化渲染** 全新形象。
- **改动**：
  1. 新增 `tools/generate_pet_assets.py` 渲染器：4 倍超采样抗锯齿；superellipse 软边果冻身体（垂直渐变 + 径向高光 + 底部内阴影 + 左上光泽斑 + 落地接触阴影）；每状态独立表情/配色/特效。
  2. 6 状态全部升级为 24 帧循环 GIF（70ms/帧）：idle 呼吸+眨眼、work 打字弹跳+火花、happy 高弹跳+爱心、tired 重眼皮+汗滴、sleep 趴扁+Zzz、angry 震动+怒气符号+蒸汽。
  3. GIF 采用全局共享调色板 + Floyd-Steinberg 抖动量化，解决首轮产出渐变色带问题（256 色限制）。
  4. 静态 PNG（代表帧）、icon.png/icon.ico 同步重绘。
  5. `ui/pet_window.py` 的 `gif_paddings`/`png_paddings` 按渲染器实测的本体 bbox 更新（气泡/面板锚定）。
  6. 版本号 v1.2.12 → v1.2.13（四处同步），CHANGELOG 更新。
- **文件**：`tools/generate_pet_assets.py`（新增）、`assets/*.gif|png|ico`（全部重绘，旧像素风资产可从 git 历史恢复）、`ui/pet_window.py`、`ui/settings_dialog.py`、`ui/tray_icon.py`、`build_release.py`、`CHANGELOG.md`
- **验证**：`tools/preview_sheet.png` 六状态 × 六帧 QA 预览通过；GIF 抽帧复检抖动后渐变色带已消除、表情可读；`py_compile` 通过。
- **踩坑**：① PIL `arc/line` 的 width 必须 int，float 会 TypeError；② 渲染器内坐标系混用（画布 1024 vs 最终 256）曾导致身体位置错误，已在入口统一换算；③ PIL 自动量化会产生明显色带，必须共享调色板 + 抖动。

### 2026-07-20 12:30 | 版本 v1.2.12（发布）
- **触发**：用户要求推送 GitHub 并包含安装包。
- **改动**：提交 v1.2.12 全部源码（commit `ea2d768`）推送至 `main`；`python build_release.py` 打包生成 `dist/VibePet-v1.2.12.zip`（47MB，243 文件）；创建 GitHub Release `v1.2.12` 并上传 zip；发布后重启新版 VibePet.exe。
- **踩坑**：首次打包失败——`dist/VibePet/VibePet.exe` 正在运行，`QMovie` 持有 `assets/work.gif` 文件句柄，PyInstaller 清理 dist 目录时 `WinError 32`。**打包前必须先关闭正在运行的 VibePet 实例。**
- **验证**：zip 内容核验无隐私文件（config.json/usage.db/log/lock 均未包含），Release 资产上传成功（https://github.com/YTU22/vibepet/releases/tag/v1.2.12），新进程已运行。

### 2026-07-20 11:50 | 版本 v1.2.12
- **触发**：用户反馈——①桌宠与截图软件（Snipaste、微信截图）冲突，截图自动复制后粘贴经常失败；②希望整体运行逻辑更清洁、丝滑、稳定。
- **根因排查**：
  - **粘贴失败元凶是「划词字数统计」**：`ui/pet_window.py` 的 `on_selection_detected` 在任何全局鼠标拖拽松手（>8px）或双击时，都会向前台窗口注入全局 `Ctrl+C` 并备份/还原剪贴板。截图同样是"拖拽选区松手"，松手瞬间该功能抢占剪贴板，把截图工具刚写入的图片覆盖掉 → 粘贴失败。且用户 `config.json` 中 `word_count_enabled=true`，冲突常驻。
  - **截图检测覆盖不足**：原规避逻辑仅匹配进程名 `snipaste`，且依赖 5~10 秒轮询。微信截图窗口属于 `WeChat.exe`（类名 `SnapShotWnd`），进程名不变，完全检测不到。
- **改动**：
  1. `utils/helpers.py`：新增 `SCREENSHOT_PROCESS_NAMES`（snipaste/snippingtool/screenclippinghost）与 `SCREENSHOT_WINDOW_CLASSES`（snapshotwnd 微信截图）及公共判定函数 `is_screenshot_tool()`。
  2. `core/monitor.py`：在 `SetWinEventHook` 前台窗口回调中增加窗口类名检测，新增 `screenshot_mode_changed(bool)` 信号实现**即时**隐藏/恢复；`status_updated` 信号末位新增截图状态作为权威同步；每轮循环对前台窗口做自愈式复核（钩子丢事件也能一个周期内纠正）。
  3. `ui/pet_window.py`：新增 `on_screenshot_mode_changed` 槽与幂等的 `_set_screenshot_mode()`（统一事件钩子与轮询两条路径）；隐藏前记录桌宠/便签各自可见状态，恢复时不再误弹用户手动隐藏的窗口；新增 `is_screenshot_tool_foreground()`；`on_selection_detected` 增加两道守卫——截图工具在前台时不注入按键不碰剪贴板、前台为本程序自身对话框时跳过。
  4. `main.py`：连接 `screenshot_mode_changed` 信号。
  5. 版本号 v1.2.11 → v1.2.12（pet_window/settings_dialog/tray_icon/build_release 四处同步），更新 CHANGELOG.md。
- **文件**：`utils/helpers.py`、`core/monitor.py`、`ui/pet_window.py`、`main.py`、`ui/settings_dialog.py`、`ui/tray_icon.py`、`build_release.py`、`CHANGELOG.md`
- **验证**：`py_compile` 全量编译通过；`is_screenshot_tool` 六个用例（Snipaste/微信/系统截图/普通窗口）全部判定正确。实际截图联动效果需用户在桌面环境复测（本环境无法模拟微信截图）。
- **遗留说明**：若用户不需要划词统计，可在设置中关闭「全局划词字数统计」以彻底免除 Ctrl+C 注入；QQ 截图（类名 `TXGuiFoundation` 与主窗口共用）暂未纳入识别，如有需求可后续补充。

### 2026-07-20 11:35 | 版本 v1.2.11（未变）
- **触发**：用户要求建立项目日志，记录后续所有工作。
- **改动**：通读项目（README/FEATURES/CHANGELOG/DEVLOG/config.json/main.py 及各模块行数统计），梳理架构与模块职责，创建本文件 `PROJECT_LOG.md`，并确立后续工作记录约定。
- **文件**：`PROJECT_LOG.md`（新增）
- **验证**：人工核对目录树与模块清单一致。
