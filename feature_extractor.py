"""
ResNet特征提取模块
使用预训练的ResNet模型提取图片特征向量
支持从本地文件或URL提取特征
"""
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np
import requests
from io import BytesIO
from config import MODEL_NAME, FEATURE_DIM, API_URL
from download_images import HEADERS


class ResNetFeatureExtractor:
    """
    使用ResNet提取图片特征
    """
    
    def __init__(self, model_name=None, device=None):
        self.model_name = model_name or MODEL_NAME
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.transform = None
        self._build_model()
        self._build_transform()
        
    def _build_model(self):
        """
        构建ResNet模型
        """
        if self.model_name == 'resnet18':
            weights = models.ResNet18_Weights.DEFAULT
            backbone = models.resnet18(weights=weights)
            feature_dim = 512
        elif self.model_name == 'resnet34':
            weights = models.ResNet34_Weights.DEFAULT
            backbone = models.resnet34(weights=weights)
            feature_dim = 512
        elif self.model_name == 'resnet50':
            weights = models.ResNet50_Weights.DEFAULT
            backbone = models.resnet50(weights=weights)
            feature_dim = 2048
        elif self.model_name == 'resnet101':
            weights = models.ResNet101_Weights.DEFAULT
            backbone = models.resnet101(weights=weights)
            feature_dim = 2048
        elif self.model_name == 'resnet152':
            weights = models.ResNet152_Weights.DEFAULT
            backbone = models.resnet152(weights=weights)
            feature_dim = 2048
        else:
            raise ValueError(f"不支持的模型: {self.model_name}")
        
        self.model = nn.Sequential(*list(backbone.children())[:-1])
        self.model = self.model.to(self.device)
        self.model.eval()
        self.feature_dim = feature_dim
        
        print(f"模型加载成功: {self.model_name}, 特征维度: {feature_dim}, 设备: {self.device}")
        
    def _build_transform(self):
        """
        构建图片预处理流程
        """
        self.transform = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
    
    def _load_image(self, source):
        """
        从本地文件或URL加载图片
        参数:
            source: 本地文件路径 或 URL（http/https开头）
        返回: PIL.Image 或 None
        """
        try:
            if isinstance(source, Image.Image):
                return source
            elif source.startswith(('http://', 'https://')):
                # 从URL加载
                response = requests.get(source.split('#')[0], headers=HEADERS, timeout=30)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content)).convert('RGB')
                return image
            else:
                # 从本地文件加载
                image = Image.open(source).convert('RGB')
                return image
        except Exception as e:
            print(f"加载图片失败 {source}: {e}")
            return None
        
    def extract_feature(self, source):
        """
        提取图片特征
        参数:
            source: PIL.Image, 本地文件路径, 或URL
        返回: 特征向量 (numpy array)
        """
        try:
            # 加载图片
            if isinstance(source, Image.Image):
                image = source
            else:
                image = self._load_image(source)
                if image is None:
                    return None
            
            # 预处理
            input_tensor = self.transform(image)
            input_batch = input_tensor.unsqueeze(0).to(self.device)
            
            # 提取特征
            with torch.no_grad():
                feature = self.model(input_batch)
            
            # 展平并转为numpy
            feature = feature.squeeze().cpu().numpy()
            
            # L2归一化
            feature = feature / np.linalg.norm(feature)
            
            return feature
        except Exception as e:
            print(f"提取特征失败 {source}: {e}")
            return None
    
    def extract_features_batch(self, sources, batch_size=32):
        """
        批量提取图片特征
        参数:
            sources: 图片源列表（URL、路径或PIL.Image）
            batch_size: 批次大小
        返回: 特征向量列表
        """
        features = []
        print(f"开始批量提取 {len(sources)} 张图片的特征...")
        
        for i in range(0, len(sources), batch_size):
            batch_sources = sources[i:i+batch_size]
            batch_features = []
            
            for source in batch_sources:
                feature = self.extract_feature(source)
                if feature is not None:
                    batch_features.append(feature)
            
            features.extend(batch_features)
            print(f"已处理 {min(i+batch_size, len(sources))}/{len(sources)} 张图片")
        
        print(f"特征提取完成! 成功 {len(features)}/{len(sources)} 张")
        return features


if __name__ == "__main__":
    # 测试特征提取
    extractor = ResNetFeatureExtractor()
    print(f"特征维度: {extractor.feature_dim}")
