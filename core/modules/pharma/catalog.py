"""Reviewed application catalogue and immutable semantic contract."""

import hashlib
import json
from pathlib import Path

APPLICATION_ID = "pharma-finance"
VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[3] / "assets" / "pharma"
APPS = [
    (
        "pharma-overview",
        "集团经营",
        "经营驾驶舱",
        "集团收入、毛利与内部交易抵销后有什么变化？",
    ),
    ("pharma-budget", "集团经营", "预算差异分析", "收入和经营利润的预算差异来自哪里？"),
    (
        "pharma-product",
        "产品与集采",
        "产品盈利分析",
        "哪些药品、渠道的盈利下降，量价结构如何变化？",
    ),
    (
        "pharma-tender",
        "产品与集采",
        "集采履约分析",
        "中选合同约定量执行是否达标，价格是否一致？",
    ),
    (
        "pharma-receivables",
        "回款与资金",
        "医院及渠道应收",
        "哪些医院和渠道逾期，应优先复核哪些款项？",
    ),
    (
        "pharma-cash",
        "回款与资金",
        "资金预测",
        "未来13周在基准与延迟回款情景下是否存在资金缺口？",
    ),
    (
        "pharma-inventory",
        "库存与供应",
        "效期库存风险",
        "哪些批次临期、滞销，资金占用有多大？",
    ),
    (
        "pharma-cost",
        "库存与供应",
        "生产采购成本",
        "采购和生产单位成本偏差来自价格还是数量？",
    ),
    (
        "pharma-rd",
        "研发与费用",
        "研发项目投入",
        "哪些研发项目超预算，资本化判断还缺哪些证据？",
    ),
    (
        "pharma-expense",
        "研发与费用",
        "销售费用与返利",
        "费用率与返利计提是否与合同测算一致？",
    ),
    (
        "pharma-quality",
        "财务质量",
        "财务勾稽检查",
        "收入、应收与现金勾稽是否存在差异？",
    ),
    (
        "pharma-monthly",
        "财务质量",
        "月度经营报告",
        "本月经营、资金和行业风险应如何复核？",
    ),
]
TABLES = {
    "entities": "entity_id,name,segment",
    "products": "product_id,name,specification,therapy",
    "monthly": "period,entity_id,revenue,cost,expense,net_profit,budget_revenue,budget_cost,budget_expense,opening_cash,operating_cash,investing_cash,financing_cash,closing_cash,internal_revenue,internal_cost,budget_version",
    "sales": "id,period,entity_id,product_id,customer,channel,region,quantity,unit_price,revenue,cost,internal,tender_id",
    "receivables": "id,period,entity_id,customer,invoice_amount,received,outstanding,due_date,as_of,settlement",
    "inventory": "id,period,entity_id,product_id,batch,quantity,unit_cost,value,expires_on,last_sale_on,as_of",
    "tenders": "id,period,entity_id,product_id,region,agreed_quantity,delivered_quantity,contract_price,actual_price",
    "costs": "id,period,entity_id,product_id,kind,quantity,actual_unit_cost,standard_unit_cost",
    "rd": "id,period,entity_id,project,stage,spend,budget,capitalized,evidence_complete",
    "expenses": "id,period,entity_id,category,amount,rebate_base,rebate_rate,rebate_accrued",
    "cash_schedule": "id,period,entity_id,week,receipts,payments",
}
SEMANTICS = {
    "version": VERSION,
    "currency": "CNY",
    "money_unit": "元",
    "revenue_basis": "不含税；销售表负数量为退货；内部销售抵销收入及对应成本",
    "receivables_basis": "含税月末快照；到期日当天未逾期；禁止跨月累计快照",
    "inventory_basis": "月末批次快照；临期阈值90天；风险金额不等于减值金额",
    "consolidation_scope": "仅同时包含制药和配送交易双方时抵销；其他范围仅汇总",
    "budget_version": "approved-v1",
    "consolidation": "模拟内部交易已全部外售，无期末内部未实现利润；否则不支持此合并口径",
    "forecast": "管理层模拟收付计划；延迟情景仅将前4周收款后移4周；不作确定承诺",
    "rd": "资本化仅展示已登记数额和证据完整性，不自动作会计认定",
}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def definitions():
    return [
        dict(app_id=a, category=c, name=n, business_question=q) for a, c, n, q in APPS
    ]


def knowledge():
    return json.loads((ROOT / "knowledge-index.json").read_text())
