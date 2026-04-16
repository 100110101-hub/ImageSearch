"""
重建指定用户的图片URL链接文件
功能：
1. 从 features_db.pkl 读取已训练的图片URL
2. 重新爬取用户所有图片链接
3. 生成新的 JSON 文件，智能匹配并排除已训练的图片
"""
import os
import sys
import urllib.parse
from download_imgbb import (
    fetch_imgbb_user_image_urls,
    normalize_user_url,
    load_user_urls,
    save_user_urls,
    get_user_url_filename,
    load_discovered_users
)
from feature_database import FeatureDatabase

# 需要重建的用户URL（修改这里）
TARGET_USER_URL = "https://lyou9527.imgbb.com/"


def normalize_url(url):
    """标准化URL以便比较（去除查询参数，统一小写）"""
    url = url.strip().lower()
    try:
        parsed = urllib.parse.urlparse(url)
        # 重建 URL，去除 query 和 fragment
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
    except:
        return url


def get_trained_urls_from_db():
    """从特征数据库获取已训练的图片URL集合（标准化后）"""
    db = FeatureDatabase()
    if not db.image_urls:
        print("[DB] 数据库为空，所有图片都将被视为未训练")
        return set()
    
    # 返回标准化后的 URL 集合，去除参数干扰
    trained_urls = {normalize_url(url) for url in db.image_urls}
    print(f"[DB] 已加载 {len(db.image_urls)} 张已训练图片的URL (标准化后: {len(trained_urls)})")
    return trained_urls


def rebuild_user_urls():
    """重建用户的URL列表"""
    print("=" * 60)
    print(f"重建用户URL: {TARGET_USER_URL}")
    print("=" * 60)
    
    # 0. 立即加载用户列表
    print("\n[0/5] 初始化用户池...")
    load_discovered_users()
    
    # 1. 获取已训练的URL
    print("\n[1/5] 加载特征数据库...")
    trained_urls = get_trained_urls_from_db()
    
    # 2. 重新爬取用户所有图片链接
    print("\n[2/5] 重新爬取用户图片链接...")
    user_url = normalize_user_url(TARGET_USER_URL)
    
    # 删除旧文件以强制重新爬取
    old_file = get_user_url_filename(user_url)
    if old_file and os.path.exists(old_file):
        print(f"  删除旧文件: {old_file}")
        os.remove(old_file)
    
    # 爬取新链接
    url_data = fetch_imgbb_user_image_urls(user_url)
    all_urls = url_data.get("urls", [])
    print(f"  爬取到 {len(all_urls)} 个图片URL")
    
    if not all_urls:
        print("[警告] 没有找到任何图片URL！")
        return
    
    # 3. 构建新的URL列表，智能匹配训练状态
    print("\n[3/5] 构建新URL列表并匹配状态...")
    new_url_list = []
    trained_count = 0
    untrained_count = 0
    
    for item in all_urls:
        url = item.get("url") if isinstance(item, dict) else item
        original_url = url  # 保留原始 URL（可能带有参数）
        
        # 使用标准化后的 URL 进行匹配
        is_trained = normalize_url(url) in trained_urls
        
        new_url_list.append({
            "url": original_url,
            "trained": is_trained
        })
        
        if is_trained:
            trained_count += 1
        else:
            untrained_count += 1
    
    print(f"  已训练 (匹配成功): {trained_count} 张")
    print(f"  未训练 (新增/匹配失败): {untrained_count} 张")
    
    # 4. 保存新文件
    print("\n[4/5] 保存新的URL文件...")
    save_user_urls(user_url, {"urls": new_url_list})
    
    # 5. 更新用户发现状态（此时用户池已初始化，安全标记）
    print("\n[5/5] 更新用户发现状态...")
    from download_imgbb import _user_list, mark_user_fully_crawled, _discovered_users
    
    # 确保用户池中有该用户
    normalized_url = normalize_user_url(user_url)
    if normalized_url not in _discovered_users:
        print(f"  用户 {normalized_url} 不在用户池中，添加...")
        _user_list.append({"url": normalized_url, "fully_crawled": False, "used_for_discovery": False})
        _discovered_users.add(normalized_url)
    
    # 标记为已完全爬取
    mark_user_fully_crawled(normalized_url)
    print(f"  ✓ {normalized_url} 已标记为 fully_crawled")
    
    print("\n" + "=" * 60)
    print("重建完成！")
    print(f"总计: {len(new_url_list)} 张图片")
    print(f"已训练: {trained_count} 张")
    print(f"待训练: {untrained_count} 张")
    print("=" * 60)


if __name__ == "__main__":
    # 可以从命令行指定用户URL
    if len(sys.argv) > 1:
        TARGET_USER_URL = sys.argv[1]
        print(f"使用命令行指定的用户: {TARGET_USER_URL}")
    
    rebuild_user_urls()
