"""
imgbb图片爬取模块
从imgbb用户相册页面爬取图片
支持分页、多用户相册和自动发现用户（通过followers）
URL持久化存储到硬盘，按用户分页组织
"""
import os
import re
import json
import time
import random
import hashlib
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv
from config import BASE_DIR

# 加载 .env 配置
load_dotenv(os.path.join(BASE_DIR, 'config', '.env'))

# URL存储目录
URLS_DIR = os.path.join(BASE_DIR, "urls")
os.makedirs(URLS_DIR, exist_ok=True)

# 种子用户（从这里开始发现更多用户）
IMGBB_SEED_USERS = [
    'https://tyx199324.imgbb.com/',
]

# 已发现用户池（运行时动态扩展）
_discovered_users = set()
_user_list = []

# 顺序获取图片的状态
_current_user_index = 0
_current_url_file = None  # 当前URL文件
_current_url_position = 0  # 当前URL文件中的位置（针对未训练URL）

# 无图片用户黑名单（跳过这些用户）
_empty_users = set()

# 浏览器headers（从.env加载cookies和UA）
IMGBB_HEADERS = {
    'User-Agent': os.getenv('IMGBB_USER_AGENT', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'sec-ch-ua': '"Microsoft Edge";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
    'Cookie': f'LID={os.getenv("IMGBB_COOKIE_LID", "")}; PHPSESSID={os.getenv("IMGBB_COOKIE_PHPSESSID", "")}',
}


def normalize_user_url(url):
    """规范化用户URL"""
    # 统一格式为 https://xxx.imgbb.com/
    url = url.rstrip('/')
    if not url.endswith('/'):
        url += '/'
    return url


def get_discovered_users():
    """获取已发现的用户列表"""
    if not _user_list:
        # 初始化种子用户
        for user in IMGBB_SEED_USERS:
            normalized = normalize_user_url(user)
            if normalized not in _discovered_users:
                _discovered_users.add(normalized)
                _user_list.append(normalized)
    return list(_user_list)


def discover_users_from_followers(user_url, max_users=50):
    """
    从用户的followers页面发现更多用户
    参数:
        user_url: 用户主页URL
        max_users: 最多发现多少用户
    返回: 新发现的用户URL列表
    """
    new_users = []
    followers_url = user_url.rstrip('/') + '/followers'
    
    print(f"[用户发现] 正在从 {followers_url} 发现新用户...")
    
    soup = fetch_imgbb_page(followers_url)
    if soup is None:
        return new_users
    
    # 提取用户链接
    # 模式: <a href="https://xxx.imgbb.com/">用户名</a>
    user_pattern = re.compile(r'https?://[a-zA-Z0-9_-]+\.imgbb\.com/?')
    
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        
        # 匹配imgbb用户主页链接
        match = user_pattern.match(href)
        if match:
            user_href = match.group(0)
            normalized = normalize_user_url(user_href)
            
            # 跳过已发现的用户和特殊页面
            if normalized in _discovered_users:
                continue
            if '/followers' in normalized or '/following' in normalized or '/albums' in normalized:
                continue
            
            # 添加到用户池
            _discovered_users.add(normalized)
            _user_list.append(normalized)
            new_users.append(normalized)
            
            if len(new_users) >= max_users:
                break
    
    print(f"[用户发现] 新发现 {len(new_users)} 个用户，当前用户池共 {len(_user_list)} 个")
    return new_users


def discover_users_deeply(max_total_users=100):
    """
    深度发现用户：遍历已发现用户的followers
    参数:
        max_total_users: 最大用户总数
    返回: 所有发现的用户列表
    """
    all_new = []
    
    # 遍历现有用户，发现他们的followers
    existing_users = get_discovered_users()
    
    for user_url in existing_users:
        if len(_user_list) >= max_total_users:
            break
        
        new_users = discover_users_from_followers(user_url)
        all_new.extend(new_users)
        time.sleep(1)  # 避免请求过快
    
    return all_new


def fetch_imgbb_page(url):
    """
    获取imgbb页面HTML
    返回: BeautifulSoup对象或None
    """
    try:
        response = requests.get(url, headers=IMGBB_HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"获取页面失败 {url}: {e}")
        return None


def extract_image_links_from_page(soup):
    """
    从imgbb页面HTML中提取图片链接
    返回: [(image_url, title), ...]
    """
    image_links = []
    
    if soup is None:
        return image_links
    
    # 方法1: 查找所有包含imgbb图片的a标签
    # imgbb通常使用这样的结构: <a href="https://ibb.co/xxx">
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # 匹配ibb.co链接（单张图片页面）
        if 'ibb.co/' in href or 'imgbb.com/images/' in href:
            # 提取图片标题（如果有）
            img_tag = a_tag.find('img')
            title = img_tag.get('alt', '') if img_tag else ''
            image_links.append((href, title))
    
    # 方法2: 查找data-src或src包含i.ibb.co的img标签
    for img_tag in soup.find_all('img'):
        src = img_tag.get('src', '') or img_tag.get('data-src', '')
        if 'i.ibb.co/' in src:
            # 这是直接图片链接
            title = img_tag.get('alt', '')
            image_links.append((src, title))
    
    # 去重
    seen = set()
    unique_links = []
    for url, title in image_links:
        if url not in seen:
            seen.add(url)
            unique_links.append((url, title))
    
    return unique_links


def get_direct_image_url(image_page_url):
    """
    从imgbb图片页面获取直接图片URL
    返回: (direct_url, image_bytes) 或 (None, None)
    """
    try:
        response = requests.get(image_page_url, headers=IMGBB_HEADERS, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 方法1: 查找包含直接图片链接的meta标签
        meta_tag = soup.find('meta', property='og:image')
        if meta_tag and meta_tag.get('content'):
            direct_url = meta_tag['content']
            return direct_url
        
        # 方法2: 查找data-medium或data-large属性
        img_tag = soup.find('img', {'data-medium': True})
        if img_tag and img_tag.get('data-medium'):
            return img_tag['data-medium']
        
        img_tag = soup.find('img', {'data-large': True})
        if img_tag and img_tag.get('data-large'):
            return img_tag['data-large']
        
        # 方法3: 在页面JS中提取图片URL
        for script in soup.find_all('script'):
            if script.string and 'i.ibb.co' in script.string:
                # 尝试从JS中提取URL
                match = re.search(r'https?://i\.ibb\.co/[a-zA-Z0-9]+/[^"\']+', script.string)
                if match:
                    return match.group(0)
        
        # 方法4: 查找所有img标签，找i.ibb.co的
        for img_tag in soup.find_all('img'):
            src = img_tag.get('src', '') or img_tag.get('data-src', '')
            if 'i.ibb.co/' in src and 'thumbs' not in src:
                return src
        
        return None
        
    except Exception as e:
        print(f"获取直接链接失败 {image_page_url}: {e}")
        return None


def fetch_image_from_url(image_url):
    """
    从URL获取图片字节数据
    返回: (PIL.Image, image_bytes) 或 (None, None)
    """
    try:
        response = requests.get(image_url, headers=IMGBB_HEADERS, timeout=30)
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
    """计算图片内容的MD5哈希值"""
    if image_bytes is None:
        return None
    return hashlib.md5(image_bytes).hexdigest()


def get_next_page_url(current_url, soup):
    """
    从页面中提取下一页URL
    返回: 下一页URL或None
    """
    if soup is None:
        return None
    
    # 查找分页链接
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        # 查找"下一页"或包含page参数的链接
        if ('下一页' in a_tag.text or 'Next' in a_tag.text or 
            'page=' in href or '/page/' in href):
            # 处理相对URL
            if href.startswith('/'):
                from config import IMGBB_BASE_URL
                return f"{IMGBB_BASE_URL.rstrip('/')}{href}"
            elif href.startswith('http'):
                return href
    
    return None


def fetch_imgbb_images(max_pages=10, user_urls=None):
    """
    从imgbb爬取图片
    参数:
        max_pages: 最大爬取页数
        user_urls: 用户相册URL列表，默认使用已发现用户池
    返回: [(image_url, image_hash), ...]
    """
    if user_urls is None:
        # 先尝试发现更多用户
        discover_users_deeply(max_total_users=50)
        user_urls = get_discovered_users()
    
    results = []
    
    for user_url in user_urls:
        print(f"\n[imgbb] 开始爬取: {user_url}")
        current_url = user_url
        page_count = 0
        
        while page_count < max_pages:
            page_count += 1
            print(f"[imgbb] 爬取第 {page_count} 页...")
            
            soup = fetch_imgbb_page(current_url)
            if soup is None:
                print(f"[imgbb] 页面获取失败，跳过")
                break
            
            # 提取图片链接
            image_links = extract_image_links_from_page(soup)
            print(f"[imgbb] 第 {page_count} 页找到 {len(image_links)} 个图片链接")
            
            if not image_links:
                print(f"[imgbb] 没有找到更多图片")
                break
            
            # 获取每张图片的直接URL
            for page_url, title in image_links:
                try:
                    # 如果是直接图片链接（包含i.ibb.co）
                    if 'i.ibb.co/' in page_url:
                        direct_url = page_url
                    else:
                        # 否则从图片页面获取直接URL
                        direct_url = get_direct_image_url(page_url)
                        time.sleep(1)  # 避免请求过快
                    
                    if direct_url:
                        image, image_bytes = fetch_image_from_url(direct_url)
                        if image and image_bytes:
                            img_hash = get_image_hash(image_bytes)
                            if img_hash:
                                results.append((direct_url, img_hash))
                                print(f"  ✓ 获取成功: {title or direct_url[-30:]}")
                                time.sleep(0.5)
                except Exception as e:
                    print(f"  ✗ 处理失败: {e}")
            
            # 查找下一页
            next_url = get_next_page_url(current_url, soup)
            if next_url:
                current_url = next_url
                time.sleep(2)  # 翻页间隔
            else:
                print(f"[imgbb] 没有更多页面")
                break
    
    print(f"\n[imgbb] 爬取完成，共获取 {len(results)} 张图片")
    return results


def fetch_imgbb_images_from_user(user_url, max_pages=10):
    """
    从单个用户获取所有图片
    参数:
        user_url: 用户主页URL
        max_pages: 最大爬取页数
    返回: [(image_url, image_hash), ...]
    """
    results = []
    current_url = user_url
    page_count = 0
    
    while page_count < max_pages:
        page_count += 1
        print(f"[imgbb] 爬取第 {page_count} 页...")
        
        soup = fetch_imgbb_page(current_url)
        if soup is None:
            print(f"[imgbb] 页面获取失败")
            break
        
        # 提取图片链接
        image_links = extract_image_links_from_page(soup)
        print(f"[imgbb] 第 {page_count} 页找到 {len(image_links)} 个图片链接")
        
        if not image_links:
            if page_count == 1:
                print(f"[imgbb] 该用户没有图片，跳过")
            else:
                print(f"[imgbb] 没有更多页面")
            break
        
        # 获取每张图片的直接URL
        for page_url, title in image_links:
            try:
                if 'i.ibb.co/' in page_url:
                    direct_url = page_url
                else:
                    direct_url = get_direct_image_url(page_url)
                    time.sleep(1)
                
                if direct_url:
                    image, image_bytes = fetch_image_from_url(direct_url)
                    if image and image_bytes:
                        img_hash = get_image_hash(image_bytes)
                        if img_hash:
                            results.append((direct_url, img_hash))
                            print(f"  ✓ 获取成功: {title or direct_url[-30:]}")
                            time.sleep(0.5)
            except Exception as e:
                print(f"  ✗ 处理失败: {e}")
        
        # 查找下一页
        next_url = get_next_page_url(current_url, soup)
        if next_url:
            current_url = next_url
            time.sleep(2)
        else:
            break
    
    return results


def get_user_url_filename(user_url):
    """获取用户URL存储文件名"""
    # 从URL提取用户名作为文件名
    match = re.search(r'https?://([a-zA-Z0-9_-]+)\.imgbb\.com', user_url)
    if match:
        username = match.group(1)
        return os.path.join(URLS_DIR, f"{username}_urls.json")
    return None


def load_user_urls(user_url):
    """从硬盘加载用户的URL列表（带训练标记）"""
    filename = get_user_url_filename(user_url)
    if filename and os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 兼容旧格式（纯列表）
        if isinstance(data, list):
            return {"urls": [{"url": u, "trained": False} for u in data]}
        return data
    return {"urls": []}


def save_user_urls(user_url, url_data):
    """保存用户的URL数据到硬盘（带训练标记）"""
    filename = get_user_url_filename(user_url)
    if filename:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(url_data, f, ensure_ascii=False, indent=2)
        total = len(url_data.get("urls", []))
        trained = sum(1 for u in url_data.get("urls", []) if u.get("trained", False))
        print(f"[存储] 保存 {total} 个URL（已训练 {trained}）到 {filename}")


def get_untrained_urls(user_url, count=None):
    """获取未训练的URL列表"""
    url_data = load_user_urls(user_url)
    untrained = [u for u in url_data.get("urls", []) if not u.get("trained", False)]
    if count:
        return untrained[:count]
    return untrained


def mark_url_as_trained(user_url, url):
    """标记指定URL为已训练"""
    if user_url is None:
        # 自动查找URL属于哪个用户
        users = get_discovered_users()
        for u in users:
            url_data = load_user_urls(u)
            for item in url_data.get("urls", []):
                if item.get("url") == url:
                    item["trained"] = True
                    save_user_urls(u, url_data)
                    return True
        return False
    
    url_data = load_user_urls(user_url)
    for u in url_data.get("urls", []):
        if u.get("url") == url:
            u["trained"] = True
            break
    save_user_urls(user_url, url_data)
    return True


def mark_urls_as_trained(user_url, urls):
    """批量标记URL为已训练"""
    url_data = load_user_urls(user_url)
    url_set = set(urls)
    for u in url_data.get("urls", []):
        if u.get("url") in url_set:
            u["trained"] = True
    save_user_urls(user_url, url_data)


def get_training_stats(user_url=None):
    """获取训练统计信息"""
    if user_url:
        url_data = load_user_urls(user_url)
        urls = url_data.get("urls", [])
        total = len(urls)
        trained = sum(1 for u in urls if u.get("trained", False))
        return {"total": total, "trained": trained, "untrained": total - trained}
    
    # 所有用户的统计
    users = get_discovered_users()
    total_all = 0
    trained_all = 0
    for u in users:
        stats = get_training_stats(u)
        total_all += stats["total"]
        trained_all += stats["trained"]
    return {"total": total_all, "trained": trained_all, "untrained": total_all - trained_all}


def fetch_imgbb_user_image_urls(user_url, max_pages=None):
    """
    从单个用户获取所有图片页面URL列表（不限制页数）
    自动分页爬取，保存到硬盘（带训练标记）
    使用imgbb的seek令牌进行分页
    参数:
        user_url: 用户主页URL
        max_pages: 最大爬取页数，None表示无限制
    返回: {"urls": [{"url": url, "trained": False}, ...]} 字典
    """
    # 先检查是否已存储URL
    stored_data = load_user_urls(user_url)
    if stored_data.get("urls"):
        total = len(stored_data["urls"])
        trained = sum(1 for u in stored_data["urls"] if u.get("trained", False))
        print(f"[URL获取] 从硬盘加载已存储的 {total} 个URL（已训练 {trained}）")
        return stored_data
    
    import re
    
    results = []
    seen_urls = set()  # 用于去重
    seen_seek_tokens = set()  # 记录访问过的seek令牌，防止循环
    base_url = user_url.rstrip('/')
    page_count = 0
    
    print(f"[URL获取] 开始爬取用户所有页面: {user_url}")
    
    # 从第1页开始
    current_url = base_url + '/'
    
    while True:
        page_count += 1
        
        print(f"[URL获取] 爬取第 {page_count} 页: {current_url}")
        
        soup = fetch_imgbb_page(current_url)
        if soup is None:
            print(f"[URL获取] 页面获取失败")
            break
        
        # 提取图片页面链接（ibb.co链接）
        image_links = extract_image_links_from_page(soup)
        print(f"[URL获取] 第 {page_count} 页找到 {len(image_links)} 个图片链接")
        
        if not image_links:
            if page_count == 1:
                print(f"[URL获取] 该用户没有图片，跳过")
            else:
                print(f"[URL获取] 没有更多页面")
            break
        
        # 查找下一页链接（找页码最大的那个，即前进方向）
        next_url = None
        next_seek = None
        max_page_found = page_count
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            # 匹配 page=N 参数
            page_match = re.search(r'page=(\d+)', href)
            if page_match:
                link_page = int(page_match.group(1))
                if link_page > max_page_found:
                    max_page_found = link_page
                    # 提取seek参数
                    seek_match = re.search(r'seek=([a-zA-Z0-9]+)', href)
                    if seek_match:
                        next_seek = seek_match.group(1)
                        next_url = href
                    elif not next_url:
                        # 如果没有seek参数，直接用页码
                        next_url = href
        
        # 如果seek令牌重复，说明进入循环
        if next_seek:
            if next_seek in seen_seek_tokens:
                print(f"[URL获取] 检测到seek令牌循环 ({next_seek})，停止爬取")
                break
            seen_seek_tokens.add(next_seek)
        
        # 只收集图片页面URL（不下载图片页面HTML）
        new_count = 0
        for page_url, title in image_links:
            # 只收集ibb.co或imgbb.com/images/的链接
            if ('ibb.co/' in page_url or 'imgbb.com/images/' in page_url) and page_url not in seen_urls:
                seen_urls.add(page_url)
                results.append({"url": page_url, "trained": False})
                new_count += 1
        
        print(f"  ✓ 本页新增 {new_count} 个URL，累计 {len(results)} 个")
        
        # 每5页保存一次，避免中断丢失数据
        if page_count % 5 == 0 and results:
            save_user_urls(user_url, {"urls": results})
        
        # 如果没有更多前进页面且没有新URL，停止
        if not next_url and new_count == 0:
            print(f"[URL获取] 没有更多页面")
            break
        
        # 如果下一页是更小的页码（peek back），停止
        if next_url:
            page_match = re.search(r'page=(\d+)', next_url)
            if page_match and int(page_match.group(1)) <= page_count:
                print(f"[URL获取] 下一页是后退链接，停止爬取")
                break
        
        # 构建下一页URL
        if next_url:
            if next_url.startswith('/'):
                current_url = f"{base_url}{next_url}"
            elif next_url.startswith('http'):
                current_url = next_url
            else:
                current_url = f"{base_url}/{next_url}"
        else:
            print(f"[URL获取] 没有下一页链接")
            break
        
        time.sleep(1)
        
        # 检查最大页数限制
        if max_pages and page_count >= max_pages:
            print(f"[URL获取] 达到最大页数限制 {max_pages}")
            break
    
    # 保存到硬盘
    if results:
        save_user_urls(user_url, {"urls": results})
    
    print(f"[URL获取] 共收集 {len(results)} 个图片页面URL")
    return {"urls": results}


def fetch_imgbb_user_page_urls(user_url, page_num=1):
    """
    获取指定页码的图片URL（按需加载）
    参数:
        user_url: 用户主页URL
        page_num: 页码（从1开始）
    返回: [{"url": url, "trained": bool}, ...] 列表
    """
    # 检查是否已存储URL
    stored_data = load_user_urls(user_url)
    stored_urls = stored_data.get("urls", [])
    
    # 如果已存储所有URL，直接返回对应页的数据（假设每页64个）
    if stored_urls:
        per_page = 64
        start = (page_num - 1) * per_page
        end = start + per_page
        return stored_urls[start:end]
    
    # 否则需要爬取到指定页
    current_url = user_url
    if page_num > 1:
        current_url = f"{user_url.rstrip('/')}?page={page_num}"
    
    soup = fetch_imgbb_page(current_url)
    if soup is None:
        return []
    
    image_links = extract_image_links_from_page(soup)
    page_urls = []
    for page_url, title in image_links:
        if 'ibb.co/' in page_url or 'imgbb.com/images/' in page_url:
            page_urls.append({"url": page_url, "trained": False})
    
    print(f"[URL获取] 第 {page_num} 页获取 {len(page_urls)} 个URL")
    return page_urls


def get_next_user_url_file(user_index=None):
    """获取下一个有未训练URL的用户"""
    global _current_user_index, _current_url_file, _current_url_position
    
    users = get_discovered_users()
    if not users:
        return None, None
    
    if user_index is not None:
        _current_user_index = user_index
    
    # 循环查找有未训练URL的用户
    max_attempts = len(users) * 2
    attempts = 0
    
    while attempts < max_attempts:
        attempts += 1
        
        if _current_user_index >= len(users):
            _current_user_index = 0
        
        user_url = users[_current_user_index]
        
        if user_url in _empty_users:
            _current_user_index += 1
            continue
        
        url_file = get_user_url_filename(user_url)
        
        # 如果文件不存在，先爬取并保存
        if not url_file or not os.path.exists(url_file):
            print(f"[URL获取] 正在爬取用户URL: {user_url}")
            url_data = fetch_imgbb_user_image_urls(user_url)
            urls = url_data.get("urls", []) if isinstance(url_data, dict) else []
            if not urls:
                print(f"[URL获取] 用户 {user_url} 没有图片，加入跳过列表")
                _empty_users.add(user_url)
                _current_user_index += 1
                _current_url_position = 0
                continue
            print(f"[URL获取] 用户 {user_url} 有 {len(urls)} 张图片URL")
            _current_url_position = 0
        else:
            # 检查是否有未训练的URL
            url_data = load_user_urls(user_url)
            untrained = [u for u in url_data.get("urls", []) if not u.get("trained", False)]
            if not untrained:
                print(f"[URL获取] 用户 {user_url} 所有URL已训练，跳过")
                _current_user_index += 1
                _current_url_position = 0
                continue
            _current_url_position = 0
        
        _current_url_file = url_file
        return url_file, user_url
    
    return None, None


def get_sequential_imgbb_urls(batch_size=10):
    """
    按顺序获取未训练的图片URL，自动跳过没有图片的用户和已训练的URL
    从硬盘按页加载URL，每次返回batch_size个未训练URL
    返回: [url1, url2, ...] 列表，如果没有更多URL则返回空列表
    """
    global _current_user_index, _current_url_file, _current_url_position
    
    users = get_discovered_users()
    if not users:
        print("[URL获取] 用户池为空")
        return []
    
    batch_urls = []
    max_attempts = len(users) * 3  # 最多尝试三轮
    attempts = 0
    
    while len(batch_urls) < batch_size and attempts < max_attempts:
        attempts += 1
        
        # 获取当前用户的URL文件
        url_file, user_url = get_next_user_url_file()
        if not url_file or not user_url:
            break
        
        # 加载URL数据
        url_data = load_user_urls(user_url)
        all_urls = url_data.get("urls", [])
        if not all_urls:
            _current_user_index += 1
            _current_url_position = 0
            continue
        
        # 从当前位置收集未训练的URL
        collected = 0
        while _current_url_position < len(all_urls) and len(batch_urls) < batch_size:
            url_item = all_urls[_current_url_position]
            _current_url_position += 1
            
            # 跳过已训练的URL
            if url_item.get("trained", False):
                continue
            
            url_str = url_item.get("url", url_item) if isinstance(url_item, dict) else url_item
            batch_urls.append(url_str)
            collected += 1
            
            # 如果当前用户的URL遍历完了，切换到下一个用户
            if _current_url_position >= len(all_urls):
                print(f"[URL获取] 用户 {user_url} 的URL已处理完毕")
                _current_user_index += 1
                _current_url_position = 0
                break
    
    if not batch_urls:
        print("[URL获取] 所有用户都没有更多未训练URL")
    
    return batch_urls


def fetch_random_imgbb_image():
    """
    从imgbb随机获取一张图片（已弃用）
    返回: (None, None)
    """
    return None, None


if __name__ == "__main__":
    print("=" * 60)
    print("imgbb图片爬取测试")
    print("=" * 60)
    
    # 测试获取随机图片
    print("\n测试: 获取随机图片")
    url, hash_val = fetch_random_imgbb_image()
    if url:
        print(f"成功! URL: {url}")
        print(f"Hash: {hash_val}")
    else:
        print("获取失败")
    
    # 测试批量获取
    print("\n测试: 批量获取（最多2页）")
    results = fetch_imgbb_images(max_pages=2)
    print(f"\n共获取 {len(results)} 张图片")
