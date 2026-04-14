"""
以图搜图服务 - 持续运行模式 + HTTP搜索接口
功能：
1. 持续下载图片并提取特征（每10张自动保存）
2. 提供HTTP API进行图片搜索
3. 提供图形化Web界面
"""
import os
import time
import threading
import requests
from flask import Flask, request, jsonify, send_from_directory, Response
from config import TOP_K, API_URL, BASE_DIR
from download_images import download_random_image, HEADERS
from feature_extractor import ResNetFeatureExtractor
from feature_database import FeatureDatabase

# 创建Flask应用
STATIC_DIR = os.path.join(BASE_DIR, 'static')
app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='/static')

# 全局变量
engine = None
running = False
download_thread = None


class ImageSearchService:
    """图片搜索服务 - 持续下载+搜索"""
    
    def __init__(self):
        print("=" * 60)
        print("以图搜图服务启动中...")
        print("=" * 60)
        
        self.extractor = ResNetFeatureExtractor()
        self.db = FeatureDatabase()
        self.running = False
        self.download_count = 0
        self.total_downloaded = 0
        
        print("服务初始化完成!\n")
    
    def start_continuous_download(self, interval=2.0, batch_size=10):
        """
        持续下载图片并提取特征
        参数:
            interval: 每张图片下载间隔（秒）
            batch_size: 每批处理数量（默认10）
        """
        self.running = True
        print(f"\n开始持续下载模式 (间隔: {interval}s, 批次: {batch_size})")
        print("按 Ctrl+C 停止...\n")
        
        batch_urls = []
        batch_hashes = []
        
        while self.running:
            try:
                print(f"[下载] 第 {self.total_downloaded + 1} 张...")
                result = download_random_image()
                
                if result[0]:
                    url, img_hash = result
                    
                    # 检查重复
                    if not self.db.is_duplicate(img_hash):
                        batch_urls.append(url)
                        batch_hashes.append(img_hash)
                        self.total_downloaded += 1
                        print(f"  ✓ 已获取 (hash: {img_hash[:8]})")
                    else:
                        print(f"  ✗ 重复跳过 (hash: {img_hash[:8]})")
                else:
                    print(f"  ✗ 获取失败")
                
                # 每10张处理一次
                if len(batch_urls) >= batch_size:
                    self._process_batch(batch_urls, batch_hashes)
                    batch_urls = []
                    batch_hashes = []
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n\n收到停止信号...")
                self.stop()
                break
            except Exception as e:
                print(f"  ✗ 错误: {e}")
                time.sleep(interval)
        
        # 处理剩余图片
        if batch_urls:
            self._process_batch(batch_urls, batch_hashes)
        
        print("下载服务已停止")
    
    def _process_batch(self, urls, hashes):
        """处理一批图片URL"""
        print(f"\n[处理] 正在提取 {len(urls)} 张图片特征...")
        
        # 提取特征
        features = self.extractor.extract_features_batch(urls)
        
        if features:
            url_hash_pairs = list(zip(urls, hashes))
            self.db.add_features(url_hash_pairs, features)
            self.db.save()
            print(f"[保存] 数据库已更新，当前共 {len(self.db.image_urls)} 张图片\n")
        else:
            print("[警告] 没有成功提取任何特征\n")
    
    def stop(self):
        """停止服务"""
        self.running = False
    
    def search_by_url(self, query_url, top_k=10):
        """通过URL搜索相似图片"""
        print(f"[搜索] 查询: {query_url}")
        
        query_feature = self.extractor.extract_feature(query_url)
        if query_feature is None:
            return {"error": "特征提取失败"}
        
        results = self.db.search(query_feature, top_k=top_k)
        
        return {
            "query_url": query_url,
            "total_in_db": len(self.db.image_urls),
            "results": [
                {
                    "url": url,
                    "image_url": f"/api/image/{db_index}",
                    "similarity": float(sim)
                }
                for db_index, url, sim in results
            ]
        }
    
    def get_stats(self):
        """获取服务统计"""
        return {
            "total_images": len(self.db.image_urls),
            "feature_dim": self.db.get_stats()["feature_dim"],
            "running": self.running
        }


# HTTP API路由
@app.route('/api/search', methods=['POST'])
def api_search():
    """搜索相似图片"""
    data = request.get_json()
    
    if not data or 'url' not in data:
        return jsonify({"error": "请提供图片URL"}), 400
    
    query_url = data['url']
    top_k = data.get('top_k', 10)
    
    results = engine.search_by_url(query_url, top_k=top_k)
    
    if "error" in results:
        return jsonify(results), 400
    
    return jsonify(results)


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """获取数据库统计"""
    return jsonify(engine.get_stats())


@app.route('/api/image/<int:index>', methods=['GET'])
def api_get_image(index):
    """代理获取图片，避免浏览器缓存"""
    # 从数据库获取图片URL
    if index >= len(engine.db.image_urls):
        return jsonify({"error": "图片不存在"}), 404
    
    image_url = engine.db.image_urls[index]
    
    try:
        # 添加时间戳参数避免缓存
        timestamp = int(time.time() * 1000)
        cache_busted_url = f"{image_url}{'&' if '?' in image_url else '?'}_t={timestamp}"
        
        response = requests.get(cache_busted_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        return Response(response.content, mimetype='image/jpeg')
    except Exception as e:
        print(f"获取图片失败 (index={index}): {e}")
        return jsonify({"error": "获取图片失败"}), 500


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """停止服务"""
    engine.stop()
    return jsonify({"message": "服务已停止"})


@app.route('/', methods=['GET'])
def index():
    """图形化界面"""
    return send_from_directory(STATIC_DIR, 'index.html')


@app.route('/api', methods=['GET'])
def api_index():
    """API文档"""
    return jsonify({
        "service": "以图搜图服务",
        "version": "2.0",
        "ui": "http://localhost:5000",
        "endpoints": {
            "POST /api/search": {
                "description": "搜索相似图片",
                "body": {"url": "图片URL", "top_k": 10}
            },
            "GET /api/stats": {
                "description": "获取数据库统计"
            },
            "POST /api/stop": {
                "description": "停止服务"
            }
        }
    })


def main():
    """主函数"""
    global engine
    
    # 初始化服务
    engine = ImageSearchService()
    
    # 启动持续下载线程
    download_thread = threading.Thread(
        target=engine.start_continuous_download,
        kwargs={"interval": 2.0, "batch_size": 10},
        daemon=True
    )
    download_thread.start()
    
    # 启动Flask HTTP服务
    print("\n" + "=" * 60)
    print("HTTP搜索接口已启动: http://localhost:5000")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n服务已停止")
        engine.stop()


if __name__ == "__main__":
    main()
