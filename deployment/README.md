# 医药财务应用部署规范

本规范从原分支的 `compose.pharma.yaml`、分享网关和 `scripts/pharma/deploy.sh` 抽取。它只部署医药应用层，底座继续提供身份、工作空间、知识索引、运行任务和报告复核。

## 前置条件

- 已运行兼容 `platform_contract: v1` 的底座平台。
- 已安装 `assets/domain-applications/pharma-finance/manifest.json`。
- 只读数据库、三个知识绑定和应用 worker 已在平台侧配置。
- 仓库内生成数据仅用于演示；生产 ERP 必须建立独立快照和指标映射合同。

## 构建后端叠加镜像

```bash
docker build \
  --build-arg PLATFORM_IMAGE='registry.example/platform@sha256:<digest>' \
  -f deploy/backend-overlay.Dockerfile \
  -t registry.example/askdata-pharma-finance-app-backend:1.0.0 .
```

## 初始化与验收

先在隔离环境执行：

```bash
python scripts/pharma/build_assets.py
python scripts/pharma/build_goldens.py
python scripts/pharma/seed_database.py
pytest tests/pharma
```

初始化脚本所需账号、数据库管理凭据和平台地址只通过环境变量或本机权限为 `0600` 的状态文件提供，不进入 Git 或镜像。

## 启动前端与受限网关

```bash
cd deployment
cp .env.example .env
sh deploy.sh config
sh deploy.sh build
sh deploy.sh up -d --no-build
sh deploy.sh ps
```

默认入口为 `http://127.0.0.1:18190/pharma-finance/`。网关只允许登录、空间解析和医药应用 API，不公开平台管理页面或通用 SQL 接口。

## 升级与回退

升级前保存平台数据库备份和当前后端、worker、前端镜像摘要。先更新 schema，再滚动更新后端与 worker，最后更新前端；验证三空间计算、跨应用隔离、任务幂等、冻结报告和知识降级。回退只恢复旧镜像摘要，保留新增数据、知识和成果。

原分支交付记录位于 `docs/source-branch-delivery-notes.md`，其中旧部署路径仅用于迁移追溯。
