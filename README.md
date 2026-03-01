# CSV Sync Server

一个基于 FastAPI 的 CSV 文件上传服务，支持文件验证、日志记录和配套客户端。

## How to Run

### Docker 启动（推荐）

```bash
# 一键启动（自动安装依赖）
./start.sh

# 或手动启动
docker-compose up --build -d
# 如果 docker-compose 不可用，使用：
docker compose up --build -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 本地启动

```bash
# 进入项目目录
cd Backend/sync-server

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Services

| 服务 | 端口 | 说明 |
|------|------|------|
| CSV Sync Server | 8000 | FastAPI 文件上传服务 |

### API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/upload` | POST | 上传 CSV 文件 |
| `/api/v1/health` | GET | 健康检查 |
| `/docs` | GET | Swagger UI 文档 |
| `/redoc` | GET | ReDoc 文档 |

### 使用示例

```bash
# 使用客户端（从项目根目录执行）
python3 client/client.py Backend/sync-server/test_data.csv --url http://localhost:8000

# 使用 curl（从项目根目录执行）
curl -X POST http://localhost:8000/api/v1/upload \
     -F "file=@Backend/sync-server/test_data.csv"
```

#### 成功响应示例（HTTP 200）

```json
{
  "success": true,
  "message": "File uploaded successfully",
  "filename": "20260301_143021_a3f8c2d1e4b5.csv",
  "file_path": "2026-03-01/20260301_143021_a3f8c2d1e4b5.csv",
  "file_size": 1024
}
```

#### 失败响应示例

```bash
# 文件类型不支持（HTTP 400）
{"detail": "Invalid file type. Only .csv allowed."}

# 文件超过 10MB（HTTP 413）
{"detail": "File too large. Maximum size is 10MB."}

# 文件内容非合法 CSV（HTTP 400）
{"detail": "File content is not valid CSV (binary data detected)."}
```

## 测试账号

本项目为文件上传服务，无需账号认证。

## 题目内容

在sync-server目录下初始化一个新的FastAPI项目，项目结构应符合Python应用开发最佳实践。使用FastAPI框架实现以下服务端功能： 

1. 创建一个RESTful API接口，专门用于接收客户端上传的CSV文件。该接口需支持multipart/form-data格式，包含文件验证机制（验证文件类型为.csv、检查文件大小限制），并将通过验证的文件存储到本地指定路径（需明确文件存储目录结构和命名规则）。 

同时，开发一个配套的客户端程序，该客户端应具备以下功能：读取本地CSV文件，通过HTTP请求将文件上传至上述FastAPI服务的文件接收接口，处理可能的网络异常和服务端返回的错误信息，并提供上传状态反馈。 

服务端需实现必要的错误处理、日志记录功能，并提供API文档（通过FastAPI自带的Swagger UI）。客户端需支持命令行参数配置（如文件路径、服务端URL等），并具有良好的用户交互体验。

---

## 项目结构

```
client/
└── client.py                # 命令行客户端（独立于服务端）
Backend/
├── Dockerfile
└── sync-server/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py          # FastAPI 应用入口
    │   ├── api/
    │   │   ├── __init__.py
    │   │   └── upload.py    # 上传接口
    │   └── core/
    │       ├── __init__.py
    │       ├── config.py    # 配置管理
    │       └── logging.py   # 日志配置
    ├── tests/               # 单元测试
    │   ├── conftest.py
    │   ├── test_upload.py
    │   └── test_client.py
    └── requirements.txt
```

## 文件存储规则

- 存储路径: `uploads/{YYYY-MM-DD}/{timestamp}_{uuid}.csv`
- 文件大小限制: 10MB
- 支持格式: .csv

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| UPLOAD_DIR | ./uploads | 文件存储目录 |
| MAX_FILE_SIZE | 10485760 | 最大文件大小(字节) |
| HOST | 0.0.0.0 | 服务监听地址 |
| PORT | 8000 | 服务端口 |
| CORS_ORIGINS | `*`（全部允许） | 允许的跨域来源，逗号分隔；生产环境应精确填写，例如 `https://app.example.com` |

## 运行测试

```bash
cd Backend/sync-server
python3 -m pytest tests/ -v
```
