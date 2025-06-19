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
from bs4 import BeautifulSoup
import subprocess



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
    # Get the target date (exactly days_lookback days ago)
    target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=CONFIG["days_lookback"])
    
    for result in client.results(search):
        print(f"Processing paper: {result.title} published on {result.published}")
        # Check if the paper was published on the target date
        published_dt = result.published.replace(tzinfo=None)
        if target_date <= published_dt :
            papers.append({
                "title": result.title,
                "url": result.entry_id,
                "pdf_url": result.pdf_url,
                "abstract": result.summary,
                "authors": [a.name for a in result.authors],
                "published": result.published,
                "categories": [c for c in result.categories],
                "primary_category": result.primary_category if result.primary_category else None
            })
    print(f"Found {len(papers)} papers published from {target_date.strftime('%Y-%m-%d')}")
    return papers

def download_pdf(url, filename, max_retries=3):
    """下载PDF文件，带有重试机制"""
        # 确保URL是正确的PDF链接
    if 'arxiv.org' in url and not url.endswith('.pdf'):
        # 从URL提取论文ID
        paper_id = url.split('/')[-1]
        url = f"https://arxiv.org/pdf/{paper_id}.pdf"
    
    print(f"尝试下载: {url}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)  # 添加超时参数
            
            # 检查响应是否成功且内容类型是PDF
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'pdf' not in content_type.lower() and len(response.content) < 10000:
                    print(f"警告: 响应可能不是PDF文件 (Content-Type: {content_type})")
                
                with open(filename, 'wb') as f:
                    f.write(response.content)
                
                # 验证文件大小
                file_size = os.path.getsize(filename)
                if file_size < 1000:  # 小于1KB可能有问题
                    print(f"警告: 下载的文件过小 ({file_size} 字节)")
                    continue
                
                return True
            else:
                print(f"下载失败: HTTP状态码 {response.status_code}")
        except Exception as e:
            print(f"尝试 {attempt+1}/{max_retries} 失败: {str(e)}")
        
        # 如果不是最后一次尝试，则等待一段时间再重试
        if attempt < max_retries - 1:
            time.sleep(2 * (attempt + 1))  # 指数退避
    
    return False

def extract_text_from_pdf(pdf_path, paper):
    """从PDF提取文本，增加错误处理"""
    text = ""
    try:
        with open(pdf_path, 'rb') as f:
            try:
                reader = PdfReader(f)
                for page_num, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    except Exception as e:
                        print(f"无法提取第 {page_num+1} 页: {str(e)}")
            except Exception as e:
                print(f"PDF解析失败: {str(e)}")
                # 如果是EOF错误，尝试使用另一种方法
                if "EOF" in str(e):
                    # 可以尝试使用其他库如pdfminer或pdfplumber
                    print("尝试备用PDF解析方法")
                    # 这里可以添加备用解析代码
    except Exception as e:
        print(f"无法打开PDF文件: {str(e)}")
    
    return text

def download_pdf_and_extract_text(paper):
    """下载PDF并提取文本，增加错误处理"""
    pdf_path = f"temp/{paper['title']}.pdf"
    if download_pdf(paper['pdf_url'], pdf_path):
        text = extract_text_from_pdf(pdf_path, paper)
        if not text:
            print(f"警告: 无法从 {paper['title']} 提取文本")
        return text
    else:
        print(f"错误: 无法下载 {paper['title']} 的PDF")
        return ""

def download_html_and_extract_text(paper):
    """从arxiv下载HTML版本，保存为PDF，然后提取文本"""
    try:
        # 从paper URL生成HTML链接
        url = paper['url']
        if 'arxiv.org' in url:
            paper_id = url.split('/')[-1]
            html_url = f"https://arxiv.org/html/{paper_id}"
        else:
            html_url = url.replace('.pdf', '.html')
        
        print(f"尝试下载HTML: {html_url}")
        
        # 下载HTML内容
        response = requests.get(html_url, timeout=30)
        
        if response.status_code == 200:
            # 创建一个临时HTML文件
            temp_html_path = f"temp/{paper['title']}_temp.html"
            with open(temp_html_path, 'wb') as f:
                f.write(response.content)
            
            # 使用wkhtmltopdf将HTML转换为PDF (需要安装wkhtmltopdf)
            pdf_path = f"temp/{paper['title']}_from_html.pdf"
            try:
                subprocess.run(['wkhtmltopdf', temp_html_path, pdf_path], 
                              check=True, timeout=60)
                print(f"已将HTML转换为PDF: {pdf_path}")
                
                # 尝试从生成的PDF提取文本
                pdf_text = extract_text_from_pdf(pdf_path, paper)
                if pdf_text and len(pdf_text) > 1000:
                    return pdf_text
            except Exception as pdf_err:
                print(f"HTML转PDF失败: {str(pdf_err)}")
            
            # 如果PDF转换失败或提取文本不足，则直接从HTML提取
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 移除脚本和样式元素
            for script in soup(["script", "style"]):
                script.extract()
                
            # 获取文本
            text = soup.get_text(separator="\n", strip=True)
            
            # 处理空白字符
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            print(f"从HTML提取了 {len(text)} 字符的文本")
            return text
        else:
            print(f"HTML下载失败: HTTP状态码 {response.status_code}")
            return ""
    except Exception as e:
        print(f"HTML处理错误: {str(e)}")
        return ""

def get_paper_text(paper):
    """尝试多种方式获取论文文本内容"""
    # 首先尝试PDF方式
    text = download_pdf_and_extract_text(paper)
    
    # 如果PDF方式失败，尝试HTML方式
    if not text or len(text) < 1000:  # 内容太少可能是提取失败
        print(f"PDF提取失败或内容太少，尝试HTML方式")
        text = download_html_and_extract_text(paper)

    # 如果text长于129024 则截断
    if len(text) > 129024:
        print(f"文本内容过长，截断到前129024字符")
        text = text[:129024]
    if not text:
        text = paper['abstract']  # 如果所有方法都失败，使用摘要作为最后的fallback
    
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

    请严格按照上述格式输出，注意使用markdown格式进行排版，不要输出任何额外标记。"""

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
            text = get_paper_text(paper)

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
* **主要分类**: {paper["primary_category"] if "primary_category" in paper else "未知分类"}
* **所属分类**: {paper["categories"] if "categories" in paper else "未知分类"}


## 📝 论文总结
{summary}

{'─' * 80}
""")
        except Exception as e:
            print(f"处理论文失败: {paper['title']}，错误: {str(e)}")
            # 发送邮件通知处理失败
            report.append(f"处理论文失败: {paper['title']}，错误: {str(e)}")
    
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
    daily_job()
    
    # 启动定时任务
    run_scheduler()