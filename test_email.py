from main import send_email

import asyncio

if __name__ == "__main__":
    # 创建一个简单的测试邮件内容
    subject = "测试邮件"
    with open("report.md", "r", encoding="utf-8") as f:
        body = f.read()

    # 异步发送邮件
    result = asyncio.run(send_email("每日ArXiv论文报告", body))

    if result:
        print("邮件发送成功")
    else:
        print("邮件发送失败")