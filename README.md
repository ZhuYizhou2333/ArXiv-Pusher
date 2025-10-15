# ArXiv Pusher

每日自动从 ArXiv 拉取指定分类的最新论文，使用大语言模型进行智能过滤和总结，并将报告推送到您的邮箱。支持多用户配置，每个用户可以自定义关注领域和总结风格。

## ✨ 功能特性

### 核心功能
*   **自动拉取**：每日定时从 ArXiv 获取用户指定分类下的最新论文
*   **智能过滤** ⭐：使用 AI 根据论文摘要判断是否符合用户研究兴趣，自动过滤不相关论文
*   **深度总结**：利用大语言模型对论文进行深度分析和总结，包括：
    *   摘要的中文翻译
    *   关键创新点提炼
    *   核心理论与方法阐述
    *   实验设计与结果展示
    *   主要研究结论
    *   重要参考文献解读
*   **邮件推送**：将生成的论文总结报告通过邮件发送给指定用户，支持 Markdown 格式
*   **审查机制** ⭐：被过滤的论文会以附录形式列在邮件末尾，包含标题和摘要，供用户二次审查

### 高级特性
*   **多用户支持**：支持配置多个用户组，每个用户组独立配置
*   **灵活配置**：
    *   自定义 ArXiv 论文分类
    *   自定义 AI 总结提示词（可针对不同领域定制）
    *   自定义兴趣过滤提示词（AI 自动判断论文相关性）
    *   配置每用户最大处理论文数量
    *   配置回溯天数
*   **本地报告**：为每个用户生成独立的 Markdown 格式报告文件
*   **定时执行**：基于 `apscheduler` 实现每日定时执行任务
*   **完善的日志**：使用 `loguru` 记录详细的运行日志

## ⚙️ 安装与依赖

### 1. Python 环境
请确保您已安装 Python 3.7+。

### 2. 克隆项目
```bash
git clone <your-repository-url>
cd ArXiv-Pusher
```

### 3. 安装依赖
```bash
pip install requests arxiv PyPDF2 openai markdown2 loguru apscheduler beautifulsoup4
```

或创建 `requirements.txt` 文件：
```txt
requests
arxiv
PyPDF2
openai
markdown2
loguru
apscheduler
beautifulsoup4
```

然后安装：
```bash
pip install -r requirements.txt
```

### 4. 可选依赖
如果需要从 HTML 转换 PDF（备用方案），请安装：
```bash
# Ubuntu/Debian
sudo apt-get install wkhtmltopdf

# macOS
brew install wkhtmltopdf
```

## 🛠️ 配置说明

在项目根目录下创建 `config.py` 文件。以下是完整的配置示例：

```python
# config.py

# AI 模型配置（全局共享）
AI_CONFIG = {
    "api_key": "your-api-key-here",
    "base_url": "https://api.openai.com/v1",  # 或通义千问等其他兼容 OpenAI 格式的 API
    "model": "gpt-4"  # 或 "qwen-plus-latest" 等
}

# 邮件服务器配置（全局共享）
EMAIL_SERVER_CONFIG = {
    "sender": "your_email@example.com",
    "password": "your_password_or_app_specific_password",
    "smtp_server": "smtp.example.com",  # 如 "smtp.qq.com", "smtp.gmail.com"
    "smtp_port": 587,
    "use_tls": True,
}

# 通用配置
GENERAL_CONFIG = {
    "days_lookback": 1,  # 回溯天数，1 表示获取昨天的论文
    "max_papers_per_user": 50,  # 每个用户最多处理的论文数量，None 表示不限制
}

# 默认提示词模板（当用户未自定义时使用）
DEFAULT_PROMPT_TEMPLATE = """请你担任学术论文助理，用中文针对下列论文内容进行详细总结。
输出遵循下面的结构：
1. 中文翻译：对论文摘要进行准确、流畅的中文翻译；
2. 创新点：列出 3 个关键创新点，并说明其重要性；
3. 理论与方法：详细描述论文采用的主要理论框架和研究方法；
4. 实验与结果：描述论文的核心实验设计和数据结果；
5. 结论与影响：列出论文的关键研究结论。

论文原文内容如下：
{text}

请严格按照上述格式输出，注意使用 markdown 格式进行排版。"""

# 用户配置列表
# 每个用户可以配置：
# - name: 用户名称（用于标识和日志）
# - email: 接收论文报告的邮箱地址（多个邮箱用逗号分隔）
# - arxiv_categories: 关注的 arXiv 论文分类列表
# - custom_prompt: 自定义 AI 总结提示词（可选，不设置则使用默认模板）
# - interest_filter_prompt: 兴趣过滤提示词（可选，用于 AI 判断用户是否对论文感兴趣）
USERS_CONFIG = [
    {
        "name": "机器学习研究组",
        "email": "user1@example.com,user2@example.com",
        "arxiv_categories": ["cs.LG", "cs.AI"],
        "custom_prompt": """请你担任机器学习领域学术论文助理，用中文针对下列论文内容进行总结。
输出遵循下面的结构：
1. 中文翻译：对论文摘要进行准确、流畅的中文翻译；
2. 创新点：列出 3 个关键创新点，并说明其重要性；

论文原文内容如下：
{text}

请严格按照上述格式输出，注意使用 markdown 格式进行排版。""",
        # 兴趣过滤提示词（可选）
        "interest_filter_prompt": """请判断用户是否会对下面这篇机器学习论文感兴趣。

用户研究兴趣：强化学习、深度学习、神经网络优化

论文摘要：
{abstract}

请仅回答"是"或"否"。如果论文主要涉及上述研究兴趣，请回答"是"；否则回答"否"。"""
    },
    {
        "name": "计算机视觉研究组",
        "email": "cv_team@example.com",
        "arxiv_categories": ["cs.CV"],
        "custom_prompt": """请你担任计算机视觉学术论文助理，用中文针对下列论文内容进行 200-300 字的简单总结。

论文原文内容如下：
{text}""",
        # 只关注生成式模型相关论文
        "interest_filter_prompt": """请判断用户是否会对下面这篇计算机视觉论文感兴趣。

用户研究兴趣：生成式模型（Generative Models），包括：
- 扩散模型 (Diffusion Models)
- 生成对抗网络 (GANs)
- 变分自编码器 (VAEs)
- 文本到图像生成
- 视频生成

论文摘要：
{abstract}

请仅回答"是"或"否"。"""
    },
]
```

### 配置项详细说明

#### AI_CONFIG - AI 模型配置
| 参数 | 说明 | 示例 |
|------|------|------|
| `api_key` | AI 服务的 API 密钥 | `"sk-xxx"` |
| `base_url` | API 接入点 | `"https://api.openai.com/v1"` |
| `model` | 使用的模型名称 | `"gpt-4"`, `"qwen-plus-latest"` |

#### EMAIL_SERVER_CONFIG - 邮件服务器配置
| 参数 | 说明 | 示例 |
|------|------|------|
| `sender` | 发件人邮箱 | `"sender@qq.com"` |
| `password` | 邮箱密码或应用专用密码 | - |
| `smtp_server` | SMTP 服务器地址 | `"smtp.qq.com"` |
| `smtp_port` | SMTP 端口 | `587` (TLS), `465` (SSL) |
| `use_tls` | 是否使用 TLS | `True` |

#### GENERAL_CONFIG - 通用配置
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `days_lookback` | 回溯天数 | `1` |
| `max_papers_per_user` | 每用户最大处理论文数 | `50` |

#### USERS_CONFIG - 用户配置（列表）
每个用户可配置以下字段：

| 参数 | 必填 | 说明 |
|------|------|------|
| `name` | ✓ | 用户组名称 |
| `email` | ✓ | 接收邮箱（多个用逗号分隔） |
| `arxiv_categories` | ✓ | ArXiv 分类列表，如 `["cs.LG", "cs.AI"]` |
| `custom_prompt` | ✗ | 自定义总结提示词，`{text}` 为占位符 |
| `interest_filter_prompt` | ✗ | 兴趣过滤提示词，`{abstract}` 为占位符 |

### ArXiv 分类代码

常用分类代码参考：

**计算机科学 (cs.XX)**
- `cs.AI` - 人工智能
- `cs.LG` - 机器学习
- `cs.CV` - 计算机视觉
- `cs.CL` - 计算语言学
- `cs.RO` - 机器人
- `cs.CR` - 密码学与安全

**量化金融 (q-fin.XX)**
- `q-fin.CP` - 计算金融
- `q-fin.PM` - 投资组合管理
- `q-fin.ST` - 统计金融
- `q-fin.TR` - 交易与市场微观结构

**经济学 (econ.XX)**
- `econ.EM` - 计量经济学
- `econ.GN` - 通用经济学
- `econ.TH` - 理论经济学

**物理学**
- `hep-th` - 高能物理理论
- `gr-qc` - 广义相对论与量子宇宙学
- `astro-ph.CO` - 宇宙学与非银河系天体物理

更多分类请访问 [ArXiv 官网](https://arxiv.org/category_taxonomy)。

## 🚀 运行项目

### 1. 定时运行（推荐）
配置好 `config.py` 后，在项目根目录执行：
```bash
python main.py
```

程序将在每天下午 4:00 自动执行任务（可在 `main.py:410` 修改 `CronTrigger` 的时间）。

### 2. 立即执行一次（测试用）
如需立即执行，取消 `main.py` 末尾的注释：
```python
if __name__ == "__main__":
    # 立即执行一次
    daily_job()

    # 启动定时任务
    # run_scheduler()
```

### 3. 测试邮件发送
运行测试脚本：
```bash
python test_email.py
```

## 📄 输出说明

### 邮件报告格式

邮件包含两部分：

**1. 主体部分**：详细总结感兴趣的论文
```markdown
## 📄论文标题
Title of the Paper

## 📊 论文信息
* 作者: Author1, Author2
* 发表日期: 2025-10-15
* 链接: https://arxiv.org/abs/xxxx.xxxxx
* 主要分类: cs.LG
* 摘要原文: ...

## 📝 论文总结
[AI 生成的详细总结]
```

**2. 附录部分**（如果启用了兴趣过滤）
```markdown
## 📋 附录：其他论文（未通过兴趣过滤）
以下论文未通过 AI 兴趣过滤，仅供参考审查：

### 1. Paper Title
**作者**: ...
**摘要**: ...
```

### 本地报告文件

每个用户组会在 `temp/<用户名>/report.md` 生成独立的报告文件。

## 🔧 高级使用

### 自定义提示词示例

**详细分析型**（适合深度研究）：
```python
"custom_prompt": """请详细分析以下论文：
1. 中文翻译
2. 创新点（列出 3-5 个）
3. 理论框架与推导
4. 实验设计与结果
5. 结论与影响
6. 主要参考文献

论文内容：{text}"""
```

**简洁摘要型**（适合快速浏览）：
```python
"custom_prompt": """用 200-300 字简洁总结这篇论文的核心内容。
论文内容：{text}"""
```

### 兴趣过滤提示词示例

**宽泛过滤**：
```python
"interest_filter_prompt": """这篇论文是否与机器学习相关？
摘要：{abstract}
请回答"是"或"否"。"""
```

**精确过滤**：
```python
"interest_filter_prompt": """判断用户是否对这篇论文感兴趣。
用户兴趣：强化学习中的策略梯度方法、Actor-Critic 算法、多智能体强化学习
摘要：{abstract}
如果论文直接涉及上述具体方向，回答"是"；否则回答"否"。"""
```

## 📊 工作流程

```
1. 从 ArXiv 获取论文列表
         ↓
2. [可选] AI 兴趣过滤（根据摘要）
         ↓
3. 应用硬截断（max_papers_per_user）
         ↓
4. 下载论文全文（PDF/HTML）
         ↓
5. AI 深度总结
         ↓
6. 生成邮件报告（包含主体 + 附录）
         ↓
7. 发送邮件 + 保存本地文件
```

## 🤝 贡献

欢迎提交 Pull Requests 或 Issues 来改进此项目。

## 📄 许可证

本项目采用 MIT License。
