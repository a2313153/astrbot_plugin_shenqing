from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import aiohttp  # 仅保留HTTP请求依赖


class ApifoxModel:
    def __init__(self, approve: bool, flag: str, reason: Optional[str] = None) -> None:
        self.approve = approve
        self.flag = flag
        self.reason = reason

@register("astrbot_plugin_appreview", "qiqi", "调用PHP API处理群聊申请的插件", "1.3.0")
class AppReviewPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        # 最小化配置：只保留API地址和延迟时间（其他逻辑全在PHP）
        self.config = {
            "verify_api_url": "https://qun.yz01.baby/verify_key.php",  # PHP API地址
            "delay_seconds": 0  # 延迟处理时间（秒）
        }
        
        if config:
            self._merge_config(config)
        else:
            self.load_config()

    def _merge_config(self, config):
        if not config:
            logger.warning("配置为空，使用默认配置")
            return
        for key, value in config.items():
            if key in self.config:
                self.config[key] = value
        logger.info(f"插件配置加载: {self.config}")

    def load_config(self):
        try:
            if self.context and hasattr(self.context, "get_config"):
                user_config = self.context.get_config()
                if user_config:
                    self._merge_config(user_config)
            else:
                logger.info("使用默认配置")
        except Exception as e:
            logger.error(f"配置加载失败: {e}")

    # 仅保留必要的session_id设置（兼容原有逻辑）
    def set_session_id(self, event):
        if not event or not hasattr(event, "message_obj") or not event.message_obj:
            return
        raw_msg = event.message_obj.raw_message
        if not isinstance(raw_msg, dict):
            return
        if not hasattr(event.message_obj, "session_id") or not event.message_obj.session_id:
            event.message_obj.session_id = str(raw_msg.get("group_id") or raw_msg.get("user_id") or "unknown")

    # 核心：调用PHP API
    async def call_php_api(self, comment, user_id, group_id):
        """仅负责向PHP API发送请求，获取处理结果"""
        try:
            async with aiohttp.ClientSession() as session:
                # 向PHP传递所有必要参数（用户验证信息、用户ID、群ID）
                payload = {
                    "comment": comment,
                    "user_id": user_id,
                    "group_id": group_id
                }
                async with session.post(self.config["verify_api_url"], json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"API请求失败，状态码: {resp.status}")
                        return {"status": "error", "approve": False, "reason": "API请求异常"}
                    return await resp.json()  # 返回PHP处理后的结果
        except Exception as e:
            logger.error(f"API调用异常: {str(e)}")
            return {"status": "error", "approve": False, "reason": "API调用失败"}

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_group_request(self, event: AstrMessageEvent):
        if not event or not hasattr(event, "message_obj") or not event.message_obj:
            return
        raw_msg = event.message_obj.raw_message
        if not isinstance(raw_msg, dict) or raw_msg.get("post_type") != "request":
            return
        # 只处理加群请求
        if raw_msg.get("request_type") == "group" and raw_msg.get("sub_type") == "add":
            await self.process_group_join_request(event, raw_msg)

    async def process_group_join_request(self, event, request_data):
        """最小化处理逻辑：调用API→执行结果"""
        flag = request_data.get("flag")
        user_id = request_data.get("user_id", "")
        comment = request_data.get("comment", "")
        group_id = request_data.get("group_id", "")
        
        if not flag:
            logger.warning("缺少flag参数，无法处理")
            return
        logger.info(f"收到加群请求: 用户{user_id}，群{group_id}，验证信息: {comment}")

        # 延迟处理（保留原有配置）
        if self.config["delay_seconds"] > 0:
            logger.info(f"{self.config['delay_seconds']}秒后处理请求")
            await asyncio.sleep(self.config["delay_seconds"])

        # 核心：调用PHP API获取处理结果
        api_result = await self.call_php_api(comment, user_id, group_id)
        
        # 根据API结果执行同意/拒绝
        approve = api_result.get("approve", False)
        reason = api_result.get("reason", "处理失败")
        await self.approve_request(event, flag, approve, reason)
        logger.info(f"请求处理完成: {'同意' if approve else '拒绝'}，理由: {reason}")

    # 原有同意/拒绝执行逻辑不变（仅做调用）
    async def approve_request(self, event, flag, approve=True, reason=""):
        try:
            if not event or not flag:
                return False
            self.set_session_id(event)
            if not approve and not reason:
                reason = "默认拒绝"
            
            platform = event.get_platform_name() if hasattr(event, "get_platform_name") else None
            if platform == "aiocqhttp":
                from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                if isinstance(event, AiocqhttpMessageEvent) and event.bot and hasattr(event.bot, "call_action"):
                    await event.bot.call_action(
                        'set_group_add_request',
                        flag=flag, sub_type="add", approve=approve, reason=reason
                    )
                    return True
            if event.bot and hasattr(event.bot, "call_action"):
                await event.bot.call_action(
                    "set_group_add_request",
                    flag=flag, sub_type="add", approve=approve, reason=reason
                )
                return True
        except Exception as e:
            logger.error(f"执行失败: {e}")
        return False

    async def terminate(self):
        logger.info("插件已停用")
