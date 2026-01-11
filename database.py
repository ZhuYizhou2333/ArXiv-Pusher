"""
数据库模块 - 用于记录用户每日token消耗情况
"""
import sqlite3
import json
import threading
from datetime import datetime
from loguru import logger
from typing import Optional, Dict, List


class TokenUsageDB:
    """Token使用情况数据库管理类"""

    def __init__(self, db_path: str = "token_usage.db"):
        """初始化数据库连接

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self._init_db()

    def _init_db(self):
        """初始化数据库连接和表结构"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # 使查询结果可以通过列名访问
            self._create_tables()
            logger.info(f"数据库初始化成功: {self.db_path}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            raise

    def _create_tables(self):
        """创建数据库表"""
        cursor = self.conn.cursor()

        # 创建用户token使用记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                user_email TEXT NOT NULL,
                date DATE NOT NULL,
                arxiv_categories TEXT,

                -- 分类(兴趣过滤)阶段统计
                filter_input_tokens INTEGER DEFAULT 0,
                filter_output_tokens INTEGER DEFAULT 0,
                filter_total_tokens INTEGER DEFAULT 0,
                filter_cost REAL DEFAULT 0.0,

                -- 解析(论文生成)阶段统计
                generate_input_tokens INTEGER DEFAULT 0,
                generate_output_tokens INTEGER DEFAULT 0,
                generate_total_tokens INTEGER DEFAULT 0,
                generate_cost REAL DEFAULT 0.0,

                -- 总计统计
                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0,

                -- 论文数量统计
                papers_fetched INTEGER DEFAULT 0,
                papers_filtered INTEGER DEFAULT 0,
                papers_processed INTEGER DEFAULT 0,

                -- 记录时间
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                -- 唯一约束：同一用户同一天只有一条记录
                UNIQUE(user_name, date)
            )
        """)

        # 创建索引以提高查询效率
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_date
            ON user_token_usage(user_name, date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_date
            ON user_token_usage(date)
        """)

        self.conn.commit()
        logger.info("数据库表创建成功")

    def record_usage(
        self,
        user_name: str,
        user_email: str,
        arxiv_categories: List[str],
        filter_input_tokens: int,
        filter_output_tokens: int,
        generate_input_tokens: int,
        generate_output_tokens: int,
        filter_cost: float,
        generate_cost: float,
        papers_fetched: int,
        papers_filtered: int,
        papers_processed: int,
        date: Optional[str] = None
    ):
        """记录用户的token使用情况

        Args:
            user_name: 用户名称
            user_email: 用户邮箱
            arxiv_categories: 用户关注的arXiv分类列表
            filter_input_tokens: 分类阶段输入token数
            filter_output_tokens: 分类阶段输出token数
            generate_input_tokens: 解析阶段输入token数
            generate_output_tokens: 解析阶段输出token数
            filter_cost: 分类阶段成本
            generate_cost: 解析阶段成本
            papers_fetched: 获取的论文总数
            papers_filtered: 兴趣过滤后保留的论文数
            papers_processed: 实际处理的论文数
            date: 记录日期，默认为今天
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # 计算总计
        filter_total_tokens = filter_input_tokens + filter_output_tokens
        generate_total_tokens = generate_input_tokens + generate_output_tokens
        total_input_tokens = filter_input_tokens + generate_input_tokens
        total_output_tokens = filter_output_tokens + generate_output_tokens
        total_tokens = total_input_tokens + total_output_tokens
        total_cost = filter_cost + generate_cost

        # 将分类列表转为JSON字符串
        categories_json = json.dumps(arxiv_categories)

        cursor = self.conn.cursor()

        try:
            # 使用 INSERT OR REPLACE 来处理重复记录
            cursor.execute("""
                INSERT OR REPLACE INTO user_token_usage (
                    user_name, user_email, date, arxiv_categories,
                    filter_input_tokens, filter_output_tokens, filter_total_tokens, filter_cost,
                    generate_input_tokens, generate_output_tokens, generate_total_tokens, generate_cost,
                    total_input_tokens, total_output_tokens, total_tokens, total_cost,
                    papers_fetched, papers_filtered, papers_processed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_name, user_email, date, categories_json,
                filter_input_tokens, filter_output_tokens, filter_total_tokens, filter_cost,
                generate_input_tokens, generate_output_tokens, generate_total_tokens, generate_cost,
                total_input_tokens, total_output_tokens, total_tokens, total_cost,
                papers_fetched, papers_filtered, papers_processed
            ))

            self.conn.commit()
            logger.info(f"成功记录用户 {user_name} 在 {date} 的token使用情况")
            logger.info(f"  总计: {total_tokens:,} tokens, 成本: ¥{total_cost:.4f}")

        except Exception as e:
            self.conn.rollback()
            logger.error(f"记录token使用情况失败: {str(e)}")
            raise

    def get_user_usage_by_date(self, user_name: str, date: Optional[str] = None) -> Optional[Dict]:
        """查询指定用户在指定日期的token使用情况

        Args:
            user_name: 用户名称
            date: 查询日期，默认为今天

        Returns:
            包含使用情况的字典，如果不存在则返回None
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM user_token_usage
            WHERE user_name = ? AND date = ?
        """, (user_name, date))

        row = cursor.fetchone()
        if row:
            result = dict(row)
            # 将JSON字符串转回列表
            if result.get('arxiv_categories'):
                result['arxiv_categories'] = json.loads(result['arxiv_categories'])
            return result
        return None

    def get_user_usage_range(
        self,
        user_name: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """查询指定用户在日期范围内的token使用情况

        Args:
            user_name: 用户名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            包含使用情况的字典列表
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM user_token_usage
            WHERE user_name = ? AND date BETWEEN ? AND ?
            ORDER BY date
        """, (user_name, start_date, end_date))

        rows = cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            if result.get('arxiv_categories'):
                result['arxiv_categories'] = json.loads(result['arxiv_categories'])
            results.append(result)

        return results

    def get_all_users_usage_by_date(self, date: Optional[str] = None) -> List[Dict]:
        """查询所有用户在指定日期的token使用情况

        Args:
            date: 查询日期，默认为今天

        Returns:
            包含所有用户使用情况的字典列表
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM user_token_usage
            WHERE date = ?
            ORDER BY user_name
        """, (date,))

        rows = cursor.fetchall()
        results = []
        for row in rows:
            result = dict(row)
            if result.get('arxiv_categories'):
                result['arxiv_categories'] = json.loads(result['arxiv_categories'])
            results.append(result)

        return results

    def get_user_total_cost(
        self,
        user_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """计算指定用户在日期范围内的总成本

        Args:
            user_name: 用户名称
            start_date: 开始日期，默认为所有记录的开始
            end_date: 结束日期，默认为所有记录的结束

        Returns:
            包含总成本、总token数等统计信息的字典
        """
        cursor = self.conn.cursor()

        if start_date and end_date:
            cursor.execute("""
                SELECT
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as total_cost,
                    SUM(filter_cost) as filter_cost,
                    SUM(generate_cost) as generate_cost,
                    SUM(papers_fetched) as papers_fetched,
                    SUM(papers_filtered) as papers_filtered,
                    SUM(papers_processed) as papers_processed,
                    COUNT(*) as record_count
                FROM user_token_usage
                WHERE user_name = ? AND date BETWEEN ? AND ?
            """, (user_name, start_date, end_date))
        else:
            cursor.execute("""
                SELECT
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as total_cost,
                    SUM(filter_cost) as filter_cost,
                    SUM(generate_cost) as generate_cost,
                    SUM(papers_fetched) as papers_fetched,
                    SUM(papers_filtered) as papers_filtered,
                    SUM(papers_processed) as papers_processed,
                    COUNT(*) as record_count
                FROM user_token_usage
                WHERE user_name = ?
            """, (user_name,))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            'total_tokens': 0,
            'total_cost': 0.0,
            'filter_cost': 0.0,
            'generate_cost': 0.0,
            'papers_fetched': 0,
            'papers_filtered': 0,
            'papers_processed': 0,
            'record_count': 0
        }

    def get_all_users_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """获取所有用户的汇总统计

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            包含每个用户汇总信息的字典列表
        """
        cursor = self.conn.cursor()

        if start_date and end_date:
            cursor.execute("""
                SELECT
                    user_name,
                    user_email,
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as total_cost,
                    SUM(filter_cost) as filter_cost,
                    SUM(generate_cost) as generate_cost,
                    SUM(papers_fetched) as papers_fetched,
                    SUM(papers_filtered) as papers_filtered,
                    SUM(papers_processed) as papers_processed,
                    COUNT(*) as record_count
                FROM user_token_usage
                WHERE date BETWEEN ? AND ?
                GROUP BY user_name, user_email
                ORDER BY total_cost DESC
            """, (start_date, end_date))
        else:
            cursor.execute("""
                SELECT
                    user_name,
                    user_email,
                    SUM(total_tokens) as total_tokens,
                    SUM(total_cost) as total_cost,
                    SUM(filter_cost) as filter_cost,
                    SUM(generate_cost) as generate_cost,
                    SUM(papers_fetched) as papers_fetched,
                    SUM(papers_filtered) as papers_filtered,
                    SUM(papers_processed) as papers_processed,
                    COUNT(*) as record_count
                FROM user_token_usage
                GROUP BY user_name, user_email
                ORDER BY total_cost DESC
            """)

        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("数据库连接已关闭")

    def __enter__(self):
        """支持上下文管理器"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        self.close()


# 全局数据库实例（线程安全）
_db_instances = {}
_db_lock = threading.Lock()

def get_db() -> TokenUsageDB:
    """获取当前线程的数据库实例（线程安全）

    Returns:
        TokenUsageDB实例
    """
    thread_id = threading.get_ident()

    with _db_lock:
        if thread_id not in _db_instances:
            _db_instances[thread_id] = TokenUsageDB()
        return _db_instances[thread_id]
