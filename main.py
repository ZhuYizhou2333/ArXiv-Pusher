import os
import requests
from datetime import datetime, timedelta
from arxiv import Client, Search, SortCriterion, SortOrder
from PyPDF2 import PdfReader
import openai

from config import CONFIG, EMAIL_CONFIG

import smtplib
import socket
import asyncio
from email.mime.text import MIMEText
import markdown2  # 导入markdown2库
from loguru import logger
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import time



async def send_email(subject, content):
    """发送邮件通知（异步版本）"""
    # 将Markdown内容转换为HTML
    html_content = markdown2.markdown(content, extras=["tables", "mathjax", "fenced-code-blocks"])
    msg = MIMEText(html_content, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_CONFIG["sender"]
    msg["To"] = EMAIL_CONFIG["receiver"]

    server = None
    try:
        logger.info("正在连接SMTP服务器...")
        # 将SMTP操作放在线程池中执行，以避免阻塞事件循环
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: _send_email_sync(msg, server)
        )
    except Exception as e:
        logger.error(f"邮件发送失败: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        return False


def _send_email_sync(msg, server=None):
    """同步发送邮件的内部函数"""
    try:
        server = smtplib.SMTP(
            EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"], timeout=10
        )
        server.starttls()  # 启用TLS加密
        server.login(EMAIL_CONFIG["sender"], EMAIL_CONFIG["password"])

        if EMAIL_CONFIG["receiver"].count(",") > 0:
            receivers = EMAIL_CONFIG["receiver"].split(",")
            server.sendmail(EMAIL_CONFIG["sender"], receivers, msg.as_string())
        else:
            server.sendmail(
                EMAIL_CONFIG["sender"], [EMAIL_CONFIG["receiver"]], msg.as_string()
            )

        logger.success("邮件发送成功")
        return True
    except socket.timeout:
        logger.warning("连接SMTP服务器超时，跳过本次邮件发送")
        return False
    except smtplib.SMTPException as e:
        logger.error(
            f"SMTP错误: {e.smtp_error.decode() if hasattr(e, 'smtp_error') else str(e)}"
        )
        return False
    except Exception as e:
        logger.error(f"邮件发送失败: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        return False
    finally:
        if server:
            try:
                server.quit()
            except Exception as e:
                logger.warning(f"关闭SMTP连接时发生错误: {str(e)}")


def fetch_papers():
    # 从配置中获取 arXiv 分类
    arxiv_categories = CONFIG["arxiv_categories"]
    # 构建搜索查询，只包含配置中的主题
    search_query = " OR ".join([f"cat:{cat}" for cat in arxiv_categories])
    client = Client()  # 创建客户端实例
    search = Search(
        query=search_query,
        sort_by=SortCriterion.SubmittedDate,
        sort_order=SortOrder.Descending,
        max_results=100
    )
    
    papers = []
    cutoff_date = datetime.now() - timedelta(days=CONFIG["days_lookback"])
    
    for result in client.results(search):
        print(f"Processing paper: {result.title} published on {result.published}")
        if result.published.replace(tzinfo=None) > cutoff_date:
            papers.append({
                "title": result.title,
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "abstract": result.summary,
                "authors": [a.name for a in result.authors],
                "published": result.published
            })
    print(f"Found {len(papers)} papers.")
    return papers

def download_pdf(url, filename):
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)

def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text

def gpt_summarize(text):
    prompt = f"""请你担任量化金融领域学术论文助理，用中文针对下列论文内容进行详细总结，并输出以下结构：
    1. 中文翻译：对论文摘要进行准确、流畅的中文翻译；
    2. 创新点：列出 3 个关键创新点，并说明其重要性；
    3. 理论与方法：详细描述论文采用的主要理论框架，推导步骤和研究方法，必要时可以使用简单的公式；
    4. 实验与结果：描述论文采取的核心实验设计、数据结果，可以使用表格以清晰地展现不同方法的效果对比；
    5. 结论与影响：仔细列出论文的所有的关键研究结论；
    6. 主要参考文献：列举并简要介绍论文中引用的 2-3 篇核心参考文献，并指出其对本研究的贡献。

    论文原文内容如下：
    {text}

    请严格按照上述格式输出，注意使用markdown格式进行排版。"""

    client = openai.OpenAI(
        base_url=CONFIG["base_url"],
        api_key=CONFIG["api_key"]
    )

    print(f"Requesting GPT to summarize: {text[:100]}...")
    print(f"Request length: {len(text)}")
    response = client.chat.completions.create(
        model=CONFIG["model"],
        messages=[{
            "role": "user",
            "content": prompt
        }],
    )
    print(f"Response: {response.choices[0].message.content[:100]}...")
    print(f"Response length: {len(response.choices[0].message.content)}")
    return response.choices[0].message.content

def daily_job():
    os.makedirs('temp', exist_ok=True)
    report = []
    papers = fetch_papers()
    
    for paper in papers:
        try:
            # 下载并处理PDF
            pdf_path = f"temp/{paper['title']}.pdf"
            download_pdf(paper['pdf_url'], pdf_path)
            text = extract_text_from_pdf(pdf_path)

            # GPT总结
            summary = gpt_summarize(text)
            # os.remove(pdf_path)  # 清理临时文件

            # 构建报告
            report.append(f"""
## 📄论文标题

{paper['title']}

## 📊 论文信息
* **作者**: {', '.join(paper['authors'])}
* **发表日期**: {paper['published'].strftime('%Y-%m-%d')}
* **链接**: [{paper['url']}]({paper['url']})

## 📝 论文总结
{summary}

{'─' * 80}
""")
        except Exception as e:
            print(f"处理论文失败: {paper['title']}，错误: {str(e)}")
    
    if report:
        asyncio.run(send_email("每日ArXiv论文报告", '\n'.join(report)))
        with open('report.md', 'w', encoding='utf-8') as f:
            f.write('\n'.join(report))
        print("Reports sent.")

def run_scheduler():
    scheduler = BlockingScheduler()
    scheduler.add_job(
        daily_job, 
        trigger=CronTrigger(hour=16, minute=0),  # 每天下午4点运行
        id='daily_arxiv_job',
        name='Daily ArXiv paper collection and summary'
    )
    
    logger.info("定时任务已设置，每天下午4:00运行")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("定时任务调度器已停止")

if __name__ == "__main__":
    # 如果需要立即运行一次，取消下面的注释
    # daily_job()
    
    # 启动定时任务
    run_scheduler()