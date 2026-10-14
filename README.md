# 押镖账本

一款 Windows 本地押镖日志统计工具。选择问道游戏目录后，程序读取其中的 `chat` 文本日志，按队伍整理角色、每轮收益与耗时，并展示历史图表。

## 功能

- 自动或手动扫描本机日志，识别同日多支队伍、角色编号和完成轮次。
- 分开统计游戏币、代金券、镖级、碰碰运气次数与耗时。
- 在看板中查看近 30 天或全部记录，切换金额与趟数、柱状图与双趋势图。
- 点击图表查看当日准确数值；所有记录存于本机 SQLite。

程序不需要本项目以外的服务，也不会上传游戏日志。小程序 Logo 与二维码仅用于界面展示；本工具与游戏官方无隶属关系。

## 界面预览

截图使用虚构数据，不包含玩家日志。图片宽度限制为 720 像素，点击可查看原图。

<a href="docs/overview.jpg"><img src="docs/overview.jpg" alt="押镖账本统计总览和镖级柱状图" width="720"></a>

<a href="docs/history-trend.jpg"><img src="docs/history-trend.jpg" alt="游戏币和代金券双趋势图" width="720"></a>

## 下载与使用

Windows 用户可从 GitHub Releases 下载 `wendao-escort-ledger-windows.zip`，解压后运行其中的 `押镖账本.exe`。需要系统安装 Microsoft Edge WebView2 Runtime。首次启动后在“设置”中选择游戏目录（包含 `chat` 文件夹），然后点击“扫描日志”。

数据保存在 `%LOCALAPPDATA%\WendaoEscort\escort.sqlite3`。卸载或替换程序不会清除这份账本；迁移电脑时可在程序关闭后复制该文件。不要将自己的 `chat` 日志或账本数据库提交到公开仓库。

## 从源码运行

需要 Windows、Python 3.9 或更高版本，以及 WebView2 Runtime。在项目根目录执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m desktop.escort_web_app
```

运行测试：

```powershell
.\.venv\Scripts\python.exe tests\test_escort_desktop.py
```

## 构建 Windows 程序

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\scripts\build-escort-desktop.ps1
```

输出位于 `dist\押镖账本.exe`。打包时，整个 `desktop/ui` 目录都会加入程序，因此 Logo、二维码和图表素材也会一并包含。分发时请将 `LICENSE`、`THIRD_PARTY_NOTICES.md` 和 `third_party/LUCIDE-LICENSE` 与程序放在同一个压缩包中。

## 项目结构

- `desktop/escort_parser.py`：解析游戏日志。
- `desktop/escort_analysis.py`：按队伍和轮次统计。
- `desktop/escort_data.py`：扫描与本地 SQLite 账本。
- `desktop/escort_web_app.py`、`desktop/ui/`：桌面窗口和界面。
- `tests/`：解析与账本测试。

## 许可证与素材

项目源码按根目录的 `LICENSE` 授权。界面中的小程序 Logo 和二维码属于“天墉城·万事屋”的品牌素材，公开源码不代表授予第三方商标使用权。Lucide 图标遵循其 ISC 许可证，详见 `THIRD_PARTY_NOTICES.md`。
