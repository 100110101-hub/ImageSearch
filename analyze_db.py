import pickle
import random
import re
import os
import json
from config import FEATURES_DIR, BASE_DIR

def analyze_users():
    # 1. Load Feature DB
    db_path = os.path.join(FEATURES_DIR, "features_db.pkl")
    if not os.path.exists(db_path):
        print("Error: features_db.pkl not found")
        return

    print("Loading database...")
    with open(db_path, 'rb') as f:
        data = pickle.load(f)
    
    all_urls = data['image_urls']
    print(f"Total images in database: {len(all_urls)}")

    # 2. Random Sample
    sample_size = 100
    if len(all_urls) > sample_size:
        sampled_urls = random.sample(all_urls, sample_size)
    else:
        sampled_urls = all_urls
    
    print(f"Randomly sampled {len(sampled_urls)} URLs for analysis.\n")

    # 3. Build URL-to-User Map from local JSONs
    print("Building URL-to-User map from local JSONs (this may take a moment)...")
    url_to_user = {}
    urls_dir = os.path.join(BASE_DIR, 'urls')
    if os.path.exists(urls_dir):
        for fname in os.listdir(urls_dir):
            if fname.endswith('_urls.json'):
                username = fname.replace('_urls.json', '')
                user_url = f"https://{username}.imgbb.com/"
                try:
                    with open(os.path.join(urls_dir, fname), 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        for item in content.get('urls', []):
                            url = item.get('url')
                            if url:
                                url_to_user[url] = user_url
                except Exception:
                    pass
    print(f"Loaded map for {len(url_to_user)} URLs.\n")

    # 4. Analyze Sample
    user_counts = {}
    unknown_count = 0
    
    for url in sampled_urls:
        # Check if URL directly contains username
        match = re.search(r'https?://([a-zA-Z0-9_-]+)\.imgbb\.com', url)
        if match:
            user_url = f"https://{match.group(1)}.imgbb.com/"
            user_counts[user_url] = user_counts.get(user_url, 0) + 1
        else:
            # Check map
            user_url = url_to_user.get(url)
            if user_url:
                user_counts[user_url] = user_counts.get(user_url, 0) + 1
            else:
                unknown_count += 1

    # 5. Report
    print("=" * 60)
    print("USER ORIGIN ANALYSIS (Sample of 100)")
    print("=" * 60)
    
    sorted_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)
    for user_url, count in sorted_users:
        print(f"  {user_url}: {count}")
    
    if unknown_count > 0:
        print("-" * 60)
        print(f"  Unknown/Orphaned URLs: {unknown_count}")
        print("  (These are likely old ibb.co links from users not in the current urls/ folder)")
    
    print("=" * 60)
    # Top 5 contributors
    if sorted_users:
        print("Top 3 Contributors in Sample:")
        for user_url, count in sorted_users[:3]:
            print(f"  🥇 {user_url} -> {count} images ({count}%)")

if __name__ == "__main__":
    analyze_users()
