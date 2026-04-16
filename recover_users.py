"""
从现有的用户URL文件恢复 discovered_users.json
"""
import os
import re
import json
from config import BASE_DIR

URLS_DIR = os.path.join(BASE_DIR, "urls")
DISCOVERED_USERS_FILE = os.path.join(URLS_DIR, "discovered_users.json")

def recover_users():
    """从 urls 文件夹中的 *_urls.json 文件恢复用户列表"""
    users = []
    seen = set()
    
    # 扫描所有 *_urls.json 文件
    pattern = re.compile(r'^(.+)_urls\.json$')
    
    for filename in os.listdir(URLS_DIR):
        match = pattern.match(filename)
        if match:
            username = match.group(1)
            user_url = f"https://{username}.imgbb.com/"
            
            if user_url not in seen:
                seen.add(user_url)
                users.append({
                    "url": user_url,
                    "fully_crawled": True,  # 有URL文件说明已爬取过
                    "used_for_discovery": False
                })
                print(f"  恢复用户: {user_url}")
    
    # 添加种子用户（如果不存在）
    seed_users = ["https://tyx199324.imgbb.com/"]
    for seed in seed_users:
        if seed not in seen:
            users.insert(0, {
                "url": seed,
                "fully_crawled": True,
                "used_for_discovery": False
            })
            print(f"  添加种子用户: {seed}")
    
    # 保存恢复后的用户列表
    data = {"users": users}
    with open(DISCOVERED_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ 恢复完成！共 {len(users)} 个用户")
    print(f"  保存位置: {DISCOVERED_USERS_FILE}")


if __name__ == "__main__":
    recover_users()
