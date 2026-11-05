"""Build reviewed demo documents/package. Never fetches or invents external text."""

import json
from pathlib import Path
from core.modules.pharma.catalog import APPS, SEMANTICS, ROOT, VERSION


def build():
    index = []

    def document(
        key,
        title,
        body,
        kind,
        apps,
        source_url=None,
        published_on=None,
        region="模拟集团",
        valid_from=None,
    ):
        item = dict(
            id=key,
            title=title,
            kind=kind,
            app_ids=apps,
            version=VERSION,
            source_url=source_url,
            published_on=published_on,
            applicable_region=region,
            valid_from=valid_from,
            valid_to=None,
            reviewed_on="2026-10-15",
            retrieved_on="2026-10-15" if source_url else None,
            path=f"{key}.md",
            simulated=kind == "demo_policy",
        )
        text = (
            f"# {title}\n\n版本：{VERSION}；适用范围：{region}。\n\n"
            + body
            + "\n\n"
            + (
                f"来源：{source_url}\n"
                if source_url
                else "本文为演示分析方法或模拟集团制度，不代表真实企业制度或外部政策。\n"
            )
        )
        (ROOT / "knowledge" / item["path"]).write_text(text)
        import hashlib

        item["sha256"] = hashlib.sha256(text.encode()).hexdigest()
        index.append(item)

    methods = {
        "pharma-overview": "收入为不含税销售收入。集团抵销同额内部收入和内部采购成本；仅适用于内部货物已全部外售的模拟情形。经营利润=收入-成本-期间费用，不替代净利润。",
        "pharma-budget": "使用 approved-v1 预算。利润差异=收入差异-成本差异-费用差异。零预算时完成率不可计算。主体预算简单汇总不能称为集团合并预算。",
        "pharma-product": "按相同产品规格及渠道计算环比量价：价格影响=(本期价-上期价)×两期平均数量；数量影响=收入差额-价格影响。新增或停销产品单独归入范围变化。退货保留负数量。",
        "pharma-tender": "约定量完成率=已交付数量/同一合同期间约定数量。没有约定数量时不可计算。合同价格按同一规格、地区、周期比较，不混用全国与省级规则。",
        "pharma-receivables": "应收为含税月末余额，等于发票金额减已核销收款。逾期天数=快照日-合同到期日；到期当天未逾期。账龄不能直接认定信用减值。",
        "pharma-cash": "以月末现金为预测期初值，逐周累加管理层收付计划。基准情景按计划执行；延迟情景将前4周收款后移4周。所有情景是模拟假设，不是确定预测。",
        "pharma-inventory": "按月末批次快照计算库存价值；0至90天内到期为临期，小于0天为已过期。90天未销售为滞销提示。临期风险价值不是会计减值金额。",
        "pharma-cost": "单位成本差异=(实际单位成本-标准单位成本)×实际数量。原料、规格与计量单位需一致。缺少标准投入量时，不计算耗用效率差异。",
        "pharma-rd": "研发投入按项目阶段归集，比较同版本预算。资本化仅展示账面已登记金额，证据不完整时提示复核；开发阶段并非自动满足资本化条件。",
        "pharma-expense": "费用按责任主体和期间归集。合同返利测算=适用基数×合同费率；与已计提返利对比。模拟合同假设不能替代真实合同审批。",
        "pharma-quality": "核对收入汇总与销售明细、期末现金与现金流、发票减收款与应收余额。逐主体检查，金额容差0.01元，避免正负差额相互抵销。",
        "pharma-monthly": "综合报告引用同一次数据快照及指标版本，列示经营、资金、库存、研发和质量结果。结果保持草稿，复核通过前不能宣称正式发布。",
    }
    for app, category, name, question in APPS:
        document(app + "-method", name + "：指标与口径", methods[app], "method", [app])
        document(
            app + "-scenario",
            name + "：分析操作指引",
            f"业务问题：{question}\n\n输入：授权问数空间、核算主体、会计期间、口径版本。\n\n步骤：先验证数据范围和期间完整性，再计算并查看明细，最后核实异常证据。\n\n{methods[app]}\n\n遇到缺少数据或证据时，报告必须写明限制，不补造数值。",
            "scenario",
            [app],
        )
    document(
        "demo-credit",
        "模拟集团信用与催收制度",
        "医院客户按合同到期日催收，逾期分1–30、31–60、61–90、90天以上。不得自动采取催收行动；所有建议由财务人员复核。",
        "demo_policy",
        ["pharma-receivables"],
    )
    document(
        "demo-budget",
        "模拟集团预算制度",
        "预算版本 approved-v1 已作为演示基线冻结。变更预算需形成新版本，不覆盖历史分析。研发超预算需项目负责人复核。",
        "demo_policy",
        ["pharma-budget", "pharma-rd"],
    )
    document(
        "demo-rebate",
        "模拟集团返利制度",
        "演示合同统一使用不含税销售收入的2%测算返利，当前计提比例1.8%，差额作为预设复核案例，不代表真实合同义务。",
        "demo_policy",
        ["pharma-expense"],
    )
    document(
        "public-rd",
        "财政部：研发支出核算依据摘要",
        "研究阶段支出计入当期损益；开发阶段支出需满足准则规定条件才可确认为无形资产。实际判断应依据完整准则和企业证据。本摘要不能单独构成资本化结论。",
        "public",
        ["pharma-rd"],
        "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/2006zcfb/200805/t20080519_23149.htm",
        "2008-05-19",
        "中国企业会计准则适用企业",
    )
    document(
        "public-settlement",
        "医保局：直接结算地方实践摘要",
        "医保局2025年2月公开材料介绍部分地方的集采及国谈药直接结算实践。结算范围和周期须按地区、品种、合同及适用时间核实；本文不将地方做法推广为全国统一规则。",
        "public",
        ["pharma-cash", "pharma-receivables", "pharma-tender"],
        "https://www.nhsa.gov.cn/art/2025/2/10/art_14_15653.html",
        "2025-02-10",
        "材料所列地方实践",
    )
    document(
        "public-inventory",
        "上海医药：存货效期审计案例摘要",
        "上海医药2024年度公开审计资料涉及存货效期报表与相关系统控制的测试。此案例支持建立批次及效期数据核验流程，不作为其他企业减值比例或内部制度依据。",
        "public",
        ["pharma-inventory", "pharma-quality"],
        "https://static.sse.com.cn/bond/bridge2/disclosure/announcement/c/202505/46567a_20250526_PJUP.pdf",
        None,
        "上市公司公开案例",
    )
    (ROOT / "knowledge-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    )
    (ROOT / "semantic-contract.json").write_text(
        json.dumps(SEMANTICS, ensure_ascii=False, indent=2) + "\n"
    )
    resources = []
    for app, category, name, question in APPS:
        path = ROOT.parent / "skills" / app
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(
            f"---\nname: {app}\ndescription: {name}，用于医药模拟集团的受权财务分析。\n---\n\n# {name}\n\n{methods[app]}\n\n只使用当前应用绑定的数据库和知识库；执行前校验主体、期间和数据粒度。禁止将模拟数据描述为真实企业数据。SQL只读，金额用确定性计算，知识引用需注明来源和版本。\n"
        )
        resources.append(
            dict(
                key=app,
                kind="skill",
                name=name,
                description=question,
                execution={"mode": "instructions", "skill_name": app},
                capabilities=["skill.load"],
            )
        )
    manifest = dict(
        schema_version="domain_application/v1",
        application_id="pharma-finance",
        version=VERSION,
        platform_contract="v1",
        domain_code="industry.pharma_finance",
        name="医药财务分析中心",
        bindings=[{"key": "pharma_database", "kind": "database"}]
        + [
            {"key": k, "kind": "knowledge_base"}
            for k in ("pharma_policy", "pharma_methods", "pharma_demo_policy")
        ],
        resources=resources,
        scenarios=[
            dict(
                id=a,
                name=n,
                inputs=["period", "entity", "context_revision"],
                outputs=["metrics", "table", "evidence", "warnings"],
            )
            for a, c, n, q in APPS
        ],
    )
    (ROOT.parent / "domain-applications/pharma-finance/manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    build()
