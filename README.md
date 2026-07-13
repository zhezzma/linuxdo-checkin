# 公告

请不要魔改本项目多线程刷论坛，本项目的初衷只是为了给个人账号刷一下访问天数的，不是给号商养号用的。

# LinuxDo 每日签到（每日打卡）

## 项目描述

这个项目用于通过 Cookie 自动登录 [LinuxDo](https://linux.do/) 网站，模拟浏览器登录以达到每日签到的功能。

每天在 `GitHub Actions` 中自动运行，也支持 `青龙面板`。

## 功能

- 通过 Cookie 自动登录 `LinuxDo`，完成每日签到。
- 内置 `turnstilePatch` 扩展，自动处理 Cloudflare Turnstile 质询。
- 每天在 `GitHub Actions` 中自动运行。
- 支持 `青龙面板` 和 `Github Actions` 自动运行。

## 环境变量配置

| 环境变量名称            | 描述                           | 示例值                          |
|-------------------|------------------------------|------------------------------|
| `LINUXDO_COOKIES` | 从浏览器 DevTools 复制的 Cookie 字符串 | `_t=xxx; _forum_session=yyy` |
| `PROXY`           | 可选，代理地址(http/https/socks5)；配合住宅代理可绕过数据中心 IP 的 CF 拦截 | `http://user:pass@host:port` |
| `HEADLESS`        | 可选，是否无头；本地调试设 `false` 可观察浏览器 | `false` |

> 本地运行时，可将上述变量写入项目根目录的 `.env` 文件（脚本会自动加载，依赖 `python-dotenv`）。

> 获取方式：打开 [linux.do](https://linux.do/) 并登录 → 按 F12 → Application → Cookies → `https://linux.do` → 全选所有 Cookie 复制为字符串粘贴即可。

---

## 如何使用

### GitHub Actions 自动运行

此项目的 GitHub Actions 配置会自动定期运行签到脚本。工作流文件位于 `.github/workflows/daily-check-in.yml`。

#### 配置步骤

1. **设置环境变量**：
    - 在 GitHub 仓库的 `Settings` -> `Secrets and variables` -> `Actions` 中添加：
        - `LINUXDO_COOKIES`：从浏览器复制的 Cookie 字符串。

2. **手动触发工作流**：
    - 进入 GitHub 仓库的 `Actions` 选项卡。
    - 选择你想运行的工作流。
    - 点击 `Run workflow` 按钮，选择分支，然后点击 `Run workflow` 以启动工作流。

#### 运行结果

`Actions`栏 -> 点击最新的 `Daily Check-in` workflow run -> `run_script` -> `Execute script` 即可查看日志。

### 青龙面板使用

*注意：如果是 docker 容器创建的青龙，**请使用 `whyour/qinglong:debian` 镜像**，latest（alpine）版本可能无法安装部分依赖*

1. **依赖安装**
    - 安装 Python 依赖
      - 进入青龙面板 -> 依赖管理 -> 安装依赖
        - 依赖类型选择 `python3`
        - 自动拆分选择 `是`
        - 名称填写（仓库 `requirements.txt` 文件的完整内容）：
            ```
            DrissionPage==4.1.0.18
            loguru==0.7.2
            ```
        - 点击确定
    - 安装 linux chromium 依赖
      - 青龙面板 -> 依赖管理 -> 安装 Linux 依赖
      - 名称填 `chromium`
        > 若安装失败，可能需要执行 `apt update` 更新索引（若使用 docker 则需进入 docker 容器执行）

2. **添加仓库**
    - 进入青龙面板 -> 订阅管理 -> 创建订阅
    - 依次在对应的字段填入内容（未提及的不填）：
      - **名称**：Linux.DO 签到
      - **类型**：公开仓库
      - **链接**：https://github.com/doveppp/linuxdo-checkin.git
      - **分支**：main
      - **定时类型**：`crontab`
      - **定时规则**(拉取上游代码的时间，一天一次，可以自由调整频率): 0 0 * * *

3. **配置环境变量**
    - 进入青龙面板 -> 环境变量 -> 创建变量
    - 需要配置以下变量：
        - `LINUXDO_COOKIES`：从浏览器复制的 Cookie 字符串

4. **手动拉取脚本**
    - 首次添加仓库后不会立即拉取脚本，需要等待到定时任务触发，当然可以手动触发拉取
    - 点击右侧"运行"按钮可手动执行

#### 运行结果

- 进入青龙面板 -> 定时任务 -> 找到 `Linux.DO 签到` -> 点击右侧的 `日志`


## 自动更新

- **Github Actions**：默认状态下自动更新是关闭的，[点击此处](https://github.com/ChatGPTNextWeb/ChatGPT-Next-Web/blob/main/README_CN.md#%E6%89%93%E5%BC%80%E8%87%AA%E5%8A%A8%E6%9B%B4%E6%96%B0)
查看打开自动更新步骤。
- **青龙面板**：更新是以仓库设置的定时规则有关，按照本文配置，则是每天0点更新一次。
