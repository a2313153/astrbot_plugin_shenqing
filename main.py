from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import aiohttp
import time
import json  # 新增json导入


class ApifoxModel:
    def __init__(self, approve: bool, flag: str, reason: Optional[str] = None) -> None:
        self.approve = approve
        self.flag = flag
        self.reason = reason

@register("astrbot_plugin_shenhe", "qiqi", "一个可以通过卡密验证来同意或拒绝进入群聊的插件", "1.4.0")
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 默认配置
        self.config = {
            "api_url": "https://qun.yz01.baby/api/check_key.php",  # 卡密验证API地址
            "auto_accept": False,
            "auto_reject": False,
            "reject_reason": "申请被拒绝",
            "delay_seconds": 0
        }
        
        if config:
            for key, value in config.items():
                if key in self.config:
                    self.config[key] = value
            logger.info(f"群聊申请审核插件配置加载成功: {self.config}")
        else:
            self.load_config()
        
        # 简化session_id处理，避免复杂的monkey patch
        self.session_ids = {}
    
    def load_config(self):
        try:
            user_config = self.context.get_config()
            if user_config:
                for key, value in user_config.items():
                    if key in self.config:
                        self.config[key] = value
            logger.info(f"群聊申请审核插件配置加载成功: {self.config}")
        except Exception as e:
            logger.error(f"群聊申请审核插件配置加载失败: {e}")
    
    def get_session_id(self, raw_message):
        """获取会话ID，不依赖message_obj"""
        if "group_id" in raw_message and raw_message["group_id"]:
            return str(raw_message["group_id"])
        elif "user_id" in raw_message and raw_message["user_id"]:
            return str(raw_message["user_id"])
        return "unknown_session"
    
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_request(self, event: AstrMessageEvent):
        """处理群聊申请事件（通用版）"""
        try:
            # 直接从event获取原始消息，不依赖特定平台的message_obj结构
            raw_message = event.raw_message if hasattr(event, 'raw_message') else None
            
            if not raw_message or not isinstance(raw_message, dict):
                return
            
            # 检查是否为群组请求事件
            if raw_message.get("post_type") != "request":
                return
            
            # 处理加群请求
            if raw_message.get("request_type") == "group" and raw_message.get("sub_type") == "add":
                await self.process_group_join_request(event, raw_message)
        except Exception as e:
            logger.error(f"处理请求事件时出错: {str(e)}")
    
    async def verify_key(self, group_id, key_code, user_id):
        """调用API验证卡密（增强错误处理）"""
        api_url = self.config.get("api_url")
        if not api_url:
            logger.error("未配置API地址，请在插件设置中配置api_url")
            return {"status": "error", "message": "系统配置错误，无法验证卡密"}
        
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "group_id": group_id,
                    "key_code": key_code,
                    "user_id": user_id,
                    "use_time": int(time.time())
                }
                
                async with session.post(api_url, data=params) as response:
                    status_code = response.status
                    response_text = await response.text()
                    logger.debug(f"API响应: 状态码={status_code}, 内容={response_text}")
                    
                    if status_code != 200:
                        return {"status": "error", "message": f"API请求失败，状态码: {status_code}"}
                    
                    try:
                        return json.loads(response_text)
                    except json.JSONDecodeError:
                        return {"status": "error", "message": f"API返回无效JSON: {response_text[:50]}..."}
        except Exception as e:
            logger.error(f"卡密验证API调用失败: {e}")
            return {"status": "error", "message": f"验证卡密时发生错误: {str(e)}"}
    
    async def process_group_join_request(self, event: AstrMessageEvent, request_data):
        """处理加群请求"""
        flag = request_data.get("flag", "")
        user_id = request_data.get("user_id", "")
        comment = request_data.get("comment", "").strip()
        group_id = request_data.get("group_id", "")
        
        logger.info(f"收到加群请求: 用户ID={user_id}, 群ID={group_id}, 卡密={comment}")
        
        # 延迟处理
        delay_seconds = self.config.get("delay_seconds", 0)
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        
        # 自动处理
        if self.config["auto_accept"]:
            await self.approve_request(event, flag, True)
            return
        
        if self.config["auto_reject"]:
            await self.approve_request(event, flag, False, self.config["reject_reason"])
            return
        
        # 卡密为空
        if not comment:
            await self.approve_request(event, flag, False, "请提供有效的卡密")
            return
        
        # 验证卡密
        verify_result = await self.verify_key(group_id, comment, user_id)
        
        # 处理验证结果
        if verify_result["status"] == "success":
            if verify_result.get("usable", 1) == 0:
                await self.approve_request(event, flag, True)
                logger.info(f"卡密验证通过，同意用户 {user_id} 加入群 {group_id}")
            else:
                await self.approve_request(event, flag, False, "该卡密已使用")
                logger.info(f"卡密已使用，拒绝用户 {user_id}")
        else:
            reason = verify_result.get("message", "卡密错误")
            await self.approve_request(event, flag, False, reason)
            logger.info(f"卡密验证失败，拒绝用户 {user_id}: {reason}")
    
    async def approve_request(self, event: AstrMessageEvent, flag, approve=True, reason=""):
        """通用版同意/拒绝请求，不依赖特定平台模块"""
        try:
            # 直接使用基础的bot调用方法，兼容更多平台
            if hasattr(event.bot, "call_action"):
                # 构造通用参数
                params = {
                    "flag": flag,
                    "sub_type": "add",
                    "approve": approve,
                    "reason": reason or ""
                }
                
                # 调用通用接口
                result = await event.bot.call_action("set_group_add_request", **params)
                logger.debug(f"处理请求结果: {result}")
                return True
            else:
                logger.error("Bot实例不支持call_action方法，无法处理请求")
                return False
        except Exception as e:
            logger.error(f"处理群聊申请失败: {str(e)}")
            return False
    
    async def terminate(self):
        logger.info("群聊申请审核插件已停用")
