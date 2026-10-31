# 通知漏斗

微信和钉钉的通知太散，重要的事混在表情包和「通过扫码加入群聊」里，看不过来，也记不住。

这个工具把两块屏幕收敛成**一张每天更新的待办页**。装到手机主屏，打开就知道今天要动哪几件事。

它不做「通知聚合」。聚合只会让信息更多更乱。它做的是过滤——
**只留下需要你动作的事，其余当作噪音丢掉。**

```
微信 / 钉钉窗口
      │  截图
      ▼
   一张画面  ──►  模型识别「谁在等我、什么有截止」  ──►  state.json
                                                            │
                                                            ▼
                                                     每日待办网页
```

页面分三组：**催着的**、**等你回复**、**有空再做**。被滤掉的消息折叠在底部，显示条数，不占注意力。

## 为什么不用更直接的办法

做完调研后排除的路径，省得你再踩一遍：

| 方案 | 结果 |
| --- | --- |
| 读微信本地数据库 | SQLCipher 加密，密钥要从进程内存里挖。违反用户协议，版本一升级就失效，**会封号** |
| 读钉钉本地数据库 | 同样加密，同上 |
| 微信官方消息 API | 个人号不开放，不存在这条路 |
| 企业微信 API | 合规可行，但只覆盖企业微信，收不到个人微信 |
| Windows UI Automation | 微信 4.x 和钉钉桌面版都是 Qt 自绘界面，控件树里只有窗口骨架，**一个文本都读不到**（实测） |
| 安卓通知监听 | 可行且合规，但仅限安卓；iPhone 没有对等能力 |
| **截图 + 视觉识别** | 画面清晰可读，不改动任何应用，无封号风险 —— **本项目采用** |

## 环境要求

- Windows 10 / 11
- Python 3.10+
- 微信 4.x 或钉钉桌面版（任一，也可以两个都要）

## 安装

```bash
git clone https://github.com/ovo622x/daily-inbox.git
cd daily-inbox
pip install -r requirements.txt
python run.py --open
```

第一次运行会自动抓一次窗口，然后用 `data/state.example.json` 生成一张示例页面——先看看成品长什么样。

## 用起来

整个过程三步，第二步是唯一需要动脑的地方。

**1. 抓图**

```bash
python scripts/collect.py
```

在你的 `data/snapshots/` 里得到 `wechat_20261103-2004.png` 这类文件，同时写一份 `data/status.json` 记录两个应用是否在线。

**2. 提取**

把截图和 [`docs/extract-prompt.md`](docs/extract-prompt.md) 里的提示词一起丢给任意多模态模型，让它输出 JSON，存成 `data/state.json`。

这一步交给模型，不是交给正则。因为它要判断的是「这条消息到底要不要我做事」——比如「12 点前交」如果现在已经 13 点，结论不该是「12 点前交」，而是「已经过期了，先问一句还收不收」。

**3. 生成页面**

```bash
python run.py --build
```

产物是 `site/index.html`，单文件，样式和数据都在里面，直接丢到任何静态托管就能访问。

## 每天自动跑

Windows 任务计划程序新建一个每日任务，操作填：

```
程序：python
参数：run.py
起始位置：C:\path\to\daily-inbox
```

想连识别一起自动化，就把这个仓库接进任意支持定时 + 读图的 agent 里，让它跑完 `collect.py` 后读图写 `state.json`，再跑 `build.py`。

## 放到手机主屏

`site/` 目录是纯静态的，传到 GitHub Pages、Vercel、Netlify 或自己的服务器都行。

iPhone 用 Safari 打开链接 → 分享 → 添加到主屏幕，它就是一个图标。勾选状态存在 localStorage，刷新不丢。

## 数据结构

`data/state.json`：

| 字段 | 说明 |
| --- | --- |
| `items[].kind` | `overdue` 已过期 / `deadline` 有截止 / `reply` 等回复 / `todo` 要做 / `info` 知道就行 |
| `items[].action` | **下一步具体做什么**，写人话，不复述原文 |
| `items[].deadline` | 展示用文本，没有就 `null` |
| `noise[]` | 被滤掉的消息，只用于显示条数 |

完整示例见 [`data/state.example.json`](data/state.example.json)。

## 已知限制

1. **只支持 Windows**。窗口抓取用的是 Win32 的 `PrintWindow`。
2. **抓图时窗口会短暂弹出约 2 秒**。窗口最小化或在托盘时，必须先让它显示才能截到内容，截完自动收回。介意的话可以只在深夜跑。
3. 窗口被其他窗口完全遮挡时可能抓到空白，`status.json` 会把它标成 `blank`。
4. **做不到实时提醒**。手机端拿不到系统通知，这个工具保证你打开后不漏，不保证第一时间推你。
5. 识别质量取决于你用的模型。换模型需要重跑一遍，脚本不负责判断内容。

## 隐私

截图包含完整聊天内容。`data/snapshots/`、`data/state.json`、`data/status.json` 都已在 `.gitignore` 里——**别把它们提交到公开仓库**。

如果要把截图发给云端模型做识别，请自己确认这些内容是否可以离开本机。

## License

[MIT](LICENSE)
