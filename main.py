from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import aiohttp  # 新增：用于发送HTTP请求


class ApifoxModel:
    def __init__(self, approve: bool, flag: str, reason: Optional[str] = None) -> None:
        self.approve = approve
        self.flag = flag
        self.reason = reason

@register("astrbot_plugin_appreview", "qiqi", "一个可以通过关键词或卡密来同意或拒绝进入群聊的插件", "1.3.0")
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 默认配置，新增卡密验证相关配置
        self.config = {
            "accept_keywords": ["给了", "一键三连了", "三连了"],
            "reject_keywords": ["拒绝", "不同意", "reject", "deny"],
            "auto_accept": False,  # 是否自动同意所有申请
            "auto_reject": False,  # 是否自动拒绝所有申请
            "reject_reason": "申请被拒绝",  # 拒绝理由
            "delay_seconds": 0,  # 延迟处理时间（秒）
            # 新增：卡密验证相关配置
            "use_verify_code": True,  # 是否启用卡密验证
            "verify_api_url": "https://qun.yz01.baby/verify_key.php",  # 卡密验证API地址
            "verify_code_prefix": "",  # 卡密前缀（可选，如"CODE:"）
            "priority_verify_code": True  # 卡密验证是否优先于关键词验证
        }
        
        # 配置加载与验证
        if config:
            self._merge_config(config)
        else:
            self.load_config()
        
        # 验证拒绝理由配置有效性
        self._validate_reject_reason()
        
        # 新增：验证卡密API配置
        self._validate_verify_api_config()
        
        # Monkey patch AstrBotMessage类，确保所有实例都有session_id属性
        from astrbot.core.platform.astrbot_message import AstrBotMessage
        original_init = AstrBotMessage.__init__
        
        def patched_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if not hasattr(self, "session_id") or not self.session_id:
                self.session_id = "unknown_session"
        
        AstrBotMessage.__init__ = patched_init
        logger.info("已应用AstrBotMessage的monkey patch，确保session_id属性存在")
    
    def _merge_config(self, config):
        """合并配置并打印日志"""
        if not config:  # 检查配置是否为null
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
    
    # 新增：验证卡密API配置
    def _validate_verify_api_config(self):
        """验证卡密API配置有效性"""
        if self.config["use_verify_code"]:
            if not self.config["verify_api_url"]:
                logger.warning("卡密验证已启用，但未配置API地址，将禁用卡密验证")
                self.config["use_verify_code"] = False
            else:
                logger.info(f"卡密验证已启用，API地址: {self.config['verify_api_url']}")
        else:
            logger.info("卡密验证已禁用")
    
    def load_config(self):
        """加载配置"""
        try:
            # 检查context是否有效
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
        """设置session_id属性，增加全面的空值检查"""
        # 检查event是否有效
        if not event:
            logger.warning("event为null，无法设置session_id")
            return
            
        # 检查message_obj是否存在且有效
        if not hasattr(event, "message_obj") or event.message_obj is None:
            logger.warning("event.message_obj为null，无法设置session_id")
            return
            
        raw_message = event.message_obj.raw_message
        # 检查raw_message是否有效
        if not isinstance(raw_message, dict):
            logger.warning(f"raw_message不是字典类型: {type(raw_message)}，无法设置session_id")
            return
            
        # 设置session_id
        if not hasattr(event.message_obj, "session_id") or not event.message_obj.session_id:
            if "group_id" in raw_message and raw_message["group_id"]:
                event.message_obj.session_id = str(raw_message["group_id"])
            elif "user_id" in raw_message and raw_message["user_id"]:
                event.message_obj.session_id = str(raw_message["user_id"])
            else:
                event.message_obj.session_id = "unknown_session"
                logger.info("无法从raw_message中获取group_id或user_id，使用默认session_id")
    
    # 新增：卡密验证API调用函数
    async def verify_card_code(self, card_code):
        """调用卡密验证API验证卡密有效性"""
        if not card_code:
            logger.warning("卡密为空，验证失败")
            return False, "卡密不能为空"
            
        # 如果配置了前缀，移除前缀再验证
        if self.config["verify_code_prefix"] and card_code.startswith(self.config["verify_code_prefix"]):
            card_code = card_code[len(self.config["verify_code_prefix"]):]
            logger.info(f"移除卡密前缀后的值: {card_code}")
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"card_code": card_code}
                async with session.post(self.config["verify_api_url"], json=payload) as response:
                    if response.status != 200:
                        error_msg = f"API请求失败，状态码: {response.status}"
                        logger.error(error_msg)
                        return False, error_msg
                        
                    response_data = await response.json()
                    
                    if response_data.get("status") == "success":
                        logger.info(f"卡密验证成功: {card_code}")
                        return True, response_data.get("msg", "卡密有效")
                    else:
                        error_msg = response_data.get("msg", "卡密无效")
                        logger.warning(f"卡密验证失败: {card_code}, 原因: {error_msg}")
                        return False, error_msg
                        
        except Exception as e:
            error_msg = f"卡密验证API调用异常: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_request(self, event: AstrMessageEvent):
        """处理群聊申请事件，增加全面的空值检查"""
        # 基础空值检查
        if not event:
            logger.warning("收到空的event对象，跳过处理")
            return
            
        # 检查message_obj是否存在
        if not hasattr(event, "message_obj") or event.message_obj is None:
            logger.warning("event.message_obj为null，跳过处理")
            return
            
        # 获取并检查raw_message
        raw_message = event.message_obj.raw_message
        if not raw_message or not isinstance(raw_message, dict):
            logger.warning(f"raw_message格式异常: {raw_message}，类型: {type(raw_message)}，跳过处理")
            return
        
        # 检查事件类型
        if raw_message.get("post_type") != "request":
            return
        
        # 设置session_id
        self.set_session_id(event)
        
        # 处理加群请求
        if raw_message.get("request_type") == "group" and raw_message.get("sub_type") == "add":
            await self.process_group_join_request(event, raw_message)
    
    async def process_group_join_request(self, event: AstrMessageEvent, request_data):
        """处理加群请求，增加卡密验证逻辑"""
        # 检查request_data有效性
        if not request_data or not isinstance(request_data, dict):
            logger.warning("无效的request_data，跳过处理")
            return
            
        flag = request_data.get("flag", "")
        user_id = request_data.get("user_id", "")
        comment = request_data.get("comment", "")
        group_id = request_data.get("group_id", "")
        
        # 基础参数检查
        if not flag:
            logger.warning("加群请求缺少flag参数，无法处理")
            return
            
        logger.info(f"收到加群请求: 用户ID={user_id}, 群ID={group_id}, 验证信息={comment}")
        
        delay_seconds = self.config.get("delay_seconds", 0)
        
        # 自动同意逻辑
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
        
        # 新增：卡密验证逻辑
        if self.config["use_verify_code"]:
            # 尝试从验证信息中提取卡密并验证
            verify_success, verify_msg = await self.verify_card_code(comment)
            
            if verify_success:
                # 卡密验证成功，同意入群
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后因卡密验证成功同意用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                await self.approve_request(event, flag, True)
                logger.info(f"卡密验证成功，同意用户 {user_id} 加入群 {group_id} 的请求: {verify_msg}")
                return
                
            if self.config["priority_verify_code"]:
                # 卡密验证优先模式下，验证失败直接拒绝
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后因卡密验证失败拒绝用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                await self.approve_request(event, flag, False, verify_msg or self.config["reject_reason"])
                logger.info(f"卡密验证失败，拒绝用户 {user_id} 加入群 {group_id} 的请求: {verify_msg}")
                return
        
        # 关键词拒绝逻辑
        for keyword in self.config["reject_keywords"]:
            if keyword.lower() in comment.lower():
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后根据关键词 '{keyword}' 拒绝用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                logger.info(f"关键词拒绝，使用理由: {self.config['reject_reason']}")
                await self.approve_request(event, flag, False, self.config["reject_reason"])
                logger.info(f"根据关键词 '{keyword}' 拒绝用户 {user_id} 加入群 {group_id} 的请求")
                return
        
        # 关键词同意逻辑
        for keyword in self.config["accept_keywords"]:
            if keyword.lower() in comment.lower():
                if delay_seconds > 0:
                    logger.info(f"将在 {delay_seconds} 秒后根据关键词 '{keyword}' 同意用户 {user_id} 加入群 {group_id} 的请求")
                    await asyncio.sleep(delay_seconds)
                await self.approve_request(event, flag, True)
                logger.info(f"根据关键词 '{keyword}' 同意用户 {user_id} 加入群 {group_id} 的请求")
                return
        
        # 如果启用了卡密验证但未验证通过，且不是优先模式，则拒绝
        if self.config["use_verify_code"]:
            logger.info(f"用户 {user_id} 加入群 {group_id} 的请求未提供有效卡密，拒绝入群")
            await self.approve_request(event, flag, False, "未提供有效卡密，拒绝入群")
            return
        
        logger.info(f"用户 {user_id} 加入群 {group_id} 的请求未匹配到关键词，等待手动审核")
        return
    
    async def approve_request(self, event: AstrMessageEvent, flag, approve=True, reason=""):
        """同意或拒绝请求，增加全面的空值检查"""
        try:
            # 基础参数检查
            if not event:
                logger.error("event为null，无法处理请求")
                return False
                
            if not flag:
                logger.error("flag参数为空，无法处理请求")
                return False
            
            # 设置session_id
            self.set_session_id(event)
            
            # 验证理由参数
            if not approve and not reason:
                reason = "申请被拒绝（默认理由）"
                logger.warning("拒绝操作未指定理由，使用默认值")
            
            logger.info(f"执行{'同意' if approve else '拒绝'}操作，理由：{reason}")
            
            # 检查平台名称获取方法
            if not hasattr(event, "get_platform_name"):
                logger.warning("event对象没有get_platform_name方法，使用通用处理方式")
                platform_name = None
            else:
                platform_name = event.get_platform_name()
            
            # 处理aiocqhttp平台
            if platform_name == "aiocqhttp":
                try:
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    # 检查事件类型和bot对象
                    if not isinstance(event, AiocqhttpMessageEvent):
                        logger.error("事件不是AiocqhttpMessageEvent类型")
                        return False
                        
                    if not event.bot:
                        logger.error("event.bot为null，无法执行操作")
                        return False
                        
                    client = event.bot
                    
                    # 检查client是否有call_action方法
                    if not hasattr(client, "call_action"):
                        logger.error("client对象没有call_action方法")
                        return False
                    
                    api_model = ApifoxModel(
                        approve=approve,
                        flag=flag,
                        reason=reason
                    )
                    
                    payloads = {
                        "flag": api_model.flag,
                        "sub_type": "add",
                        "approve": api_model.approve,
                        "reason": api_model.reason
                    }
                    
                    await client.call_action('set_group_add_request', **payloads)
                    return True
                except ImportError:
                    logger.error("导入AiocqhttpMessageEvent失败，可能平台支持不完整")
                    return False
                except Exception as e:
                    logger.error(f"aiocqhttp平台处理失败: {str(e)}")
                    return False
            
            # 处理其他平台
            if not hasattr(event, "bot") or event.bot is None:
                logger.error("event.bot为null，无法执行操作")
                return False
                
            if not hasattr(event.bot, "call_action"):
                logger.error("bot对象没有call_action方法")
                return False
                
            await event.bot.call_action(
                "set_group_add_request",
                flag=flag,
                sub_type="add",
                approve=approve,
                reason=reason
            )
            return True
            
        except Exception as e:
            logger.error(f"处理群聊申请失败: {str(e)}")
            return False
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("群聊申请审核插件已停用")
