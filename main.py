import requests
import json

# 配置API地址（替换为你的PHP接口地址）
VERIFY_API_URL = "https://qun.yz01.baby/verify_card.php"

def handle_join_request(apply_message):
    """
    处理入群申请
    :param apply_message: 入群申请消息内容（字符串）
    :return: 是否同意入群（bool）
    """
    # 从申请消息中提取卡密（假设卡密是消息中的独立字符串，可根据实际格式调整提取逻辑）
    # 示例：消息格式为"申请入群，卡密：TEST123456"
    card_code = None
    if "卡密：" in apply_message:
        card_code = apply_message.split("卡密：")[-1].strip()
    
    if not card_code:
        print("未在申请消息中找到卡密")
        return False  # 无卡密则拒绝
    
    # 调用API验证卡密
    try:
        response = requests.post(
            VERIFY_API_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"card_code": card_code})
        )
        result = response.json()
        
        if result.get("status") == "success":
            print(f"卡密 {card_code} 验证通过，同意入群")
            return True
        else:
            print(f"卡密 {card_code} 验证失败：{result.get('msg')}")
            return False
    except Exception as e:
        print(f"API调用失败：{str(e)}")
        return False  # 接口异常时拒绝入群

# 测试示例
if __name__ == "__main__":
    # 模拟入群申请消息
    test_messages = [
        "申请入群，卡密：TEST123456",  # 有效卡密
        "申请入群，卡密：INVALID123",  # 无效卡密
        "申请入群，卡密：VALID7890",   # 有效卡密
        "单纯申请入群"                 # 无卡密
    ]
    
    for msg in test_messages:
        print(f"\n处理消息：{msg}")
        if handle_join_request(msg):
            print("操作：同意入群")
        else:
            print("操作：拒绝入群")
