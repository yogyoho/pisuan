# 离线包 payload 来源与版本记录

本文件记录离线部署包 payload 的组件来源、版本与完整性校验值。权威副本存放于构建机导出工作区 `<OutDir>\yuxi-offline-work\payload\`，由 export 脚本自动收入包内 `payload/`，本文件随 export 一并复制进包，是现场唯一来源说明。

## 范围裁定（2026-11-08）

**客户环境自备对话/OCR/嵌入模型与 GPU 驱动，包内不含任何模型权重与 NVIDIA 组件（2026-11-08 范围裁定）。** payload 最终仅含 Docker Engine 静态包与 compose 插件二进制。

## 组件清单

| 文件 | 版本 | 来源 URL | 下载日期 | 字节数 | sha256 |
|---|---|---|---|---|---|
| docker-29.7.2.tgz | 29.7.2 | https://mirrors.aliyun.com/docker-ce/linux/static/stable/x86_64/docker-29.7.2.tgz | 2026-11-08 | 85700518 | 803d433f226db4776e1768fd319fc6c6e4935a456acf84fcc0080818b854bc8f |
| docker-compose-linux-x86_64 | v5.7.0 | https://github.com/docker/compose/releases/download/v5.7.0/docker-compose-linux-x86_64 | 2026-11-08 | 34125466 | 7758048ad38e580f22559603312874fec8bb638d021a9e64182385fc17cc12a2 |

## 版本达标与校验记录

- Docker Engine **29.7.2** ≥ 28.0（达标）。tgz 内含 `docker/` 下 dockerd、docker、containerd、runc、containerd-shim-runc-v2、ctr、docker-init、docker-proxy 全部 8 个二进制（tar -tzf 验证）。
- docker compose **v5.7.0** ≥ v2.33.1（达标，GitHub releases/latest，2026-11-02 发布）。ELF magic `7F 45 4C 46`（linux/x86_64），已在 Linux 环境实机执行 `docker compose version` 输出 `Docker Compose version v5.7.0`。
- 完整性比对照上表 sha256 即可（`sha256sum` 逐文件比对）。

## 换源说明

- Docker Engine 原源 `https://download.docker.com/linux/static/stable/x86_64/` 在构建机网络下被连接重置（curl exit 35），改用阿里云镜像 `https://mirrors.aliyun.com/docker-ce/linux/static/stable/x86_64/`（与官方 static/stable 同源同步）；该镜像不含官方 `.sha256sum` 旁证文件，完整性以本表自算 sha256 为准。
- compose 插件自 `github.com` 直连下载，未换源、未换版本。
