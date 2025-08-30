from nonebot import on_request, logger
from nonebot.adapters.onebot.v11 import Bot, GroupRequestEvent, ActionFailed
from nonebot.permission import SUPERUSER
import asyncio
from pydantic import BaseModel
from typing import List, Optional

# 配置模型
class Config(BaseModel):
    # 允许入群的关键词列表
    allow_keywords: List[str] = []
    # 拒绝入群的关键词列表
    reject_keywords: List[str] = []
    # 拒绝理由
    reject_reason: str = "您的申请包含不适当内容，已拒绝入群"
    # 无关键词时的默认回复
    default_allow: bool = False
    # 默认允许/拒绝时的回复
    default_allow_reason: str = "欢迎加入本群！"
    default_reject_reason: str = "未包含必要关键词，已拒绝入群"
    # 最大重试次数
    max_retries: int = 2

# 全局配置实例
config = Config()

# 注册群请求处理
group_join_request = on_request(priority=10, permission=SUPERUSER)

@group_join_request.handle()
async def process_group_join_request(bot: Bot, event: GroupRequestEvent):
    """处理群加入请求"""
    if event.request_type != "add":
        return  # 只处理入群请求
    
    user_id = event.user_id
    group_id = event.group_id
    comment = event.comment.strip() if event.comment else ""
    flag = event.flag
    
    logger.info(f"收到入群请求 - 用户: {user_id}, 群聊: {group_id}, 验证信息: {comment}")
    
    # 检查是否包含拒绝关键词
    reject = await check_reject_keywords(comment)
    if reject:
        logger.info(f"用户 {user_id} 的入群请求包含拒绝关键词，准备拒绝")
        success = await approve_request(
            bot, event, flag, approve=False, 
            reason=config.reject_reason
        )
        if success:
            logger.info(f"已成功拒绝用户 {user_id} 入群")
        else:
            logger.error(f"拒绝用户 {user_id} 入群失败")
        return
    
    # 检查是否包含允许关键词
    allow = await check_allow_keywords(comment) if config.allow_keywords else False
    
    # 根据默认设置处理
    if allow or (not config.allow_keywords and config.default_allow):
        # 允许入群
        reason = config.default_allow_reason
        success = await approve_request(bot, event, flag, approve=True, reason=reason)
        logger.info(f"允许用户 {user_id} 入群: {reason}")
    else:
        # 拒绝入群（未包含必要关键词）
        reason = config.default_reject_reason
        success = await approve_request(bot, event, flag, approve=False, reason=reason)
        logger.info(f"拒绝用户 {user_id} 入群（未含必要关键词）: {reason}")

async def check_reject_keywords(comment: str) -> bool:
    """检查是否包含拒绝关键词"""
    clean_comment = comment.lower()
    for keyword in config.reject_keywords:
        clean_keyword = keyword.strip().lower()
        if clean_keyword and clean_keyword in clean_comment:
            logger.info(f"匹配到拒绝关键词: {keyword}")
            return True
    return False

async def check_allow_keywords(comment: str) -> bool:
    """检查是否包含允许关键词"""
    clean_comment = comment.lower()
    for keyword in config.allow_keywords:
        clean_keyword = keyword.strip().lower()
        if clean_keyword and clean_keyword in clean_comment:
            logger.info(f"匹配到允许关键词: {keyword}")
            return True
    return False

async def approve_request(
    bot: Bot, 
    event: GroupRequestEvent, 
    flag: str, 
    approve: bool = True, 
    reason: str = ""
) -> bool:
    """处理入群请求（包含重试机制）"""
    retries = 0
    while retries <= config.max_retries:
        try:
            logger.debug(
                f"处理入群请求 - 操作: {'允许' if approve else '拒绝'}, "
                f"用户: {event.user_id}, 群聊: {event.group_id}, "
                f"理由: {reason}, 重试次数: {retries}"
            )
            
            # 调用平台接口处理请求
            await bot.set_group_add_request(
                flag=flag,
                sub_type="add",
                approve=approve,
                reason=reason[:20]  # 限制理由长度，避免接口报错
            )
            return True
            
        except ActionFailed as e:
            retries += 1
            logger.error(
                f"处理入群请求失败（第{retries}次重试）- "
                f"错误码: {e.retcode}, 错误信息: {e.info}"
            )
            if retries > config.max_retries:
                return False
            await asyncio.sleep(1)  # 等待1秒后重试
        except Exception as e:
            logger.error(f"处理入群请求时发生未知错误: {str(e)}")
            return False

# 配置加载函数（根据实际框架调整）
def load_config(new_config: dict):
    """加载配置"""
    global config
    config = Config(**new_config)
    logger.info("入群请求处理器配置已更新")
    logger.debug(f"当前配置: {config.dict()}")
