from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import mysql.connector  # 替换sqlite3为mysql-connector
from mysql.connector import Error
from datetime import datetime


class ApifoxModel:
    def __init__(self, approve: bool, flag: str, reason: Optional[str] = None) -> None:
        self.approve = approve
        self.flag = flag
        self.reason = reason

@register("astrbot_plugin_appreview", "qiqi", "一个可以通过卡密验证来同意或拒绝进入群聊的插件", "1.4.0")  # 版本号更新
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 默认配置，更新为MySQL连接参数
        self.config = {
            "db_host": "localhost",      # MySQL主机
            "db_port": 3306,             # MySQL端口
            "db_user": "root",           # 数据库用户名
            "db_password": "",           # 数据库密码
            "db_name": "qun_db",         # 数据库名
            "auto_accept": False,        # 是否自动同意所有申请
            "auto_reject": False,        # 是否自动拒绝所有申请
            "reject_reason": "申请被拒绝",  # 拒绝理由
            "delay_seconds": 0           # 延迟处理时间（秒）
        }
        
        # 配置加载与验证
        if config:
            self._merge_config(config)
        else:
            self.load_config()
        
        # 验证拒绝理由配置有效性
        self._validate_reject_reason()
        
        # Monkey patch AstrBotMessage类，确保所有实例都有session_id属性
        from astrbot.core.platform.astrbot_message import AstrBotMessage
        original_init = AstrBotMessage.__init__
        
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if not hasattr(self, "session_id") or not self.session_id:
                self.session_id = "unknown_session"
        
        AstrBotMessage.__init__ = patched_init
        logger.info("已应用AstrBotMessage的monkey patch，确保session_id属性存在")
        
        # 数据库连接初始化
        self.db_conn = None
        self._init_db_connection()
    
    def _init_db_connection(self):
        """初始化MySQL数据库连接"""
        try:
            self.db_conn = mysql.connector.connect(
                host=self.config["db_host"],
                port=self.config["db_port"],
                user=self.config["db_user"],
                password=self.config["db_password"],
                database=self.config["db_name"],
                charset="utf8mb4"  # 支持中文
            )
            if self.db_conn.is_connected():
                logger.info(f"成功连接到MySQL数据库: {self.config['db_name']}")
        except Error as e:
            logger.error(f"MySQL数据库连接失败: {e}")
            self.db_conn = None
    
    def _merge_config(self, config):
        """合并配置并打印日志"""
        if not config:
            logger.warning("传入的配置为null，使用默认配置")
            return
            
        for key, value in config.items():
            if key in self.config:
                self.config[key] = value
        logger.info(f"群聊申请审核插件配置加载成功: {self.config}")
    
    def _validate_reject_reason(self):
        """验证拒绝理由不为空"""
        if not self.config["reject_reason"]:
            self.config["reject_reason"] = "申请被拒绝（默认理由）"
            logger.warning("拒绝理由配置为空，已使用默认值")
        else:
            logger.info(f"当前拒绝理由配置: {self.config['reject_reason']}")
    
    def load_config(self):
        """加载配置"""
        try:
            if not self.context or not hasattr(self.context, "get_config"):
                logger.warning("context对象无效，无法加载配置，使用默认配置")
                return
                
            user_config = self.context.get_config()
            if user_config:
                self._merge_config(user_config)
            else:
                logger.info("使用默认配置")
        except Exception as e:
            logger.error(f"群聊申请审核插件配置加载失败: {e}")
    
    def set_session_id(self, event):
        """设置session_id属性"""
        if not event:
            logger.warning("event为null，无法设置session_id")
            return
            
        if not hasattr(event, "message_obj") or event.message_obj is None:
            logger.warning("event.message_obj为null，无法设置session_id")
            return
            
        raw_message = event.message_obj.raw_message
        if not isinstance(raw_message, dict):
            logger.warning(f"raw_message不是字典类型: {type(raw_message)}，无法设置session_id")
            return
            
        if not hasattr(event.message_obj, "session_id") or not event.message_obj.session_id:
            if "group_id" in raw_message and raw_message["group_id"]:
                event.message_obj.session_id = str(raw_message["group_id"])
            elif "user_id" in raw_message and raw_message["user_id"]:
                event.message_obj.session_id = str(raw_message["user_id"])
            else:
                event.message_obj.session_id = "unknown_session"
                logger.info("无法从raw_message中获取group_id或user_id，使用默认session_id")
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_request(self, event: AstrMessageEvent):
        """处理群聊申请事件"""
        if not event:
            logger.warning("收到空的event对象，跳过处理")
            return
            
        if not hasattr(event, "message_obj") or event.message_obj is None:
            logger.warning("event.message_obj为null，跳过处理")
            return
            
        raw_message = event.message_obj.raw_message
        if not raw_message or not isinstance(raw_message, dict):
            logger.warning(f"raw_message格式异常: {raw_message}，类型: {type(raw_message)}，跳过处理")
            return
        
        if raw_message.get("post_type") != "request":
            return
        
        self.set_session_id(event)
        
        if raw_message.get("request_type") == "group" and raw_message.get("sub_type") == "add":
            await self.process_group_join_request(event, raw_message)
    
    async def process_group_join_request(self, event: AstrMessageEvent, request_data):
        """处理加群请求，使用MySQL数据库卡密验证"""
        if not request_data or not isinstance(request_data, dict):
            logger.warning("无效的request_data，跳过处理")
            return
            
        # 检查数据库连接
        if not self.db_conn or not self.db_conn.is_connected():
            logger.error("MySQL数据库连接未初始化或已断开，尝试重新连接...")
            self._init_db_connection()  # 尝试重新连接
            if not self.db_conn or not self.db_conn.is_connected():
                logger.error("重新连接失败，无法处理申请")
                return
            
        flag = request_data.get("flag", "")
        user_id = request_data.get("user_id", "")
        comment = request_data.get("comment", "")  # 入群申请消息，包含卡密
        group_id = request_data.get("group_id", "")
        
        if not flag:
            logger.warning("加群请求缺少flag参数，无法处理")
            return
            
        logger.info(f"收到加群请求: 用户ID={user_id}, 群ID={group_id}, 验证信息={comment}")
        
        delay_seconds = self.config.get("delay_seconds", 0)
        
        # 自动同意逻辑（优先级最高）
        if self.config["auto_accept"]:
            if delay_seconds > 0:
                logger.info(f"将在 {delay_seconds} 秒后自动同意用户 {user_id} 加入群 {group_id} 的请求")
                await asyncio.sleep(delay_seconds)
            await self.approve_request(event, flag, True)
            logger.info(f"自动同意用户 {user_id} 加入群 {group_id} 的请求")
            return
        
        # 自动拒绝逻辑
        if self.config["auto_reject"]:
            if delay_seconds > 0:
                logger.info(f"将在 {delay_seconds} 秒后自动拒绝用户 {user_id} 加入群 {group_id} 的请求")
                await asyncio.sleep(delay_seconds)
            logger.info(f"执行自动拒绝，使用理由: {self.config['reject_reason']}")
            await self.approve_request(event, flag, False, self.config["reject_reason"])
            logger.info(f"自动拒绝用户 {user_id} 加入群 {group_id} 的请求")
            return
        
        # 卡密验证逻辑
        try:
            # 延迟处理
            if delay_seconds > 0:
                logger.info(f"将在 {delay_seconds} 秒后验证用户 {user_id} 的卡密")
                await asyncio.sleep(delay_seconds)
            
            # 查询数据库验证卡密
            cursor = self.db_conn.cursor()
            
            # 检查群是否存在并验证卡密（MySQL使用%s作为占位符）
            cursor.execute(
                "SELECT id, usable FROM qun_keys WHERE group_id = %s AND key_code = %s",
                (group_id, comment)
            )
            result = cursor.fetchone()
            
            if result:
                record_id, usable = result
                # 检查卡密是否可用（usable=0）
                if usable == 0:
                    # 更新卡密使用信息
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute(
                        "UPDATE qun_keys SET usable = 1, use_time = %s, used_by = %s WHERE id = %s",
                        (current_time, user_id, record_id)
                    )
                    self.db_conn.commit()  # MySQL需要显式提交事务
                    
                    # 同意入群
                    await self.approve_request(event, flag, True)
                    logger.info(f"卡密验证通过，同意用户 {user_id} 加入群 {group_id} 的请求")
                    return
                else:
                    logger.info(f"卡密已被使用，拒绝用户 {user_id} 加入群 {group_id} 的请求")
            else:
                logger.info(f"卡密不存在或群不匹配，拒绝用户 {user_id} 加入群 {group_id} 的请求")
            
            # 卡密验证失败，拒绝入群
            await self.approve_request(event, flag, False, "卡密验证失败，无法入群")
            
        except Error as e:
            logger.error(f"MySQL操作出错: {e}")
            self.db_conn.rollback()  # 出错时回滚事务
            await self.approve_request(event, flag, False, "验证过程出错，请联系管理员")
        finally:
            if 'cursor' in locals() and cursor:
                cursor.close()
    
    async def approve_request(self, event: AstrMessageEvent, flag, approve=True, reason=""):
        """同意或拒绝请求"""
        try:
            if not event:
                logger.error("event为null，无法处理请求")
                return False
                
            if not flag:
                logger.error("flag参数为空，无法处理请求")
                return False
            
            self.set_session_id(event)
            
            if not approve and not reason:
                reason = "申请被拒绝（默认理由）"
            
            # 调用AstrBot的API处理入群申请
            await event.message_obj.approve_group_request(flag, approve, reason)
            return True
            
        except Exception as e:
            logger.error(f"处理请求时出错: {e}")
            return False
    
    def __del__(self):
        """销毁对象时关闭数据库连接"""
        if self.db_conn and self.db_conn.is_connected():
            self.db_conn.close()
            logger.info("MySQL数据库连接已关闭")
