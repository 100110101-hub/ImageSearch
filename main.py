"""
以图搜图主程序
使用ResNet特征提取实现图片搜索
支持URL记录和自动去重
"""
import os
import time
import random
from config import IMAGES_DIR, FEATURES_DIR, TOP_K
from download_imgbb import fetch_imgbb_images, fetch_random_imgbb_image
from feature_extractor import ResNetFeatureExtractor
from feature_database import FeatureDatabase


class ImageSearchEngine:
    """
    图片搜索引擎（不保存本地图片，使用URL记录）
    """
    
    def __init__(self):
        print("=" * 60)
        print("以图搜图系统启动中...")
        print("=" * 60)
        
        # 初始化特征提取器
        self.extractor = ResNetFeatureExtractor()
        
        # 初始化特征数据库
        self.db = FeatureDatabase()
        
        print("系统初始化完成!\n")
    
    def build_database(self, image_count=50, batch_size=32, delay=1.0):
        """
        构建图片特征数据库
        参数:
            image_count: 要获取的图片数量
            batch_size: 特征提取批次大小
            delay: 获取间隔（秒）
        """
        print("\n" + "=" * 60)
        print("步骤1: 获取图片URL")
        print("=" * 60)
        
        # 获取图片URL和哈希
        url_hash_pairs = fetch_imgbb_images(max_pages=max(1, image_count // 20))
        
        if not url_hash_pairs:
            print("没有成功获取任何图片")
            return
        
        print(f"\n成功获取 {len(url_hash_pairs)} 张图片URL\n")
        
        print("=" * 60)
        print("步骤2: 提取特征（从URL直接提取）")
        print("=" * 60)
        
        # 提取特征（直接从URL提取，不保存本地）
        urls = [pair[0] for pair in url_hash_pairs]
        features = self.extractor.extract_features_batch(urls, batch_size=batch_size)
        
        if not features:
            print("没有成功提取任何特征")
            return
        
        # 添加到数据库（自动去重）
        self.db.add_features(url_hash_pairs, features)
        
        # 保存数据库
        self.db.save()
        
        print(f"\n数据库构建完成! 共 {len(self.db.image_urls)} 张图片\n")
    
    def search_by_url(self, query_url, top_k=None):
        """
        通过URL搜索相似图片
        参数:
            query_url: 查询图片URL
            top_k: 返回结果数量
        """
        if top_k is None:
            top_k = TOP_K
            
        print(f"\n搜索查询图片: {query_url}")
        
        # 提取查询图片特征
        query_feature = self.extractor.extract_feature(query_url)
        if query_feature is None:
            print("特征提取失败")
            return []
        
        # 搜索相似图片
        start_time = time.time()
        results = self.db.search(query_feature, top_k=top_k)
        search_time = time.time() - start_time
        
        # 打印结果
        print(f"\n搜索结果 (耗时: {search_time:.3f}s):")
        print("-" * 60)
        for i, (db_idx, image_url, similarity) in enumerate(results, 1):
            print(f"{i:2d}. 相似度: {similarity:.4f} | {image_url}")
        print("-" * 60)
        
        return results
    
    def search_random_image(self, top_k=None):
        """
        从数据库中随机选择一张图片进行搜索
        """
        if top_k is None:
            top_k = TOP_K
        
        if len(self.db.image_urls) == 0:
            print("数据库为空")
            return []
        
        # 随机选择一张图片
        query_url = random.choice(self.db.image_urls)
        print(f"\n随机选择查询图片URL: {query_url}")
        
        return self.search_by_url(query_url, top_k=top_k)
    
    def show_stats(self):
        """
        显示数据库统计信息
        """
        stats = self.db.get_stats()
        print("\n数据库统计:")
        print(f"  图片总数: {stats['total_images']}")
        print(f"  特征维度: {stats['feature_dim']}")
        print(f"  数据库文件: {self.db.db_file}\n")


def main():
    """
    主函数 - 演示以图搜图流程
    """
    engine = ImageSearchEngine()
    engine.show_stats()
    
    if len(engine.db.image_urls) == 0:
        print("数据库为空，开始获取图片并构建...")
        engine.build_database(image_count=30)
    
    engine.show_stats()
    
    if len(engine.db.image_urls) == 0:
        print("数据库仍然为空，无法进行搜索测试")
        return
    
    # 交互式菜单
    while True:
        print("\n" + "=" * 60)
        print("以图搜图系统 - 请选择操作:")
        print("=" * 60)
        print("1. 随机选择一张图片进行搜索测试")
        print("2. 从URL下载图片并搜索")
        print("3. 获取更多图片并更新数据库")
        print("4. 显示数据库统计")
        print("5. 退出程序")
        print("=" * 60)
        
        try:
            choice = input("\n请输入选项 (1-5): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n感谢使用以图搜图系统!")
            break
        
        if choice == "1":
            engine.search_random_image(top_k=10)
        elif choice == "2":
            url = input("请输入图片URL: ").strip()
            if url:
                engine.search_by_url(url, top_k=10)
        elif choice == "3":
            count = input("请输入要获取的图片数量 (默认20): ").strip()
            count = int(count) if count.isdigit() else 20
            engine.build_database(image_count=count)
        elif choice == "4":
            engine.show_stats()
        elif choice == "5":
            print("\n感谢使用以图搜图系统!")
            break
        else:
            print("无效选项，请重新输入")


if __name__ == "__main__":
    main()
