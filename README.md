# 以图搜图系统

基于 ResNet152 的图片搜索引擎，支持大规模持续爬取、智能训练状态追踪与 HTTP/Web 搜索接口。

## 核心特性

- 🧠 **深度特征提取**：使用预训练 ResNet152 模型，输出 2048 维高精度特征向量
- 🌐 **智能 URL 管理**：仅保存图片链接至本地，配合 `trained` 状态标记避免重复计算
- 🔄 **批量流水线处理**：每 30 个 URL 为一组 → 多线程下载 → MD5 去重 → 特征提取 → 自动入库
- 📚 **分页与持久化**：支持无限规模图片检索，URL 按用户分页存储至硬盘，具备环检测机制
- 🔍 **多维度检索**：支持通过图片 URL 检索库中最相似的 Top-K 图片
- 🖥️ **Web 可视化界面**：内置 Flask 服务器，提供图形化搜索与结果展示
- 🚀 **持续运行模式**：后台线程自动发现新用户、爬取 URL 并更新特征库
- ⚡ **GPU 加速**：自动检测并调用 CUDA 加速特征提取过程

## imbb 爬取策略

### 1. 用户发现机制

系统采用**种子用户 + 社交关系扩散**的策略自动发现新用户：

- **种子初始化**：从 `IMGBB_SEED_USERS` 配置的初始用户出发，加载至 `urls/discovered_users.json`
- **Followers 深度爬取**：遍历每个用户的 followers 页面（支持 `page=N` 分页），正则匹配 `xxx.imgbb.com` 格式的用户主页链接
- **防重复发现**：每个用户记录两个关键状态标签：
  - `used_for_discovery`：标记该用户是否已用于爬取新用户，防止反复请求同一用户的 followers 列表
  - `fully_crawled`：标记该用户的图片 URL 是否已全部采集完毕
- **用户池持久化**：所有发现的用户实时保存至 JSON 文件，服务重启后可无缝恢复

```json
// urls/discovered_users.json
{
  "users": [
    {"url": "https://tyx199324.imgbb.com/", "fully_crawled": false, "used_for_discovery": true},
    {"url": "https://lyou9527.imgbb.com/", "fully_crawled": false, "used_for_discovery": false}
  ]
}
```

### 2. URL 获取与分页策略

每个用户的图片 URL 独立存储为 `urls/{username}_urls.json`，采用**无限分页 + 环检测**策略：

- **无页数限制**：`fetch_imgbb_user_image_urls()` 不设置最大页数上限，自动翻页直至到底
- **Seek 令牌环检测**：imgbb 使用 `seek=xxx` 令牌进行分页。系统记录所有访问过的 seek 值，一旦检测到重复立即停止，防止陷入无限循环
- **前进方向优先**：只跟随页码更大的分页链接（`page=N`，N > 当前页），拒绝 "peek back" 回退链接
- **URL 状态追踪**：每条 URL 存储为 `{"url": "...", "trained": bool}` 对象，避免重复提取特征
- **断点续存**：每爬取 5 页自动保存一次 URL 列表到硬盘，进程中断不丢失数据
- **智能跳过**：已完全爬取的用户不再发起新请求，直接读取本地 JSON 文件获取未训练 URL

```json
// urls/tyx199324_urls.json
{
  "urls": [
    {"url": "https://ibb.co/abc123", "trained": true},
    {"url": "https://ibb.co/def456", "trained": false}
  ]
}
```

### 3. 图片下载与处理流水线

采用**URL 优先 + 批量并发**的高效处理模式，避免一次性加载大量图片到内存：

1. **URL 采集阶段**：仅获取并保存图片页面链接到本地 JSON，不下载图片内容
2. **批次调度**：每次从本地文件读取 30 个 `trained: false` 的 URL 进入处理队列
3. **多线程并发下载**：使用 `ThreadPoolExecutor(max_workers=10)` 并发请求图片资源
   - 自动识别 URL 类型：区分 `ibb.co` 页面链接和 `i.ibb.co` 直接图片链接
   - 页面链接自动解析：通过 `og:image` meta 标签、`data-medium`/`data-large` 属性或 JS 脚本提取直接图片 URL
4. **哈希去重前置**：图片下载完成后**立即计算 MD5**，在 GPU 特征提取前进行去重判断
   - 若哈希已存在于数据库，直接跳过该图片，节省 GPU 计算资源
   - 若为新图片，继续后续特征提取流程
5. **特征提取**：ResNet152 推理 → L2 归一化 → 2048 维特征向量
6. **状态回写**：无论图片是否重复，均标记对应 URL 为 `trained: true`，避免后续重复处理

```
[本地 JSON 读取 30 个未训练 URL]
         ↓
[ThreadPoolExecutor 并发下载 10 线程]
         ↓
[下载完成 → 立即计算 MD5 哈希]
         ↓
[哈希是否在库中？] ──是──→ [跳过，标记 trained]
         ↓ 否
[ResNet152 GPU 推理]
         ↓
[L2 归一化 → 入库保存]
         ↓
[标记 trained: true → 写回 JSON]
```

## 数据库管理

### 存储结构

特征数据库使用 Pickle 序列化存储于 `features/features_db.pkl`，包含三个核心数组：

| 字段 | 类型 | 说明 |
|------|------|------|
| `image_urls` | `List[str]` | 图片 URL 列表（索引即数据库 ID） |
| `image_hashes` | `List[str]` | MD5 哈希列表，与 URL 一一对应 |
| `features` | `numpy.ndarray` | N×2048 特征向量矩阵（已 L2 归一化） |

### 去重机制

- **哈希集合快速查找**：维护 `hash_set = set(image_hashes)`，实现 O(1) 时间复杂度的重复检测
- **入库前检查**：`is_duplicate(hash)` 方法在添加前验证，相同内容的图片仅保留一次
- **下载后即时去重**：在 GPU 特征提取前计算哈希，避免对重复图片进行昂贵的推理计算

### 增量保存策略

- **批次级保存**：每处理完一批次（30 张），若有新增图片则立即调用 `db.save()` 持久化
- **全量序列化**：`pickle.dump()` 将完整数据写入 `.pkl` 文件，确保服务重启后可完整恢复
- **加载自动去重**：启动时加载 `.pkl` 文件并重建 `hash_set`，保证内存与磁盘数据一致

### 训练状态同步

- URL 级别的状态（`trained` 标记）存储于 `urls/*.json`，与特征数据库分离
- 成功添加或跳过重复图片后，立即调用 `mark_url_as_trained()` 更新 JSON 文件
- 支持自动查找 URL 所属用户：传入 `user_url=None` 时遍历所有用户文件定位并更新

## 技术架构

### 整体数据流

```
[种子用户] → [Followers 发现新用户] → [用户池持久化]
       ↓
[逐用户无限分页] → [Seek 环检测] → [URL 列表持久化]
       ↓
[批次调度 30 个 URL] → [多线程并发下载]
       ↓
[MD5 哈希计算] → [数据库去重检查]
       ↓ 否
[ResNet152 特征提取] → [L2 归一化] → [入库 + 保存]
       ↓
[标记 trained: true] → [下一批次]
```

## 项目结构

```
image/
├── config.py              # 全局配置（TOP_K, MODEL_NAME, 路径等）
├── download_imgbb.py      # imgbb 爬虫（分页、用户发现、URL 持久化）
├── feature_extractor.py   # ResNet 特征提取器（支持批量处理）
├── feature_database.py    # 特征数据库（CRUD、搜索、去重）
├── search_service.py      # Flask 服务（持续下载 + API + Web UI）
├── main.py                # 交互式主程序（CLI 模式）
├── requirements.txt       # Python 依赖
├── urls/                  # URL 持久化存储目录
│   └── {username}_urls.json
└── features/              # 特征数据库目录
    └── features_db.pkl
```

## 快速开始

### 1. 环境准备
```bash
# 创建虚拟环境（推荐）
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置 Cookies
复制示例配置文件并填入你的 Cookies：
```bash
cp config/.env.example config/.env
```

编辑 `config/.env`：
```env
IMGBB_COOKIE_LID=your_lid_value_here
IMGBB_COOKIE_PHPSESSID=your_phpsessid_value_here
IMGBB_USER_AGENT=Mozilla/5.0 ...
```

> **注意**: `config/.env` 包含敏感信息，已加入 `.gitignore`，不会提交到版本库。

### 3. 运行服务
```bash
python search_service.py
```
服务启动后将：
- 自动开始爬取并提取特征（后台线程）
- 启动 Flask Web 服务器：`http://localhost:5000`
- 按 `Ctrl+C` 优雅停止

## 使用方式

### Web 界面
访问 `http://localhost:5000` 即可使用图形化搜索界面，输入图片 URL 即可查看相似结果。

### HTTP API

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/search` | POST | 搜索相似图片 |
| `/api/stats` | GET | 获取数据库统计 |
| `/api/image/{index}` | GET | 获取指定图片（代理转发） |
| `/api/stop` | POST | 停止服务 |

#### 搜索示例
```bash
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg", "top_k": 10}'
```

#### Python 调用
```python
import requests

resp = requests.post('http://localhost:5000/api/search', json={
    'url': 'https://example.com/query.jpg',
    'top_k': 5
})
for r in resp.json()['results']:
    print(f"相似度: {r['similarity']:.4f} | {r['url']}")
```

### CLI 交互模式
```bash
python main.py
```
适用于调试、单次查询或验证搜索效果。

## 配置说明

`config.py` 核心参数：
```python
MODEL_NAME = 'resnet152'    # 特征提取模型
FEATURE_DIM = 2048          # 特征维度
TOP_K = 10                  # 默认返回结果数
BASE_DIR = '...'            # 项目根目录
```

## 工作原理

1. **用户发现**：从种子用户出发，递归爬取 `followers` 页面发现新用户
2. **分页检索**：使用 `seek/peek` 令牌实现相册翻页，内置环路检测防止死循环
3. **URL 持久化**：按用户名保存至 `urls/`，记录 `trained` 状态避免重复计算
4. **批量处理**：每次拉取 10 个未训练 URL → 下载 → MD5 校验 → 提取特征 → 标记已训练
5. **特征索引**：ResNet152 提取 2048 维向量，L2 归一化后使用余弦相似度快速检索

## 常见问题

**Q: 首次运行很慢？**
A: 首次需下载 ResNet152 预训练权重（约 230MB），后续运行将直接加载本地缓存。

**Q: 如何清空数据重新开始？**
A: 删除 `urls/` 目录下所有 JSON 文件及 `features/features_db.pkl`，重启服务即可。

**Q: 支持其他模型吗？**
A: 系统内置 resnet18/34/50/101/152，在 `config.py` 修改 `MODEL_NAME` 即可切换。

**Q: GPU 显存不足？**
A: 可改用 CPU 模式，或选择更轻量的模型（如 resnet50）。代码会自动检测设备并降级。

## 扩展方向

- [ ] 接入 Faiss 向量库加速百万级检索
- [ ] 支持本地文件夹批量导入
- [ ] 添加图片分类/标签过滤
- [ ] 分布式爬虫节点协同
- [ ] 结果预览缩略图缓存

## 依赖环境

- Python 3.8+
- PyTorch (推荐 CUDA 版本)
- Flask
- BeautifulSoup4
- Pillow
- Requests

```bash
pip install torch torchvision flask beautifulsoup4 pillow requests numpy
```
