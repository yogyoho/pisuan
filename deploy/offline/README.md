# Pisuan 生产离线部署包

## 快速开始

    1. （若服务器无 Docker）sudo bash install-docker.sh
    2. cp deploy.conf.example deploy.conf && vi deploy.conf   # 填 3 个必填项
    3. chmod +x install.sh && sudo ./install.sh
    4. 按脚本末尾验证清单逐项核对

详细步骤与故障排查见 docs/MANUAL-DEPLOY.md；升级见 docs/MANUAL-UPGRADE.md；
第三方组件许可证义务见 docs/LICENSES.md。

## 目录结构

    install.sh / load-images.sh / install-docker.sh   # 部署脚本
    deploy.conf(.example)                             # 唯一手写配置
    .env.prod(.example)                               # 环境变量（install.sh 自动补全密钥）
    docker-compose.prod.yml                           # 核心栈（含 gitea refs 链）
    docker-compose.langfuse.yml                       # Langfuse 观测栈（独立项目名）
    images/core                                       # 镜像 tar
    payload/docker                                    # Docker 引擎 / compose 插件
    state/pisuan|postgresql|milvus|neo4j              # 全量预置数据快照（知识库/文件库/图谱/数据库/refs，原样含开发期数据）
    manifest.txt / manifest.json                        # 镜像清单（sha256.txt 在 tar.gz 旁）
    docs/                                             # 手册与许可附录

## 数据红线（绝不可执行）

    docker compose -p pisuan-prod down -v   # 删数据卷
    docker volume prune / docker system prune --volumes
    rm -rf docker/volumes                   # 删历史文件/Skill/refs 数据
    docker system prune -af                 # 删已 load 未 up 的镜像
