# RenderQ

轻量级渲染队列管理系统，专为小型动画/特效团队设计。

## 特性

- 🚀 **轻量高效** - 纯Python实现，无需复杂部署
- 🎬 **After Effects支持** - 原生aerender集成，支持分块渲染
- 🔌 **插件架构** - 易于扩展支持Blender、3ds Max等
- 🖥️ **多种界面** - PySide6 GUI / 命令行 / Web API
- 📡 **实时监控** - WebSocket推送渲染进度
- 🔧 **企业级设计** - 支持优先级、依赖、Worker池

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        RenderQ                               │
├─────────────┬─────────────┬─────────────┬──────────────────┤
│ Queue Server│ Worker Agent│  REST API   │   GUI/CLI        │
│  (调度核心)  │  (渲染执行)  │  (任务提交)  │  (监控面板)      │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬─────────┘
       │             │             │               │
       └─────────────┴─────────────┴───────────────┘
                          │
                    ┌─────┴─────┐
                    │  SQLite   │
                    │ Database  │
                    └───────────┘
```

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/renderq.git
cd renderq

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[all]"
```

### 启动服务器 (渲染机)

```bash
# 方式1: 直接运行
python -m src.server.main

# 方式2: 使用uvicorn
uvicorn src.server.main:app --host 0.0.0.0 --port 8000
```

### 启动Worker (渲染机)

```bash
# 基本启动
python -m src.worker.agent --server http://localhost:8000

# 指定配置
python -m src.worker.agent -c config/worker.yaml
```

### 启动GUI (作业机)

```bash
python -m src.client.gui.main
```

### 使用CLI

```bash
# 提交AE作业
renderq submit -p aftereffects -n "场景01" \
    --project "R:\projects\test.aep" \
    --comp "合成1" \
    --output "R:\renders\out_[#####].exr" \
    --start 1 --end 100

# 查看作业
renderq jobs

# 查看Worker
renderq workers

# 取消作业
renderq cancel <job_id>
```

## 目录结构

```
renderq/
├── src/                     # 源代码
│   ├── core/               # 核心库
│   │   ├── models.py       # 数据模型
│   │   ├── database.py     # 数据库操作
│   │   ├── scheduler.py    # 任务调度器
│   │   └── events.py       # 事件系统
│   ├── plugins/            # 渲染插件
│   │   ├── base.py         # 插件基类
│   │   ├── aftereffects.py # AE插件
│   │   └── registry.py     # 插件注册
│   ├── server/             # API服务器
│   │   └── main.py         # FastAPI应用
│   ├── worker/             # Worker代理
│   │   └── agent.py        # 执行代理
│   └── client/             # 客户端
│       ├── gui/            # PySide6 GUI
│       │   ├── main.py
│       │   ├── main_window.py
│       │   └── widgets/
│       └── cli/            # 命令行工具
│           └── renderq.py
└── config/                  # 配置文件
    ├── server.yaml
    └── worker.yaml
```

## 典型部署场景

### 双机直连渲染

```
作业机 (编辑)                    渲染机 (渲染)
┌──────────────┐                ┌──────────────┐
│   AE编辑      │   100G网络    │  RenderQ     │
│   GUI/CLI    │◄──────────────►│  Server      │
│              │                │  Worker      │
└──────────────┘                │  SSD存储池   │
                                └──────────────┘
```

1. 渲染机运行Server + Worker
2. 工程文件存储在渲染机SSD
3. 作业机通过SMB映射网络驱动器
4. 使用GUI或CLI提交任务

### 网络配置

```bash
# 渲染机 (192.168.100.1)
# 作业机 (192.168.100.2)
# 子网掩码: 255.255.255.0
# MTU: 9000 (Jumbo Frame)
```

## API文档

启动服务器后访问: `http://localhost:8000/docs`

### 主要端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/jobs | 提交作业 |
| GET | /api/jobs | 列出作业 |
| GET | /api/jobs/{id} | 获取作业详情 |
| POST | /api/jobs/{id}/suspend | 暂停作业 |
| POST | /api/jobs/{id}/resume | 恢复作业 |
| POST | /api/jobs/{id}/cancel | 取消作业 |
| GET | /api/workers | 列出Worker |
| GET | /api/plugins | 列出插件 |
| WS | /ws | WebSocket实时更新 |

## 开发插件

```python
from src.plugins.base import CommandLinePlugin
from src.core.models import Job, Task

class MyPlugin(CommandLinePlugin):
    name = "myplugin"
    display_name = "My Renderer"
    
    parameters = {
        "scene_file": {
            "type": "path",
            "label": "场景文件",
            "required": True,
        },
    }
    
    def validate(self, plugin_data: dict) -> tuple[bool, str | None]:
        if not plugin_data.get("scene_file"):
            return False, "缺少场景文件"
        return True, None
    
    def create_tasks(self, job: Job) -> list[Task]:
        return [Task(job_id=job.id, index=0)]
    
    def build_command(self, task: Task, job: Job) -> list[str]:
        return ["myrenderer", "-scene", job.plugin_data["scene_file"]]

plugin = MyPlugin()
```

## 配置说明

### server.yaml

```yaml
server:
  host: "0.0.0.0"
  port: 8000

scheduler:
  poll_interval: 1.0      # 调度轮询间隔
  worker_timeout: 60      # Worker心跳超时
  max_task_retries: 3     # 任务重试次数
```

### worker.yaml

```yaml
server_url: "http://192.168.100.1:8000"
pools: ["default"]
capabilities: ["aftereffects"]
heartbeat_interval: 10
poll_interval: 2
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request!
