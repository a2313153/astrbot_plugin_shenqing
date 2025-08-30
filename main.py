import requests
import re
import logging
import os
from typing import Tuple, Optional, Dict, Any

# 插件加载时立即初始化日志（确保在任何可能出错的操作前）
def init_logger():
    """初始化日志系统，确保插件加载阶段即可记录日志"""
    logger = logging.getLogger("astrbot_plugin_shenqing")
    logger.setLevel(logging.DEBUG)
    
    # 避免重复添加处理器
    if not logger.handlers:
        # 文件处理器
        log_file = os.path.join(os.path.dirname(__file__), "join_verify.log") if __file__ else "join_verify.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        # 控制台处理器
        console_handler = logging.StreamHandler()
        
        # 格式化器
        formatter = logging.Formatter('%(asctime)s - [入群验证插件] - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
    
    return logger

# 初始化日志（插件加载时立即执行）
logger = init_logger()
logger.debug("开始加载入群申请验证插件...")

# 安全读取配置文件（避免配置读取时的索引错误）
def load_config() -> Dict[str, Any]:
    """安全加载配置文件，提供默认值防止索引错误"""
    default_config = {
        "api_url": "https://qun.yz01.baby/check_key.php",
        "key_pattern": r'[A-Za-z0-9]{8,20}',
        "timeout": 10
    }
    
    try:
        # 尝试从文件加载配置
        if __file__:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    import json
                    user_config = json.load(f)
                    # 合并配置，确保不会因缺少键导致错误
                    return {**default_config,** user_config}
            else:
                logger.warning(f"配置文件不存在：{config_path}，使用默认配置")
        else:
            logger.warning("无法确定配置文件路径，使用默认配置")
    except Exception as e:
        logger.error(f"加载配置文件出错：{str(e)}，使用默认配置", exc_info=True)
    
    return default_config

# 加载配置（插件初始化阶段执行，带错误处理）
try:
    config = load_config()
    API_URL = config["api_url"]
    KEY_PATTERN = config["key_pattern"]
    TIMEOUT = config["timeout"]
    logger.debug(f"配置加载完成：API地址={API_URL}，卡密模式={KEY_PATTERN}")
except Exception as e:
    logger.error(f"配置初始化失败：{str(e)}", exc_info=True)
    # 提供最后的安全保障，避免插件完全无法加载
    API_URL = "http://你的域名/check_key.php"
    KEY_PATTERN = r'[A-Za-z0-9]{8,20}'
    TIMEOUT = 10

def extract_key_code(message: str) -> Optional[str]:
    """从入群申请消息中提取卡密，带完整错误处理"""
    try:
        if not message:
            logger.debug("入群消息为空，无法提取卡密")
            return None
            
        # 安全使用正则表达式
        pattern = re.compile(KEY_PATTERN)
        match_result = pattern.search(message)
        
        if match_result:
            key_code = match_result.group().strip()
            logger.debug(f"提取到卡密：{key_code}")
            return key_code
        else:
            logger.debug(f"未从消息「{message[:50]}...」中提取到符合格式的卡密")
            return None
    except re.error as e:
        logger.error(f"正则表达式错误：{str(e)}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"提取卡密时发生错误：{str(e)}", exc_info=True)
        return None

def verify_key(group_id: str, applicant_qq: str, key_code: str) -> dict:
    """调用API验证卡密有效性，带参数校验"""
    try:
        # 严格验证输入参数
        if not isinstance(group_id, str) or not group_id.strip():
            return {"success": False, "message": "群ID无效"}
        if not isinstance(applicant_qq, str) or not applicant_qq.strip():
            return {"success": False, "message": "申请人QQ无效"}
        if not isinstance(key_code, str) or not key_code.strip():
            return {"success": False, "message": "卡密无效"}
        
        group_id = group_id.strip()
        applicant_qq = applicant_qq.strip()
        key_code = key_code.strip()
        
        # 准备请求数据
        data = {
            "group_id": group_id,
            "applicant_qq": applicant_qq,
            "key_code": key_code
        }
        
        logger.debug(f"发送验证请求：{data}")
        
        # 发送请求
        response = requests.post(
            API_URL,
            data=data,
            timeout=TIMEOUT,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        # 处理响应
        if response.status_code != 200:
            return {"success": False, "message": f"API请求失败，状态码：{response.status_code}"}
        
        try:
            result = response.json()
            return result if isinstance(result, dict) else {"success": False, "message": "API返回格式错误"}
        except ValueError:
            logger.error(f"API返回非JSON数据：{response.text[:100]}...")
            return {"success": False, "message": "API返回数据格式错误"}
            
    except requests.exceptions.Timeout:
        return {"success": False, "message": "API请求超时"}
    except Exception as e:
        logger.error(f"卡密验证出错：{str(e)}", exc_info=True)
        return {"success": False, "message": "验证过程发生错误"}

def handle_join_request(event) -> Tuple[bool, str]:
    """处理入群申请，带严格的参数校验"""
    try:
        # 验证事件对象是否有效
        if not event:
            return False, "事件对象为空"
        
        # 安全处理事件参数，防止索引错误
        args = []
        if hasattr(event, 'args'):
            # 确保args是列表类型
            if isinstance(event.args, (list, tuple)):
                args = list(event.args)
            else:
                logger.warning(f"事件参数不是列表/元组类型，而是：{type(event.args)}")
                args = [str(event.args)]
        
        # 确保有足够的参数，不足则用空字符串填充
        while len(args) < 3:
            args.append("")
        
        # 提取参数（现在args至少有3个元素，不会索引越界）
        group_id = str(args[0]).strip()
        applicant_qq = str(args[1]).strip()
        request_message = str(args[2]).strip()
        
        logger.info(f"收到入群申请 - 群ID：{group_id}，申请人：{applicant_qq}")
        
        # 验证必要参数
        if not group_id:
            return False, "群ID为空，无法处理"
        if not applicant_qq:
            return False, "申请人QQ为空，无法处理"
        
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
            
    except Exception as e:
        logger.error(f"处理入群申请时出错：{str(e)}", exc_info=True)
        return False, "处理申请时发生错误"

def on_event(event, bot) -> None:
    """AstrBot事件处理入口，带事件类型检查"""
    try:
        # 安全检查事件类型
        event_type = ""
        if hasattr(event, 'type'):
            event_type = str(event.type)
        
        logger.debug(f"收到事件：{event_type}")
        
        # 只处理入群申请事件
        if event_type == "join_request":
            allow_join, message = handle_join_request(event)
            
            # 执行入群操作（根据实际AstrBot API调整）
            try:
                if allow_join:
                    # 假设同意入群的方法
                    if hasattr(bot, 'approve_join_request'):
                        bot.approve_join_request(event, message)
                        logger.info(f"已同意入群 - 群ID：{getattr(event, 'group_id', '未知')}，申请人：{getattr(event, 'user_id', '未知')}")
                    else:
                        logger.warning("未找到同意入群的方法，可能需要适配AstrBot版本")
                else:
                    # 假设拒绝入群的方法
                    if hasattr(bot, 'reject_join_request'):
                        bot.reject_join_request(event, message)
                        logger.info(f"已拒绝入群 - 群ID：{getattr(event, 'group_id', '未知')}，申请人：{getattr(event, 'user_id', '未知')}，原因：{message}")
                    else:
                        logger.warning("未找到拒绝入群的方法，可能需要适配AstrBot版本")
            except Exception as e:
                logger.error(f"执行同意/拒绝操作时出错：{str(e)}", exc_info=True)
    except Exception as e:
        logger.error(f"事件处理入口出错：{str(e)}", exc_info=True)

# 插件元信息（确保格式正确，避免框架解析时出错）
plugin_info = {
    "name": "astrbot_plugin_shenqing",
    "version": "1.1.0",
    "description": "入群申请卡密验证插件，修复了列表索引越界错误",
    "author": "开发者",
    "dependencies": ["requests>=2.25.0"],
    "events": ["join_request"],
    "entry": "on_event"
}

logger.debug("入群申请验证插件加载完成")
