"""
图片下载模块
从API获取随机图片并保存到本地（可选）
"""
import os
import time
import hashlib
import requests
from PIL import Image
from io import BytesIO
from config import API_URL, IMAGES_DIR

# 浏览器headers，避免被Cloudflare拦截
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# API配置说明:
# https://cdn.seovx.com/?mom=302 - 直接返回随机图片（无需二次请求）


def fetch_image_bytes(image_url):
    """
    从URL获取图片字节数据（不保存到本地）
    返回: (PIL.Image, image_bytes) 或 (None, None)
    """
    try:
        response = requests.get(image_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # 验证是否为有效图片
        image = Image.open(BytesIO(response.content))
        image.verify()
        
        image = Image.open(BytesIO(response.content))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image, response.content
    except Exception as e:
        print(f"获取图片失败 {image_url}: {e}")
        return None, None


def get_image_hash(image_bytes):
    """
    计算图片内容的哈希值用于去重
    """
    return hashlib.md5(image_bytes).hexdigest()


def download_random_image(save_dir=None, filename=None):
    """
    从API直接下载随机图片（可选保存到本地）
    API: https://cdn.seovx.com/?mom=302
    返回: (image_url, image_hash) 或 (None, None)
    """
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        # 验证图片
        image = Image.open(BytesIO(response.content))
        image.verify()
        
        image = Image.open(BytesIO(response.content))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 计算哈希用于去重
        image_hash = hashlib.md5(response.content).hexdigest()
        
        # 生成唯一URL标识
        timestamp = int(time.time() * 1000)
        unique_url = f"{API_URL}#{timestamp}"
        
        print(f"获取图片成功, hash: {image_hash[:8]}...")
        return unique_url, image_hash
    except Exception as e:
        print(f"下载图片失败: {e}")
        return None, None


def download_batch_images(count=10, delay=1.0):
    """
    批量获取图片URL（不保存到本地）
    返回: [(url, hash), ...] 成功列表
    """
    success_list = []
    print(f"开始获取 {count} 张图片...")
    print(f"使用API: {API_URL}")
    
    for i in range(count):
        print(f"正在获取第 {i+1}/{count} 张图片...")
        result = download_random_image()
        if result[0]:
            success_list.append(result)
        if i < count - 1:
            time.sleep(delay)
    
    print(f"获取完成! 成功 {len(success_list)}/{count} 张")
    return success_list


if __name__ == "__main__":
    # 测试
    download_batch_images(count=3, delay=0.5)
