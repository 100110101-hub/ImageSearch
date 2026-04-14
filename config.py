"""
图片搜索引擎项目配置
"""
import os

# API配置
# https://cdn.seovx.com/?mom=302 - 直接返回随机图片（无需二次请求）
API_URL = "https://cdn.seovx.com/?mom=302"

# 目录配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
FEATURES_DIR = os.path.join(BASE_DIR, "features")

# 确保目录存在
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(FEATURES_DIR, exist_ok=True)

# 模型配置
MODEL_NAME = "resnet50"  # 可选: resnet18, resnet34, resnet50, resnet101, resnet152
BATCH_SIZE = 32
FEATURE_DIM = 2048  # ResNet50的特征维度

# 搜索配置
TOP_K = 10  # 返回最相似的K张图片
SIMILARITY_THRESHOLD = 0.5  # 相似度阈值
