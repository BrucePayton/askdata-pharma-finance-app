# 医药财务分析平台：实现与交付

应用 `pharma-finance` 复用问数空间、鉴权、DSC、知识索引、Redis问数执行记录、PostgreSQL后台任务和报告复核。独立前端入口为 `http://localhost:18190/pharma-finance/`。原 `/finance/` 保持独立；医药接口不接受财务应用的运行ID，反向访问也拒绝。

## 当前交付

- 六专题十二应用：集团经营、预算、产品盈利、集采履约、应收、13周资金情景、批次效期、生产采购成本、研发投入、费用返利、财务勾稽、月度报告。
- 24个月（2024-10至2026-09）、4个模拟主体、12个模拟药品，共4,000行数据。数据库和知识均标记演示用途，不包含真实企业或患者数据。
- 三空间分别绑定集团全量库、制药研发视图库、流通视图库。独立账号仅有对应数据库SELECT权限，不能跨库读取底表；空间为team可见，演示账号为owner。
- 三知识库：公开依据3篇、指标方法及场景指引24篇、模拟制度3篇。30份文档具有版本、摘要、来源、范围及文件校验值，真实完成向量索引。三篇公开资料是原创摘要，非完整法规库；上线前仍需核验适用政策。
- 固定场景使用Decimal确定性计算；报告后台执行、幂等提交、失败重领和冻结成果复用公共实现。知识检索失败明确降级，不伪造政策结论。
- 问数使用已有 `analysis.v1` 日志和任务，只增加JSON启动/轮询/取消接口，适用于不支持SSE的Cloudflare Quick Tunnel。

## 业务口径与限制

收入不含税、应收含税；禁止跨月累计应收和库存快照。到期当天未逾期。集团合并只支持模拟的“内部购入货物全部对外售出”假设，抵销同额内部收入和采购成本，不支持期末未实现利润抵销。预算按主体加总比较，明确不是集团合并预算。

量价采用相同药品规格和渠道的对称分解；新增/停销项目单列范围变化。生产成本只有单位成本比较，没有标准投入量时不推断耗用效率。研发阶段不能自动决定资本化；临期金额不能自动决定减值。研发主体后期负资金头寸是模拟融资缺口，不能作为真实资产负债表现金余额。

底座每次重新授权，读数据通过两次有界DSC查询和行数核验；跨表不是事务快照。本版本只接受冻结的模拟数据，真实ERP接入须新增快照和指标映射合同。账户级数据库权限已实现；演示组内尚未做任意配置的细粒度行权限管理界面。

## 安装与回退

前提：现有 `deployments/deployment_finance` 基础服务健康，配置了可用模型与知识嵌入模型；Docker可用。基础环境安装沿用原财务部署说明。

```bash
bash scripts/pharma/deploy.sh
python3 scripts/pharma/share.py
python3 scripts/pharma/share.py stop
```

镜像：`askdata-pharma-backend:demo-v1`、`askdata-pharma-web:demo-v1`。后端采用已验证运行时增量构建；发行时将 `PHARMA_BACKEND_BASE` 指向固定摘要，保留镜像清单。新机器无基线镜像时脚本使用仓库Dockerfile构建基线。

本机初始化状态、账号、隧道日志及验收结果放在 `~/.local/state/askdata-pharma/`，权限0700，凭据文件0600，不进入Git或镜像。`local_resources.py` 使用专属MySQL容器初始化日志中的root凭据，其他环境使用 `seed_database.py` 的 `PHARMA_MYSQL_ADMIN_*` 环境变量。数据库生成器拒绝覆盖不同指纹或部分数据；重复运行复用已创建资源和知识索引。

历史空间API会强制将创建者设为owner，因此 `assign_demo_access.py` 在部署阶段事务性赋权：只接受检查点记录、医药包安装关联及演示标记全部匹配的空间，不修改其他空间。

部署前保存现有后端/worker镜像ID和PostgreSQL备份。本次已保存在私有状态目录的 `rollback-images.json` 与 `postgres-before-pharma.sql.gz`。回退先停隧道，将Compose覆盖文件中的两个服务镜像替换为记录的旧ID，再仅重建backend/worker；停止pharma-web/share。保留新增数据库、知识库和成果，不通过删除卷回退。本次没有执行平台数据库结构迁移。

## API与执行边界

医药路径统一为 `/api/application-center/v1/workspaces/{workspace_id}/applications/pharma-finance`：

- `GET /context` 返回已授权资源、应用和口径版本。
- `POST /apps/{app_id}/calculation` 接受period、entity、context_revision；拒绝SQL、客户端dataset和连接信息。
- `POST /apps/{app_id}/runs` 增加idempotency_key，返回202；`GET /runs`、`GET /runs/{id}`读取本人运行。
- `/runs/{id}/document`与复核接口通过运行ID验证应用、空间、创建人，再调用公共成果治理。
- `POST /analysis` 复用底座问数请求；`GET /analysis/{id}`返回脱敏快照；`POST /analysis/{id}/cancel`取消当前用户执行。

应用注册仍使用仓库审核包。通用worker通过显式注册表选择实现，客户端和manifest不能提供Python模块路径。医药场景ID全部以 `pharma-` 开头，避免旧队列表唯一键未包含application_id时与财务场景冲突。未来允许跨应用同名场景前必须迁移该唯一键。

分享网关只公开医药静态页面、登录及医药受权API，不透出管理界面、通用SQL接口或旧财务入口。前端所有请求同源。演示账号不能发布报告；管理员仍在本地完成最终复核发布。

## 验证

```bash
bash scripts/pharma/check.sh
python3 scripts/pharma/verify_live.py
python3 scripts/pharma/verify_analysis.py
node scripts/pharma/browser-check.mjs
```

`assets/pharma/golden-cases.json`保存60个固定问题与独立SQLite聚合公式计算的预期指标；不是使用被测引擎生成期望。另测零分母、预算版本、量价闭合、到期日边界、部分回款、抵销方向、13周情景、逐主体勾稽以及跨用户/空间/应用拒绝。

实机验收覆盖三空间36次计算、受限主体拒绝、任务幂等、冻结报告、真实知识检索、非SSE问数、桌面和390px移动端。生产容量压测、真实ERP映射、整机故障恢复和异地备份演练不属于已通过项，不能据此宣称生产认证。

Cloudflare临时地址随重启改变，依赖本机联网及隧道进程持续运行。其[官方文档](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)明确不保证可用性且不支持SSE，本应用使用JSON轮询适配；长期固定域名需另行配置托管Tunnel。
