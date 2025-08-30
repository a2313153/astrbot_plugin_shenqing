from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from typing import Optional
import asyncio
import requests
import re

# API地址 - 请替换为实际的API地址
API_URL = "https://qun.yz01.baby/check_key.php"

def extract_key_code(message):
    """从申请消息中提取卡密"""
    # 这里的正则表达式可以根据实际卡密格式进行调整
    # 假设卡密是由字母和数字组成的8-20位字符串
    pattern = r'[A-Za-z0-9]{8,20}'
    match = re.search(pattern, message)
    return match.group() if match else None

def verify_key(group_id, applicant_qq, key_code):
    """调用API验证卡密"""
    try:
        data = {
            'group_id': group_id,
            'applicant_qq': applicant_qq,
            'key_code': key_code
        }
        response = requests.post(API_URL, data=data, timeout=10)
        result = response.json()
        return result
    except Exception as e:
        return {'success': False, 'message': f'API调用失败: {str(e)}'}

def handle_join_request(group_id, applicant_qq, request_message):
    """处理入群申请逻辑"""
    # 从申请消息中提取卡密
    key_code = extract_key_code(request_message)
    
    if not key_code:
        return False, "未找到有效的卡密"
    
    # 验证卡密
    verification_result = verify_key(group_id, applicant_qq, key_code)
    
    if verification_result.get('success', False):
        # 卡密验证通过，允许入群
        return True, "卡密验证通过，已同意入群"
    else:
        # 卡密验证失败
        return False, verification_result.get('message', "卡密验证失败")

# 示例用法
if __name__ == "__main__":
    # 模拟入群申请
    group_id = "123456789"  # 群ID
    applicant_qq = "987654321"  # 申请人QQ
    request_message = "我要入群，我的卡密是：ABC123456"  # 入群申请消息
    
    # 处理入群申请
    allowed, message = handle_join_request(group_id, applicant_qq, request_message)
    
    if allowed:
        print(f"处理结果：允许入群。{message}")
        # 这里可以添加实际同意入群的代码
    else:
        print(f"处理结果：拒绝入群。{message}")
        # 这里可以添加拒绝入群的代码
    
    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("群聊申请审核插件已停用")
