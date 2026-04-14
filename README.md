# 以图搜图系统

基于 ResNet152 的图片搜索引擎，支持大规模持续爬取、智能训练状态追踪与 HTTP/Web 搜索接口。

## 核心特性

- 🧠 **深度特征提取**：使用预训练 ResNet152 模型，输出 2048 维高精度特征向量
- 🌐 **智能 URL 管理**：仅保存图片链接至本地，配合 `trained` 状态标记避免重复计算
- 🔄 **批量流水线处理**：每 10 个 URL 为一组 → 下载 → MD5 去重 → 特征提取 → 自动入库
- 📚 **分页与持久化**：支持无限规模图片检索，URL 按用户/页码分页存储至硬盘，具备环检测机制
- 🔍 **多维度检索**：支持通过图片 URL 检索库中最相似的 Top-K 图片
- 🖥️ **Web 可视化界面**：内置 Flask 服务器，提供图形化搜索与结果展示
- 🚀 **持续运行模式**：后台线程自动发现新用户、爬取 URL 并更新特征库
- ⚡ **GPU 加速**：自动检测并调用 CUDA 加速特征提取过程

## 技术架构

### 数据流
```
[imgbb 用户页] → [分页爬取 URL] → [本地 JSON 持久化]
       ↓
[顺序读取 10 个 URL] → [解析直接图片链接]
       ↓
[下载图片] → [MD5 哈希计算] → [库中已存在？是 → 跳过]
                                       ↓ 否
[ResNet152 特征提取] → [L2 归一化] → [标记 trained: true] → [入库保存]
```

### URL 状态追踪
系统维护每个 URL 的训练状态，避免重复计算：
```json
[
  {"url": "https://ibb.co/xxx", "trained": true},
  {"url": "https://ibb.co/yyy", "trained": false}
]
```

### 特征数据库
- **格式**：`features/features_db.pkl` (Pickle 序列化)
- **结构**：存储 URL、MD5 哈希、2048 维特征向量及元数据
- **去重机制**：基于内容级 MD5 哈希，相同图片仅保留一次

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

### 2. 配置
在 `download_imgbb.py` 中配置 Cookies（如需访问受限内容）：
```python
IMGBB_HEADERS = {
    'Cookie': 'LID=...; PHPSESSID=...',
    'User-Agent': 'Mozilla/5.0 ...',
}
```

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
