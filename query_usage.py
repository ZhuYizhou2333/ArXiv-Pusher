#!/usr/bin/env python3
"""
Token使用情况查询工具
用于查询和统计用户的token消耗情况
"""

import argparse
from datetime import datetime, timedelta
from database import get_db
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def format_usage_record(record):
    """格式化单条使用记录（使用 rich 表格输出）"""
    table = Table(show_header=False, box=box.SIMPLE_HEAVY)
    table.add_column("字段", style="bold cyan", no_wrap=True)
    table.add_column("值", style="white")

    # 基本信息
    table.add_row("用户", record["user_name"])
    table.add_row("邮箱", record["user_email"])
    table.add_row("日期", str(record["date"]))
    table.add_row("关注分类", ", ".join(record.get("arxiv_categories", [])))

    # 论文统计
    table.add_section()
    table.add_row("[bold]论文统计[/bold]", "")
    table.add_row("获取论文数", f"{record['papers_fetched']}")
    table.add_row("过滤后保留", f"{record['papers_filtered']}")
    table.add_row("实际处理数", f"{record['papers_processed']}")

    # 过滤阶段
    table.add_section()
    table.add_row("[bold]过滤阶段[/bold]", "")
    table.add_row("输入Token", f"{record['filter_input_tokens']:,}")
    table.add_row("输出Token", f"{record['filter_output_tokens']:,}")
    table.add_row("总计Token", f"{record['filter_total_tokens']:,}")
    table.add_row("成本", f"¥{record['filter_cost']:.4f}")

    # 生成阶段
    table.add_section()
    table.add_row("[bold]生成阶段[/bold]", "")
    table.add_row("输入Token", f"{record['generate_input_tokens']:,}")
    table.add_row("输出Token", f"{record['generate_output_tokens']:,}")
    table.add_row("总计Token", f"{record['generate_total_tokens']:,}")
    table.add_row("成本", f"¥{record['generate_cost']:.4f}")

    # 总计
    table.add_section()
    table.add_row("[bold]总计[/bold]", "")
    table.add_row("总Token数", f"{record['total_tokens']:,}")
    table.add_row("总成本", f"¥{record['total_cost']:.4f}")

    console.print(table)
    console.print()  # 空行分隔


def query_user_today(user_name):
    """查询指定用户今天的使用情况"""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    record = db.get_user_usage_by_date(user_name, today)

    if record:
        console.print(
            Panel.fit(
                f"【{user_name}】今天 ({today}) 的 Token 使用情况",
                style="bold green",
            )
        )
        console.print()
        format_usage_record(record)
    else:
        console.print(f"[yellow]未找到用户 {user_name} 在 {today} 的记录[/yellow]")


def query_user_range(user_name, days):
    """查询指定用户最近N天的使用情况"""
    db = get_db()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")

    records = db.get_user_usage_range(user_name, start_date, end_date)

    if records:
        console.print(
            Panel.fit(
                f"【{user_name}】从 {start_date} 到 {end_date} 的 Token 使用情况",
                style="bold green",
            )
        )
        console.print()
        for record in records:
            format_usage_record(record)

        # 显示汇总
        total_stats = db.get_user_total_cost(user_name, start_date, end_date)

        summary_table = Table(
            title=f"【汇总统计】最近 {days} 天",
            show_header=False,
            box=box.SIMPLE_HEAVY,
        )
        summary_table.add_column("字段", style="bold cyan", no_wrap=True)
        summary_table.add_column("值", style="white")

        summary_table.add_row("总Token数", f"{total_stats['total_tokens']:,}")
        summary_table.add_row("总成本", f"¥{total_stats['total_cost']:.4f}")
        summary_table.add_row(
            "过滤阶段成本", f"¥{total_stats['filter_cost']:.4f}"
        )
        summary_table.add_row(
            "生成阶段成本", f"¥{total_stats['generate_cost']:.4f}"
        )
        summary_table.add_row(
            "总论文获取数", f"{total_stats['papers_fetched']}"
        )
        summary_table.add_row(
            "总论文过滤后", f"{total_stats['papers_filtered']}"
        )
        summary_table.add_row(
            "总论文处理数", f"{total_stats['papers_processed']}"
        )
        summary_table.add_row(
            "平均每天成本", f"¥{total_stats['total_cost'] / days:.4f}"
        )

        console.print(summary_table)
    else:
        console.print(
            f"[yellow]未找到用户 {user_name} 在该时间段的记录[/yellow]"
        )


def query_all_users_today():
    """查询所有用户今天的使用情况"""
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    records = db.get_all_users_usage_by_date(today)

    if records:
        console.print(
            Panel.fit(
                f"所有用户在 {today} 的 Token 使用情况",
                style="bold green",
            )
        )
        console.print()
        total_cost = 0.0
        total_tokens = 0

        for record in records:
            format_usage_record(record)
            total_cost += record["total_cost"]
            total_tokens += record["total_tokens"]

        summary_table = Table(
            title="【今日总计】",
            show_header=False,
            box=box.SIMPLE_HEAVY,
        )
        summary_table.add_column("字段", style="bold cyan", no_wrap=True)
        summary_table.add_column("值", style="white")
        summary_table.add_row("用户数", f"{len(records)}")
        summary_table.add_row("总Token数", f"{total_tokens:,}")
        summary_table.add_row("总成本", f"¥{total_cost:.4f}")

        console.print(summary_table)
    else:
        console.print(f"[yellow]未找到今天的任何记录[/yellow]")


def query_all_users_summary(days=None):
    """查询所有用户的汇总统计"""
    db = get_db()

    if days:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days - 1)).strftime(
            "%Y-%m-%d"
        )
        summary = db.get_all_users_summary(start_date, end_date)
        title = f"所有用户从 {start_date} 到 {end_date} 的汇总统计"
    else:
        summary = db.get_all_users_summary()
        title = "所有用户的历史汇总统计"

    if summary:
        console.print(
            Panel.fit(
                title,
                style="bold green",
            )
        )
        console.print()

        table = Table(
            box=box.SIMPLE_HEAVY,
            title="用户 Token 使用汇总",
        )
        table.add_column("用户名", style="bold cyan", no_wrap=True)
        table.add_column("邮箱", style="white", no_wrap=True)
        table.add_column("总Token", justify="right")
        table.add_column("总成本(¥)", justify="right")
        table.add_column("论文处理数", justify="right")
        table.add_column("记录天数", justify="right")

        total_cost = 0.0
        total_tokens = 0

        for user in summary:
            table.add_row(
                user["user_name"],
                user["user_email"],
                f"{user['total_tokens']:,}",
                f"{user['total_cost']:.2f}",
                f"{user['papers_processed']}",
                f"{user['record_count']}",
            )
            total_cost += user["total_cost"]
            total_tokens += user["total_tokens"]

        console.print(table)

        footer = Table(show_header=False, box=None)
        footer.add_column("字段", style="bold cyan", no_wrap=True)
        footer.add_column("值", style="white")
        footer.add_row("总Token", f"{total_tokens:,}")
        footer.add_row("总成本", f"¥{total_cost:.2f}")
        console.print(footer)
    else:
        console.print("[yellow]未找到任何记录[/yellow]")


def main():
    parser = argparse.ArgumentParser(
        description="Token使用情况查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询指定用户今天的使用情况
  python query_usage.py --user "金融经济研究组" --today

  # 查询指定用户最近7天的使用情况
  python query_usage.py --user "金融经济研究组" --days 7

  # 查询所有用户今天的使用情况
  python query_usage.py --all-today

  # 查询所有用户历史汇总
  python query_usage.py --summary

  # 查询所有用户最近30天的汇总
  python query_usage.py --summary --days 30
        """,
    )

    parser.add_argument("--user", type=str, help="用户名称")
    parser.add_argument("--today", action="store_true", help="查询今天的记录")
    parser.add_argument("--days", type=int, help="查询最近N天的记录")
    parser.add_argument(
        "--all-today", action="store_true", help="查询所有用户今天的记录"
    )
    parser.add_argument(
        "--summary", action="store_true", help="查询所有用户的汇总统计"
    )

    args = parser.parse_args()

    # 移除loguru默认handler，避免不必要的日志输出
    logger.remove()

    try:
        if args.user:
            if args.today:
                query_user_today(args.user)
            elif args.days:
                query_user_range(args.user, args.days)
            else:
                console.print(
                    "[yellow]请指定 --today 或 --days N[/yellow]"
                )
        elif args.all_today:
            query_all_users_today()
        elif args.summary:
            query_all_users_summary(args.days)
        else:
            parser.print_help()

    except Exception as e:
        console.print(f"[red]查询出错: {str(e)}[/red]")


if __name__ == "__main__":
    main()
