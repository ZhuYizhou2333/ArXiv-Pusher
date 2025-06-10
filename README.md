# ArXiv Pusher

每日自动从 ArXiv 拉取指定分类的最新论文，使用大语言模型进行总结，并将报告推送到您的邮箱。同时会在本地生成一份 Markdown 格式的报告。

## ✨ 功能特性

*   **自动拉取**：每日定时从 ArXiv 获取用户指定分类下的最新论文。
*   **智能总结**：利用大语言模型（如 OpenAI GPT 系列、通义千问等）对论文进行深度分析和总结，包括：
    *   摘要的中文翻译
    *   关键创新点提炼
    *   核心理论与方法阐述
    *   实验设计与结果展示
    *   主要研究结论
    *   重要参考文献解读
*   **邮件推送**：将生成的论文总结报告通过邮件发送给指定用户。
*   **本地报告**：在项目根目录生成 `report.md` 文件，方便本地查阅。
*   **高度可配置**：
    *   自定义 ArXiv 论文分类和回顾天数。
    *   灵活配置 AI 模型的 API Key、Base URL 及具体模型。
    *   详细配置邮件发送参数（发件人、收件人、SMTP 服务器等）。
*   **定时执行**：基于 `apscheduler` 实现每日定时执行任务。

## ⚙️ 安装与依赖

1.  **Python 环境**：请确保您已安装 Python (建议 3.7+)。
2.  **克隆项目** (如果您是通过 git 获取):
    ```bash
    git clone <your-repository-url>
    cd ArXiv-Pusher
    ```
3.  **安装依赖**:
    项目依赖以下 Python 包：
    *   `requests`
    *   `arxiv`
    *   `PyPDF2`
    *   `openai`
    *   `markdown2`
    *   `loguru`
    *   `apscheduler`

    建议创建一个 `requirements.txt` 文件并使用 `pip install -r requirements.txt` 安装。
    您可以根据 [`main.py`](main.py:1) 中的 `import` 语句手动安装：
    ```bash
    pip install requests arxiv PyPDF2 openai markdown2 loguru apscheduler
    ```

## 🛠️ 配置说明

在项目根目录下创建 `config.py` 文件，并填入以下配置信息。请根据您的实际情况修改。

```python
# config.py

CONFIG = {
    # ArXiv 相关设置
    "arxiv_categories": ["cs.AI", "cs.CL", "cs.LG"],  # 您感兴趣的 ArXiv 分类，例如：["cs.AI", "cs.SY"]
    "days_lookback": 1,  # 回顾过去多少天的论文

    # 大语言模型相关设置
    "api_key": "sk-your_api_key_here",  # 您的 AI 服务 API Key
    "base_url": "https://api.openai.com/v1",  # AI 服务的 API Base URL
    "model": "gpt-4-turbo"  # 使用的 AI 模型，例如 "gpt-4", "qwen-plus"
}

EMAIL_CONFIG = {
    "sender": "your_email@example.com",  # 发件人邮箱地址
    "password": "your_email_password_or_app_specific_password",  # 发件人邮箱密码或应用专用密码
    "receiver": "receiver_email@example.com",  # 收件人邮箱地址 (多个邮箱请用英文逗号 "," 分隔)
    "smtp_server": "smtp.example.com",  # SMTP 服务器地址，例如 "smtp.qq.com", "smtp.gmail.com"
    "smtp_port": 587,  # SMTP 服务器端口 (通常 SSL 为 465, TLS 为 587)
    "use_tls": True,  # 是否使用 TLS 加密 (main.py 中默认为 True)
}
```

**配置项说明:**

*   **`CONFIG`**:
    *   `arxiv_categories`: 一个包含 ArXiv 分类代码的列表。您可以在 [ArXiv 官网](https://arxiv.org/archive/cs) 找到所有分类。
    *   `days_lookback`: 指定程序回顾过去多少天内发布的论文。
    *   `api_key`: 您所使用的大语言模型服务的 API 密钥。
    *   `base_url`: 大语言模型服务的 API 接入点。
    *   `model`: 指定使用的大语言模型名称。

*   **`EMAIL_CONFIG`**:
    *   `sender`: 用于发送报告的邮箱地址。
    *   `password`: 发件人邮箱的密码或为第三方客户端生成的应用专用密码。
    *   `receiver`: 接收报告的邮箱地址。如果需要发送给多个收件人，请使用英文逗号 `,` 分隔。
    *   `smtp_server`: 您发件邮箱对应的 SMTP 服务器地址。
    *   `smtp_port`: SMTP 服务器的端口号。
    *   `use_tls`: [`main.py`](main.py:1) 中的邮件发送逻辑默认启用 TLS 加密。

## 🚀 运行项目

1.  **运行主程序**:
    配置好 `config.py` 后，在项目根目录下执行：
    ```bash
    python main.py
    ```
    程序将根据 `config.py` 中的设置，在每日下午 4:00（默认，可在 [`main.py`](main.py:203) 中修改 `CronTrigger`）自动执行论文拉取、总结和邮件发送任务。
    日志信息会输出到控制台。

2.  **立即执行一次任务** (用于测试或首次运行):
    如果您想立即执行一次任务而不是等待定时器，可以取消 [`main.py`](main.py:216) 文件中 `daily_job()` 的注释，然后运行 `python main.py`。
    ```python
    # main.py
    # ...
    if __name__ == "__main__":
        # 如果需要立即运行一次，取消下面的注释
        daily_job() # <--- 取消此行注释

        # 启动定时任务 (如果同时取消了 daily_job() 的注释，可以暂时注释掉 run_scheduler())
        # run_scheduler()
    ```

3.  **测试邮件发送功能**:
    如果您想单独测试邮件发送是否配置正确，可以运行：
    ```bash
    python test_email.py
    ```
    此脚本会尝试读取本地的 `report.md` (如果存在) 作为邮件内容进行发送。

## 📄 输出

*   **邮件通知**：每日的论文总结报告将发送到您在 `EMAIL_CONFIG` 中配置的收件人邮箱。
*   **本地报告文件**：每次成功执行任务后，会在项目根目录下生成或更新 `report.md` 文件，包含最新的论文总结。

## 🤝 贡献

欢迎提交 Pull Requests 或 Issues 来改进此项目。

## 📄 许可证

本项目采用 [MIT License](LICENSE) (如果您的项目有 LICENSE 文件，请链接到它，否则可以移除此句或选择一个许可证)。
