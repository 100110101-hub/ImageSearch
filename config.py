"""
图片搜索引擎项目配置
"""
import os

# imgbb配置
IMGBB_BASE_URL = "https://imgbb.com"

# 目录配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(BASE_DIR, "images")
FEATURES_DIR = os.path.join(BASE_DIR, "features")

# 确保目录存在
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(FEATURES_DIR, exist_ok=True)

# 模型配置
MODEL_NAME = "resnet152"  # 可选: resnet18, resnet34, resnet50, resnet101, resnet152
BATCH_SIZE = 32
FEATURE_DIM = 2048  # ResNet50/101/152的特征维度

# 搜索配置
TOP_K = 40  # 返回最相似的K张图片
SIMILARITY_THRESHOLD = 0.3  # 相似度阈值
