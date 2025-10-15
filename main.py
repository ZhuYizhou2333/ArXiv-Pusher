import os
import requests
from datetime import datetime, timedelta
from arxiv import Client, Search, SortCriterion, SortOrder
from PyPDF2 import PdfReader
import openai

from config import AI_CONFIG, EMAIL_SERVER_CONFIG, GENERAL_CONFIG, USERS_CONFIG, DEFAULT_PROMPT_TEMPLATE

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



async def send_email(subject, content, receiver_email):
    """发送邮件通知（异步版本）"""
    # 将Markdown内容转换为HTML
    html_content = markdown2.markdown(content, extras=["tables", "mathjax", "fenced-code-blocks"])
    msg = MIMEText(html_content, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SERVER_CONFIG["sender"]
    msg["To"] = receiver_email

    server = None
    try:
        logger.info(f"正在连接SMTP服务器，发送给 {receiver_email}...")
        # 将SMTP操作放在线程池中执行，以避免阻塞事件循环
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: _send_email_sync(msg, server, receiver_email)
        )
    except Exception as e:
        logger.error(f"邮件发送失败: {str(e)}")
        logger.error(f"错误类型: {type(e).__name__}")
        return False


def _send_email_sync(msg, server=None, receiver_email=None):
    """同步发送邮件的内部函数"""
    try:
        server = smtplib.SMTP(
            EMAIL_SERVER_CONFIG["smtp_server"], EMAIL_SERVER_CONFIG["smtp_port"], timeout=10
        )
        server.starttls()  # 启用TLS加密
        server.login(EMAIL_SERVER_CONFIG["sender"], EMAIL_SERVER_CONFIG["password"])

        if receiver_email.count(",") > 0:
            receivers = receiver_email.split(",")
            server.sendmail(EMAIL_SERVER_CONFIG["sender"], receivers, msg.as_string())
        else:
            server.sendmail(
                EMAIL_SERVER_CONFIG["sender"], [receiver_email], msg.as_string()
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


def fetch_papers(arxiv_categories):
    """获取指定分类的论文"""
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
    # Get the target date (previous workday)
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    target_date = today - timedelta(days=GENERAL_CONFIG["days_lookback"])

    # Adjust if yesterday was a weekend
    weekday = target_date.weekday()  # 0-6, where 5 is Saturday and 6 is Sunday
    if weekday >= 5:  # If Saturday or Sunday
        # Go back to Friday (4)
        target_date -= timedelta(days=weekday - 4)

    logger.info(f"Target date set to previous workday: {target_date.strftime('%Y-%m-%d')}")
    for result in client.results(search):
        logger.info(f"Processing paper: {result.title} published on {result.published}")
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
    logger.success(f"Found {len(papers)} papers published from {target_date.strftime('%Y-%m-%d')}")
    return papers

def download_pdf(url, filename, max_retries=3):
    """下载PDF文件，带有重试机制"""
        # 确保URL是正确的PDF链接
    if 'arxiv.org' in url and not url.endswith('.pdf'):
        # 从URL提取论文ID
        paper_id = url.split('/')[-1]
        url = f"https://arxiv.org/pdf/{paper_id}.pdf"
    
    logger.info(f"尝试下载: {url}")
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=30)  # 添加超时参数
            
            # 检查响应是否成功且内容类型是PDF
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'pdf' not in content_type.lower() and len(response.content) < 10000:
                    logger.warning(f"响应可能不是PDF文件 (Content-Type: {content_type})")
                
                with open(filename, 'wb') as f:
                    f.write(response.content)
                
                # 验证文件大小
                file_size = os.path.getsize(filename)
                if file_size < 1000:  # 小于1KB可能有问题
                    logger.warning(f"下载的文件过小 ({file_size} 字节)")
                    continue
                
                return True
            else:
                logger.error(f"下载失败: HTTP状态码 {response.status_code}")
        except Exception as e:
            logger.warning(f"尝试 {attempt+1}/{max_retries} 失败: {str(e)}")
        
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
                        logger.warning(f"无法提取第 {page_num+1} 页: {str(e)}")
            except Exception as e:
                logger.error(f"PDF解析失败: {str(e)}")
                # 如果是EOF错误，尝试使用另一种方法
                if "EOF" in str(e):
                    # 可以尝试使用其他库如pdfminer或pdfplumber
                    logger.info("尝试备用PDF解析方法")
                    # 这里可以添加备用解析代码
    except Exception as e:
        logger.error(f"无法打开PDF文件: {str(e)}")
    
    return text

def download_pdf_and_extract_text(paper, user_dir):
    """下载PDF并提取文本，增加错误处理"""
    pdf_path = f"{user_dir}/{paper['title']}.pdf"
    if download_pdf(paper['pdf_url'], pdf_path):
        text = extract_text_from_pdf(pdf_path, paper)
        if not text:
            logger.warning(f"警告: 无法从 {paper['title']} 提取文本")
        return text
    else:
        logger.error(f"错误: 无法下载 {paper['title']} 的PDF")
        return ""

def download_html_and_extract_text(paper, user_dir):
    """从arxiv下载HTML版本，保存为PDF，然后提取文本"""
    try:
        # 从paper URL生成HTML链接
        url = paper['url']
        if 'arxiv.org' in url:
            paper_id = url.split('/')[-1]
            html_url = f"https://arxiv.org/html/{paper_id}"
        else:
            html_url = url.replace('.pdf', '.html')

        logger.info(f"尝试下载HTML: {html_url}")

        # 下载HTML内容
        response = requests.get(html_url, timeout=30)

        if response.status_code == 200:
            # 创建一个临时HTML文件
            temp_html_path = f"{user_dir}/{paper['title']}_temp.html"
            with open(temp_html_path, 'wb') as f:
                f.write(response.content)

            # 使用wkhtmltopdf将HTML转换为PDF (需要安装wkhtmltopdf)
            pdf_path = f"{user_dir}/{paper['title']}_from_html.pdf"
            try:
                subprocess.run(['wkhtmltopdf', temp_html_path, pdf_path],
                              check=True, timeout=60)
                logger.info(f"已将HTML转换为PDF: {pdf_path}")
                
                # 尝试从生成的PDF提取文本
                pdf_text = extract_text_from_pdf(pdf_path, paper)
                if pdf_text and len(pdf_text) > 1000:
                    return pdf_text
            except Exception as pdf_err:
                logger.error(f"HTML转PDF失败: {str(pdf_err)}")
            
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
            
            logger.info(f"从HTML提取了 {len(text)} 字符的文本")
            return text
        else:
            logger.error(f"HTML下载失败: HTTP状态码 {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"HTML处理错误: {str(e)}")
        return ""

def get_paper_text(paper, user_dir):
    """尝试多种方式获取论文文本内容"""
    # 首先尝试PDF方式
    text = download_pdf_and_extract_text(paper, user_dir)

    # 如果PDF方式失败，尝试HTML方式
    if not text or len(text) < 1000:  # 内容太少可能是提取失败
        logger.info(f"PDF提取失败或内容太少，尝试HTML方式")
        text = download_html_and_extract_text(paper, user_dir)

    # 如果text长于129024 则截断
    if len(text) > 129024:
        logger.warning(f"文本内容过长，截断到前129024字符")
        text = text[:129024]
    if not text:
        text = paper['abstract']  # 如果所有方法都失败，使用摘要作为最后的fallback

    return text

def gpt_check_interest(abstract, interest_filter_prompt):
    """使用GPT判断用户是否对论文感兴趣

    Args:
        abstract: 论文摘要
        interest_filter_prompt: 兴趣过滤提示词，需包含{abstract}占位符

    Returns:
        bool: True表示感兴趣，False表示不感兴趣
    """
    prompt = interest_filter_prompt.format(abstract=abstract)

    client = openai.OpenAI(
        base_url=AI_CONFIG["base_url"],
        api_key=AI_CONFIG["api_key"]
    )

    logger.info(f"检查论文兴趣度...")
    try:
        response = client.chat.completions.create(
            model=AI_CONFIG["model"],
            messages=[{
                "role": "user",
                "content": prompt
            }],
            temperature=0.3,  # 降低温度以获得更一致的判断
        )

        answer = response.choices[0].message.content.strip().lower()
        logger.info(f"兴趣判断结果: {answer}")

        # 判断AI回复是否表示感兴趣
        # 支持多种可能的回答形式
        interested = any(keyword in answer for keyword in ['是', 'yes', '感兴趣', '有兴趣', 'interested'])
        not_interested = any(keyword in answer for keyword in ['否', 'no', '不感兴趣', '无兴趣', 'not interested'])

        if interested and not not_interested:
            return True
        elif not_interested and not interested:
            return False
        else:
            # 如果无法明确判断，默认为感兴趣（保守策略）
            logger.warning(f"无法明确判断兴趣，默认为感兴趣。AI回复: {answer}")
            return True

    except Exception as e:
        logger.error(f"兴趣判断失败: {str(e)}，默认为感兴趣")
        return True  # 出错时默认为感兴趣

def gpt_summarize(text, custom_prompt=None):
    """使用GPT对论文进行总结，支持自定义提示词"""
    # 如果没有自定义提示词，使用默认模板
    if custom_prompt:
        prompt = custom_prompt.format(text=text)
    else:
        prompt = DEFAULT_PROMPT_TEMPLATE.format(text=text)

    client = openai.OpenAI(
        base_url=AI_CONFIG["base_url"],
        api_key=AI_CONFIG["api_key"]
    )

    logger.info(f"Requesting GPT to summarize: {text[:100]}...")
    logger.info(f"Request length: {len(text)}")
    response = client.chat.completions.create(
        model=AI_CONFIG["model"],
        messages=[{
            "role": "user",
            "content": prompt
        }],
        temperature=1.5,
    )
    logger.info(f"Response: {response.choices[0].message.content[:100]}...")
    logger.info(f"Response length: {len(response.choices[0].message.content)}")

    # Remove any code blocks from the response
    content = response.choices[0].message.content
    cleaned_content = ""
    in_code_block = False
    for line in content.split('\n'):
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            cleaned_content += line + '\n'
    return response.choices[0].message.content

def build_filtered_papers_appendix(filtered_out_papers):
    """构建被过滤论文的附录

    Args:
        filtered_out_papers: 被过滤掉的论文列表

    Returns:
        str: 格式化的附录内容
    """
    if not filtered_out_papers:
        return ""

    appendix = ["\n\n" + "=" * 80]
    appendix.append("\n## 📋 附录：其他论文（未通过兴趣过滤）")
    appendix.append("\n以下论文未通过AI兴趣过滤，仅供参考审查：\n")

    for i, paper in enumerate(filtered_out_papers, 1):
        appendix.append(f"\n### {i}. {paper['title']}\n")
        appendix.append(f"**作者**: {', '.join(paper['authors'])}\n")
        appendix.append(f"**发表日期**: {paper['published'].strftime('%Y-%m-%d')}\n")
        appendix.append(f"**链接**: [{paper['url']}]({paper['url']})\n")
        appendix.append(f"**主要分类**: {paper.get('primary_category', '未知分类')}\n")
        appendix.append(f"\n**摘要**:\n{paper['abstract']}\n")
        appendix.append("\n" + "─" * 80 + "\n")

    return ''.join(appendix)

def process_user(user_config):
    """处理单个用户的论文获取和报告生成"""
    user_name = user_config["name"]
    user_email = user_config["email"]
    arxiv_categories = user_config["arxiv_categories"]
    custom_prompt = user_config.get("custom_prompt", None)
    interest_filter_prompt = user_config.get("interest_filter_prompt", None)

    logger.info(f"开始处理用户: {user_name}")

    # 为每个用户创建独立的临时目录
    user_dir = f"temp/{user_name.replace(' ', '_')}"
    os.makedirs(user_dir, exist_ok=True)

    # 获取该用户关注的论文
    papers = fetch_papers(arxiv_categories)

    if not papers:
        logger.info(f"用户 {user_name} 没有找到新论文")
        return

    # 第一步：如果配置了兴趣过滤提示词，先根据摘要过滤论文
    filtered_out_papers = []  # 存储被过滤掉的论文
    if interest_filter_prompt:
        logger.info(f"开始使用兴趣过滤，共 {len(papers)} 篇论文待过滤")
        filtered_papers = []
        for i, paper in enumerate(papers):
            logger.info(f"过滤论文 {i+1}/{len(papers)}: {paper['title']}")
            try:
                is_interested = gpt_check_interest(paper['abstract'], interest_filter_prompt)
                if is_interested:
                    filtered_papers.append(paper)
                    logger.info(f"✓ 用户可能对此论文感兴趣")
                else:
                    filtered_out_papers.append(paper)
                    logger.info(f"✗ 用户可能对此论文不感兴趣，跳过")
            except Exception as e:
                logger.error(f"过滤论文时出错: {str(e)}，保留该论文")
                filtered_papers.append(paper)

        papers = filtered_papers
        logger.info(f"兴趣过滤完成，剩余 {len(papers)} 篇论文，过滤掉 {len(filtered_out_papers)} 篇论文")

        if not papers:
            logger.info(f"用户 {user_name} 经过兴趣过滤后没有感兴趣的论文")
            # 即使没有感兴趣的论文，如果有被过滤的论文，也发送附录
            if filtered_out_papers:
                filtered_appendix = build_filtered_papers_appendix(filtered_out_papers)
                asyncio.run(send_email(f"每日ArXiv论文报告 - {user_name}", filtered_appendix, user_email))
            return

    # 第二步：根据配置限制处理的论文数量（硬截断）
    max_papers = GENERAL_CONFIG.get("max_papers_per_user", None)
    if max_papers is not None and max_papers > 0:
        papers = papers[:max_papers]
        logger.info(f"应用硬截断，用户 {user_name} 最多处理 {max_papers} 篇论文")

    report = []
    for paper in papers:
        try:
            # 下载并处理PDF
            text = get_paper_text(paper, user_dir)

            # GPT总结（使用用户自定义提示词）
            summary = gpt_summarize(text, custom_prompt)

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
* **摘要原文**: 

{paper['abstract']}


## 📝 论文总结
{summary}

{'─' * 80}
""")
        except Exception as e:
            logger.error(f"处理论文失败: {paper['title']}，错误: {str(e)}")
            report.append(f"处理论文失败: {paper['title']}，错误: {str(e)}")

    if report:
        # 构建完整报告，包括被过滤论文的附录
        full_report = '\n'.join(report)

        # 如果有被过滤掉的论文，添加附录
        if filtered_out_papers:
            full_report += "\n\n" + build_filtered_papers_appendix(filtered_out_papers)

        # 发送给该用户
        asyncio.run(send_email(f"每日ArXiv论文报告 - {user_name}", full_report, user_email))

        # 保存报告到用户专属文件
        report_file = f"{user_dir}/report.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(full_report)
        logger.success(f"用户 {user_name} 的报告已发送并保存到 {report_file}")

def daily_job():
    """每日任务：为所有配置的用户处理论文"""
    os.makedirs('temp', exist_ok=True)

    logger.info(f"开始每日任务，共有 {len(USERS_CONFIG)} 个用户")

    for user_config in USERS_CONFIG:
        try:
            process_user(user_config)
        except Exception as e:
            logger.error(f"处理用户 {user_config['name']} 时发生错误: {str(e)}")

    logger.success("所有用户处理完成")

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
    # 配置loguru
    logger.add(
        "arxiv_pusher.log",
        rotation="10 MB",
        level="INFO",
        encoding="utf-8"
    )
    # 如果需要立即运行一次，取消下面的注释
    daily_job()
    
    # 启动定时任务
    run_scheduler()