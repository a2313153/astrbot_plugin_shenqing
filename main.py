from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import requests
import re
import logging
from typing import Tuple, Optional

# 配置日志（写入文件并输出到控制台）
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - [入群验证插件] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("join_verify.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# API地址 - 请替换为你的PHP接口实际地址
API_URL = "https://qun.yz01.baby/check_key.php"

def extract_key_code(message: str) -> Optional[str]:
    """
    从入群申请消息中提取卡密
    卡密格式：假设为8-20位字母+数字组合（可根据实际调整正则）
    """
    try:
        # 正则匹配卡密（可根据实际卡密规则修改）
        pattern = r'[A-Za-z0-9]{8,20}'
        match_result = re.search(pattern, message)
        if match_result:
            key_code = match_result.group().strip()
            logger.debug(f"从消息中提取到卡密：{key_code}")
            return key_code
        else:
            logger.debug(f"未从消息「{message}」中提取到符合格式的卡密")
            return None
    except Exception as e:
        logger.error(f"提取卡密时发生错误：{str(e)}", exc_info=True)
        return None

def verify_key(group_id: str, applicant_qq: str, key_code: str) -> dict:
    """调用API验证卡密有效性"""
    try:
        # 检查参数合法性
        if not all([group_id, applicant_qq, key_code]):
            return {"success": False, "message": "验证参数不完整"}
        
        # 发送POST请求到API
        data = {
            "group_id": group_id,
            "applicant_qq": applicant_qq,
            "key_code": key_code
        }
        logger.debug(f"向API发送验证请求：{data}")
        
        response = requests.post(
            API_URL,
            data=data,
            timeout=10,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        # 解析JSON响应
        if response.status_code != 200:
            return {"success": False, "message": f"API请求失败，状态码：{response.status_code}"}
        
        result = response.json()
        logger.debug(f"API返回验证结果：{result}")
        return result
    
    except requests.exceptions.Timeout:
        return {"success": False, "message": "API请求超时"}
    except requests.exceptions.RequestException as e:
        logger.error(f"API请求发生网络错误：{str(e)}", exc_info=True)
        return {"success": False, "message": "网络请求异常"}
    except ValueError:
        logger.error(f"API返回非JSON格式数据：{response.text}", exc_info=True)
        return {"success": False, "message": "API返回数据格式错误"}
    except Exception as e:
        logger.error(f"卡密验证过程发生未知错误：{str(e)}", exc_info=True)
        return {"success": False, "message": "验证过程出错"}

def handle_join_request(event) -> Tuple[bool, str]:
    """
    处理入群申请事件
    :param event: AstrBot的入群申请事件对象
    :return: (是否允许入群, 处理消息)
    """
    try:
        # 验证事件参数完整性（避免索引越界核心处理）
        if not hasattr(event, 'args'):
            return False, "事件参数异常：无args属性"
        
        args = event.args
        if len(args) < 3:
            logger.error(f"事件参数不足，需要3个参数，实际收到：{len(args)}个，参数列表：{args}")
            return False, "事件参数不完整"
        
        # 提取关键参数（严格校验索引有效性）
        group_id = str(args[0]).strip() if len(args) > 0 else ""
        applicant_qq = str(args[1]).strip() if len(args) > 1 else ""
        request_message = str(args[2]).strip() if len(args) > 2 else ""
        
        # 基础参数校验
        if not group_id:
            return False, "群ID为空，无法验证"
        if not applicant_qq:
            return False, "申请人QQ为空，无法验证"
        if not request_message:
            return False, "入群申请消息为空"
        
        logger.info(f"收到入群申请 - 群ID：{group_id}，申请人：{applicant_qq}，消息：{request_message}")
        
        # 提取卡密
        key_code = extract_key_code(request_message)
        if not key_code:
            return False, "未检测到有效的卡密，请检查输入格式"
        
        # 验证卡密
        verify_result = verify_key(group_id, applicant_qq, key_code)
        if verify_result.get("success", False):
            return True, "卡密验证通过，已同意入群"
        else:
            return False, verify_result.get("message", "卡密验证失败")
    
    except IndexError as e:
        logger.error(f"处理入群申请时发生索引越界错误：{str(e)}", exc_info=True)
        return False, "处理申请时发生参数错误"
    except Exception as e:
        logger.error(f"处理入群申请时发生未知错误：{str(e)}", exc_info=True)
        return False, "处理申请时发生系统错误"

# AstrBot插件入口（根据AstrBot的插件规范实现）
def on_event(event, bot):
    """AstrBot事件处理入口"""
    try:
        # 判断是否为入群申请事件（根据AstrBot的事件类型定义调整）
        if event.type == "join_request":  # 此处事件类型需与AstrBot实际定义一致
            allow_join, message = handle_join_request(event)
            logger.info(f"入群申请处理结果 - 允许：{allow_join}，消息：{message}")
            
            # 执行同意/拒绝操作（根据AstrBot的API调整）
            if allow_join:
                bot同意入群的方法(event, message)  # 替换为实际同意方法
            else:
                bot拒绝入群的方法(event, message)  # 替换为实际拒绝方法
    except Exception as e:
        logger.error(f"插件入口事件处理错误：{str(e)}", exc_info=True)

# 插件元信息（AstrBot插件规范要求）
plugin_info = {
    "name": "入群卡密验证插件",
    "version": "1.0.0",
    "description": "通过卡密验证自动处理入群申请",
    "author": "你的名字"
}
