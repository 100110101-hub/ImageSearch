# 以图搜图系统

基于ResNet特征提取的图片搜索引擎，支持持续下载模式和HTTP搜索接口。
**特点：不保存本地图片，使用URL记录 + 自动去重 + 持续运行**

## 功能特性

- 🔍 **以图搜图**: 输入图片URL，找到最相似的Top-K图片
- 🌐 **URL记录**: 图片仅保存URL，不占用本地存储
- 🔄 **自动去重**: 基于MD5哈希值自动跳过重复图片
- 🚀 **持续运行**: 每下载10张图片自动提取特征并保存
- 🌍 **HTTP接口**: 提供RESTful API进行图片搜索
- 🧠 **ResNet特征**: 使用预训练ResNet模型提取图片特征
- 💾 **持久化存储**: 特征向量保存到本地，支持快速加载

## 项目结构

```
image/
├── config.py              # 配置文件
├── download_images.py     # 图片获取模块
├── feature_extractor.py   # ResNet特征提取模块
├── feature_database.py    # 特征数据库模块（含去重）
├── main.py                # 交互式主程序
├── search_service.py      # 持续运行服务 + HTTP API
├── requirements.txt       # 依赖包
├── README.md              # 使用说明
└── features/              # 特征数据库目录
    └── features_db.pkl    # 特征数据库文件
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 模式一：交互式主程序

```bash
python main.py
```

适用于手动控制、测试搜索功能。

### 模式二：持续运行服务 + HTTP搜索接口（推荐）

```bash
python search_service.py
```

服务启动后：
- 自动持续下载图片，每10张自动提取特征并保存
- 提供HTTP API用于搜索相似图片
- 按 `Ctrl+C` 停止服务

## HTTP API接口

服务运行在 `http://localhost:5000`

### 1. 搜索相似图片

**POST** `/api/search`

请求体:
```json
{
  "url": "https://example.com/image.jpg",
  "top_k": 10
}
```

响应示例:
```json
{
  "query_url": "https://example.com/image.jpg",
  "total_in_db": 39,
  "results": [
    {"url": "https://cdn.seovx.com/?mom=302#1776142423599", "similarity": 0.5397},
    {"url": "https://cdn.seovx.com/?mom=302#1776142031948", "similarity": 0.5166}
  ]
}
```

### 2. 获取数据库统计

**GET** `/api/stats`

响应示例:
```json
{
  "total_images": 39,
  "feature_dim": 2048,
  "running": true
}
```

### 3. 停止服务

**POST** `/api/stop`

### 4. API文档

**GET** `/`

返回所有可用接口信息。

## 使用示例

### Python调用

```python
import requests

# 搜索相似图片
response = requests.post('http://localhost:5000/api/search', json={
    'url': 'https://example.com/image.jpg',
    'top_k': 10
})
results = response.json()

for r in results['results']:
    print(f"相似度: {r['similarity']:.4f} | URL: {r['url']}")
```

### cURL调用

```bash
# 搜索
curl -X POST http://localhost:5000/api/search \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/image.jpg", "top_k": 5}'

# 统计
curl http://localhost:5000/api/stats
```

## 配置说明

在 `config.py` 中可以修改以下配置:

```python
# API配置
API_URL = "https://cdn.seovx.com/?mom=302"  # 直接返回随机图片

# 模型配置
MODEL_NAME = "resnet50"  # 可选: resnet18, resnet34, resnet50, resnet101, resnet152
BATCH_SIZE = 32
FEATURE_DIM = 2048

# 搜索配置
TOP_K = 10  # 返回最相似的K张图片
```

## 技术原理

1. **特征提取**: 使用预训练的ResNet模型（去掉最后分类层），提取2048维特征向量
2. **特征归一化**: 对特征向量进行L2归一化
3. **相似度计算**: 使用余弦相似度（归一化后等价于点积）
4. **去重机制**: 计算图片MD5哈希值，相同哈希值只保留一次
5. **批量处理**: 每10张图片为一组，批量提取特征并保存
6. **快速检索**: 直接计算所有特征的相似度并排序

## 注意事项

- 首次运行需要下载模型权重（约100MB）
- 建议使用GPU加速特征提取（代码自动检测）
- API访问可能需要网络代理
- 数据库文件会持续累积，定期清理不需要的特征

## 扩展方向

- [ ] 添加GUI界面
- [ ] 支持实时摄像头搜索
- [ ] 使用Faiss加速大规模检索
- [ ] 添加图片预览功能
- [ ] 支持自定义数据集
