# Libot

面向 `booking.lib.zju.edu.cn` 的座位空闲查询/监控小工具。

核心原则：不做 CAS 自动登录；直接使用你从浏览器复制出来的 Cookie（相当于请求头里的 `Cookie: ...`）。

## 功能

- CLI：查询区域（房间）列表、查询空闲座位、生成 SVG 可视化（可选）
- GUI（Qt/PySide6）：列表模式展示空闲座位，并按馆舍分组
- 钉钉机器人推送：每分钟刷新；监控馆舍有空位时推送（消息前缀 `[ZJU]`，便于关键字筛选）

## 快速开始（开发态）

建议使用 Python 3.10+。

```bash
pip install -e .
libot ping
```

GUI 需要额外依赖：

```bash
pip install -e '.[gui]'
libot-gui
```

## 桌面程序（不使用本地 Web）

GUI 是“列表模式”（不显示座位图）：馆舍 → 房间 → 空闲座位号（示例）。

### Cookie / webhook 配置

- Cookie（必需）
	- 环境变量：`LIBOT_COOKIE='a=b; c=d'`
	- 或在 GUI 输入框粘贴
- 钉钉 webhook（可选）
	- 环境变量：`DINGTALK_WEBHOOK='https://oapi.dingtalk.com/robot/send?...'`
	- 或在 GUI 输入框填写

### 监控与推送

- 每 60 秒自动刷新一次
- 监控馆舍支持多选（默认只勾选“主馆”和“基础馆”）
- 只有当监控馆舍“有空位”时才推送；没空位不推送
- 推送消息格式：
	- `某馆有空位：`
	- `【房间名】对应链接`
	- ...

### 锁屏持续运行（macOS）

程序内默认会自动开启“防睡眠”（使用 macOS 自带 `caffeinate`），锁屏后仍能继续每分钟刷新/推送。

注意：合盖通常会睡眠（系统限制），这时程序会暂停。

## macOS 一键脚本

### 一键运行（macOS）

双击运行根目录的 `Libot.command`：自动创建虚拟环境、安装依赖并启动 GUI。

如果系统提示“无法打开/来自身份不明开发者”，请在 Finder 里右键 -> 打开，或到“系统设置 -> 隐私与安全性”里允许。

### 一键打包成 .app（macOS）

双击运行根目录的 `BuildLibotApp.command`，会生成：`dist/Libot.app`。

之后你就可以直接双击 `dist/Libot.app` 启动。

#### 把钉钉 webhook 打包进 .app

仓库内提供模板：`libot_bundled.example.json`。

建议你在本地新建/编辑 `libot_bundled.json`（该文件已在 `.gitignore` 中忽略，避免把 token 推到 GitHub）：

- 填入 `dingtalk_webhook`
- 重新运行 `BuildLibotApp.command` 打包

GUI 取 webhook 的优先级：

1) 环境变量 `DINGTALK_WEBHOOK`
2) GUI 输入框
3) 打包内置的 `libot_bundled.json`

#### 开机自启动（打包好的 .app）

推荐先把 `dist/Libot.app` 拖到 `/Applications/`，然后运行：

```bash
./InstallLibotAutostart.command /Applications/Libot.app
```

## CLI：列出空闲座位（第一期功能）

该功能通过后端接口 `/api/Seat/seat` 获取座位状态。

- 方式 1：直接传浏览器 Cookie（推荐）
	- `libot seats --area 7 --day 2026-01-07 --cookie "a=b; c=d"`
- 方式 2：用环境变量传 Cookie
	- `export LIBOT_COOKIE='a=b; c=d'`
	- `libot seats --area 7 --day 2026-01-07`

#### 查看“真实位置”（坐标/平面图）

- 先列出所有可用区域（房间）的 `area id`：
	- `libot areas`
- 查看某个区域的空闲座位，并输出坐标（`point_x/point_y`）：
	- `libot seats --area 7 --day 2026-01-07 --coords --limit 20`

命令会额外打印该区域在 `/api/Seat/tree` 里对应的 `image_url`（平面图链接），你可以用坐标在平面图上定位。

#### 直接可视化（生成 SVG）

- 生成一个带背景平面图的 SVG，并把空闲座位叠加成点：
	- `libot viz --area 7 --day 2026-01-07 --out seats.svg`
	- 打开 `seats.svg` 即可查看（点上悬停会显示座位号）

## 注意事项

- 不要把你的 Cookie / webhook 提交到 git（已在 `.gitignore` 里尽量规避常见文件，但仍建议你自查）
- 本项目仅做“查询/监控”用途，默认不处理 CAS 登录流程
