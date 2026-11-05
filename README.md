# AskData Pharma Finance App

医药财务分析应用，作为独立行业应用连接兼容 `domain_application/v1` 和 `platform_contract: v1` 的底座平台。

本仓库包含医药财务前端、12 个行业场景、确定性计算、演示数据生成器、知识资产、应用清单与测试。账号、鉴权、工作空间、数据源治理、知识索引、任务持久化和报告复核由底座平台提供。

## 本地开发

```bash
cd frontend
npm ci
PLATFORM_API_TARGET=http://127.0.0.1:18080 npm run dev
```

纯领域测试不需要运行平台：

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest tests/pharma/test_engine.py
```

## 测试数据

`core/modules/pharma/demo.py` 可重复生成 24 个月、4 个模拟主体和 12 个模拟药品的数据；`assets/pharma/golden-cases.json` 保存独立公式计算的固定预期。`assets/pharma/knowledge/` 中的演示制度和方法资料同样不含真实企业、患者或个人数据。

## 接入底座

- 应用合同：`assets/domain-applications/pharma-finance/manifest.json`
- 前端 API：同源 `/api/application-center/v1/.../applications/pharma-finance`
- 后端叠加：`docker build --build-arg PLATFORM_IMAGE=<immutable-platform-image> -f deploy/backend-overlay.Dockerfile .`
- 初始化和验收工具：`scripts/pharma/`

`PLATFORM_IMAGE` 应固定为不可变摘要。`core.modules.pharma.views` 是平台适配层；`catalog.py`、`demo.py` 和 `engine.py` 是不依赖平台存储的领域内核。

## 数据与合规边界

- 仓库内数据均为生成的演示数据，不包含真实企业、患者或个人数据。
- 公开知识文件是方法说明或原创摘要，不能替代现行法规、会计政策和专业判断。
- 不要提交 `.env`、平台凭据、数据库导出、隧道状态或验收账号。

## License

Apache-2.0，见 `LICENSE`。
