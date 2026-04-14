"""
特征数据库模块
保存和加载特征向量，支持相似度搜索和图片去重
"""
import os
import pickle
import numpy as np
from config import FEATURES_DIR, TOP_K


class FeatureDatabase:
    """
    特征数据库
    存储图片URL和对应的特征向量
    支持基于URL和哈希值的去重
    """
    
    def __init__(self, db_file=None):
        if db_file is None:
            db_file = os.path.join(FEATURES_DIR, "features_db.pkl")
        
        self.db_file = db_file
        self.image_urls = []     # 图片URL列表（不再保存本地路径）
        self.image_hashes = []   # 图片内容哈希列表（用于去重）
        self.features = []       # 特征向量列表 (N x D)
        self.hash_set = set()    # 哈希集合（快速去重检查）
        
        # 尝试加载已有数据库
        if os.path.exists(self.db_file):
            self.load()
            print(f"已加载数据库: {len(self.image_urls)} 张图片")
        else:
            print("创建新的特征数据库")
    
    def is_duplicate(self, image_hash):
        """
        检查图片是否已存在（基于哈希去重）
        """
        return image_hash in self.hash_set
    
    def add_feature(self, image_url, image_hash, feature):
        """
        添加图片特征（自动去重）
        参数:
            image_url: 图片URL
            image_hash: 图片内容哈希
            feature: 特征向量 (numpy array)
        返回: True=添加成功, False=重复跳过
        """
        if self.is_duplicate(image_hash):
            print(f"  跳过重复图片: {image_hash[:8]}...")
            return False
        
        self.image_urls.append(image_url)
        self.image_hashes.append(image_hash)
        self.features.append(feature)
        self.hash_set.add(image_hash)
        return True
    
    def add_features(self, url_hash_pairs, features):
        """
        批量添加图片特征
        参数:
            url_hash_pairs: [(url, hash), ...] 列表
            features: 特征向量列表
        """
        added = 0
        skipped = 0
        
        for (url, img_hash), feature in zip(url_hash_pairs, features):
            if self.add_feature(url, img_hash, feature):
                added += 1
            else:
                skipped += 1
        
        print(f"批量添加完成: 新增 {added}, 跳过重复 {skipped}")
    
    def save(self):
        """
        保存数据库到文件
        """
        data = {
            'image_urls': self.image_urls,
            'image_hashes': self.image_hashes,
            'features': np.array(self.features) if self.features else np.array([])
        }
        
        with open(self.db_file, 'wb') as f:
            pickle.dump(data, f)
        
        print(f"数据库已保存: {self.db_file}, 共 {len(self.image_urls)} 张图片")
    
    def load(self):
        """
        从文件加载数据库
        """
        try:
            with open(self.db_file, 'rb') as f:
                data = pickle.load(f)
            
            self.image_urls = data['image_urls']
            self.image_hashes = data.get('image_hashes', [])
            self.features = data['features'].tolist() if len(data['features']) > 0 else []
            self.hash_set = set(self.image_hashes)
            
            print(f"数据库加载成功: {len(self.image_urls)} 张图片")
        except Exception as e:
            print(f"加载数据库失败: {e}")
            self.image_urls = []
            self.image_hashes = []
            self.features = []
            self.hash_set = set()
    
    def search(self, query_feature, top_k=None):
        """
        搜索最相似的图片
        参数:
            query_feature: 查询图片的特征向量
            top_k: 返回结果数量
        返回: [(image_url, similarity), ...] 按相似度降序排列
        """
        if top_k is None:
            top_k = TOP_K
        
        if len(self.features) == 0:
            print("数据库为空")
            return []
        
        # 将特征转为numpy数组
        features_array = np.array(self.features)
        query_feature = np.array(query_feature)
        
        # 计算余弦相似度 (归一化后点积=余弦相似度)
        similarities = features_array @ query_feature
        
        # 获取top_k个最相似的索引
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        # 构建结果，返回 (数据库索引, image_url, similarity)
        results = []
        for idx in top_indices:
            results.append((int(idx), self.image_urls[idx], similarities[idx]))
        
        return results
    
    def get_stats(self):
        """
        获取数据库统计信息
        """
        return {
            'total_images': len(self.image_urls),
            'feature_dim': len(self.features[0]) if self.features else 0
        }


if __name__ == "__main__":
    db = FeatureDatabase()
    print(db.get_stats())
