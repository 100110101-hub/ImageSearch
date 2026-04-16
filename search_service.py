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
from config import TOP_K, BASE_DIR
from download_imgbb import get_sequential_imgbb_urls, discover_users_deeply, IMGBB_HEADERS  # headers 从 config/.env 加载
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
        self._direct_url_cache = {}  # 缓存页面URL→直接图片URL的映射
        
        print("服务初始化完成!\n")
    
    def start_continuous_download(self, interval=0.3, batch_size=30):
        """
        持续下载图片并提取特征
        参数:
            interval: 每批次处理间隔（秒）
            batch_size: 每批处理数量（默认30）
        """
        self.running = True
        print(f"\n开始持续下载模式 (间隔: {interval}s, 批次: {batch_size})")
        print("图片来源: imgbb")
        print("按 Ctrl+C 停止...\n")
        
        while self.running:
            try:
                print(f"[下载] 正在获取 {batch_size} 个图片URL...")
                
                # 获取一批图片URL（不下载图片）
                urls = get_sequential_imgbb_urls(batch_size=batch_size)
                
                if not urls:
                    print("[下载] 没有获取到URL，等待后重试...")
                    time.sleep(interval)
                    continue
                
                print(f"[下载] 获取到 {len(urls)} 个URL，开始下载和处理...")
                
                # 下载图片、计算哈希、提取特征（在处理前自动计算哈希）
                results = self.extractor.download_and_extract_batch(urls)
                
                if results:
                    # 去重并添加到数据库
                    added = 0
                    skipped = 0
                    
                    for url, image_hash, feature in results:
                        if not self.db.is_duplicate(image_hash):
                            self.db.add_feature(url, image_hash, feature)
                            added += 1
                            self.total_downloaded += 1
                            # 标记URL为已训练
                            from download_imgbb import mark_url_as_trained
                            mark_url_as_trained(None, url)  # 自动查找用户
                            print(f"  ✓ 已添加 (hash: {image_hash[:8]})")
                        else:
                            skipped += 1
                            # 即使重复也标记为已训练，避免重复处理
                            from download_imgbb import mark_url_as_trained
                            mark_url_as_trained(None, url)
                            print(f"  ✗ 重复跳过 (hash: {image_hash[:8]})")
                    
                    # 保存数据库
                    if added > 0:
                        self.db.save()
                        print(f"[保存] 数据库已更新: 新增 {added}, 跳过 {skipped}, 当前共 {len(self.db.image_urls)} 张图片\n")
                    else:
                        print(f"[跳过] 本批次全部重复，跳过 {skipped} 张\n")
                else:
                    print("[警告] 没有成功处理任何图片\n")
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n\n收到停止信号...")
                self.stop()
                break
            except Exception as e:
                print(f"  ✗ 错误: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(interval)
        
        print("下载服务已停止")
    
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
    from download_imgbb import get_direct_image_url, IMGBB_HEADERS
    
    # 从数据库获取图片URL
    if index >= len(engine.db.image_urls):
        return jsonify({"error": "图片不存在"}), 404
    
    image_url = engine.db.image_urls[index]
    
    try:
        # 如果是ibb.co页面URL，先获取直接图片URL（使用缓存）
        direct_url = image_url
        if 'ibb.co/' in image_url and 'i.ibb.co' not in image_url:
            if image_url in engine._direct_url_cache:
                direct_url = engine._direct_url_cache[image_url]
            else:
                direct_url = get_direct_image_url(image_url)
                if not direct_url:
                    return jsonify({"error": "无法获取直接图片URL"}), 500
                engine._direct_url_cache[image_url] = direct_url
        
        # 添加时间戳参数避免缓存
        timestamp = int(time.time() * 1000)
        cache_busted_url = f"{direct_url}{'&' if '?' in direct_url else '?'}_t={timestamp}"
        
        response = requests.get(cache_busted_url, headers=IMGBB_HEADERS, timeout=30)
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
    
    # 先发现一批用户
    print("\n" + "=" * 60)
    print("正在发现imgbb用户...")
    print("=" * 60)
    discover_users_deeply(max_total_users=50)
    print()
    
    # 启动持续下载线程
    download_thread = threading.Thread(
        target=engine.start_continuous_download,
        kwargs={"interval": 0.3, "batch_size": 30},
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
