# 项目简介

本仓库用于构建一个基础的全栈项目骨架，包含后端、前端及相关服务的目录结构，并提供基于 FastAPI 的健康检查接口，方便后续扩展。

## 仓库结构

```
backend/     # 后端 FastAPI 应用及其依赖
frontend/    # 前端代码占位目录
adapters/    # 适配器相关代码目录
services/    # 领域服务目录
projects/    # 项目或部署配置目录
config/      # 配置文件目录
scripts/     # 脚本工具目录
```

## 快速开始

### 1. 准备运行环境

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 2. 启动开发服务器

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
```

或者使用项目提供的脚本：

```bash
./scripts/run_backend.sh
```

服务启动后访问 `http://localhost:8000/healthz`，若返回如下 JSON 即表示健康检查通过：

```json
{"status": "ok"}
```

## 健康检查接口

- 路径：`GET /healthz`
- 说明：用于确认后端服务是否正常工作，返回值为 `{ "status": "ok" }`。

## 许可证

本项目使用 MIT License，详情请参阅仓库中的 [LICENSE](LICENSE) 文件。
