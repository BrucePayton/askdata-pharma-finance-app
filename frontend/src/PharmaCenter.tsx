import { useEffect, useRef, useState } from "react";
import {
  platformRequest as api,
  platformToken,
  setPlatformToken,
} from "./platform";
import {
  analysisReducer,
  initialAnalysisState,
} from "./shared/analysis-room/reducer";
import { RichText } from "./RichText";
import { ReportReview } from "./ReportReview";
import "./pharma.css";

type App = {
  app_id: string;
  category: string;
  name: string;
  business_question: string;
};
type Evidence = {
  id: string;
  title: string;
  source_url?: string;
  version: string;
  applicable_region: string;
  kind: string;
};
type Context = {
  workspace_id: number;
  context_revision: string;
  apps: App[];
  entities: { entity_id: string; name: string }[];
  periods: string[];
  knowledge: Evidence[];
  limitations: string[];
  resources: { key: string; kind: string; status: string }[];
};
type Analysis = {
  metrics: Record<
    string,
    { label: string; value: string | null; unit: string }
  >;
  tables: { title: string; rows: Record<string, unknown>[] }[];
  warnings: string[];
  evidence: Evidence[];
};
type Run = {
  id: string;
  app_id: string;
  status: string;
  error?: string;
  created_at: string;
  result?: { artifact_id: number; title: string; analysis: Analysis };
};
const labels: Record<string, string> = {
  entity_id: "主体",
  period: "期间",
  product_id: "药品",
  revenue: "收入",
  cost: "成本",
  expense: "费用",
  net_profit: "净利润",
  budget_revenue: "预算收入",
  budget_cost: "预算成本",
  budget_expense: "预算费用",
  budget_version: "预算版本",
  opening_cash: "期初资金",
  closing_cash: "期末资金",
  operating_cash: "经营现金流",
  investing_cash: "投资现金流",
  financing_cash: "融资现金流",
  internal_revenue: "内部收入",
  internal_cost: "内部成本",
  quantity: "数量",
  channel: "渠道",
  customer: "客户",
  gross_profit: "毛利",
  price_effect: "价格影响",
  volume_effect: "数量影响",
  scope_effect: "范围变化",
  as_of: "快照日期",
  due_date: "到期日",
  invoice_amount: "发票金额",
  received: "已核销收款",
  outstanding: "未结余额",
  settlement: "结算方式",
  week: "周次",
  baseline: "基准资金",
  delayed: "延迟资金",
  batch: "批次",
  unit_cost: "单位成本",
  value: "账面金额",
  expires_on: "效期",
  last_sale_on: "最近销售日",
  days_to_expiry: "剩余效期天数",
  days_idle: "未销售天数",
  agreed_quantity: "约定数量",
  delivered_quantity: "交付数量",
  contract_price: "合同价格",
  actual_price: "实际价格",
  actual_unit_cost: "实际单位成本",
  standard_unit_cost: "标准单位成本",
  kind: "类型",
  project: "项目",
  stage: "阶段",
  spend: "投入",
  budget: "预算",
  capitalized: "已登记资本化",
  evidence_complete: "证据完整",
  category: "类别",
  amount: "金额",
  rebate_base: "返利基数",
  rebate_rate: "返利率",
  rebate_accrued: "已计提返利",
  revenue_gap: "收入勾稽差额",
  cash_gap: "现金勾稽差额",
  ar_gap: "应收勾稽差额",
  id: "明细编号",
  region: "区域",
};
const path = (workspace: string) =>
  `/api/application-center/v1/workspaces/${workspace}/applications/pharma-finance`;

function AnalysisRoom({
  workspace,
  entity,
  period,
  question,
  consolidated,
}: {
  workspace: string;
  entity: string;
  period: string;
  question: string;
  consolidated: boolean;
}) {
  const [query, setQuery] = useState(question),
    [answer, setAnswer] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [interrupt, setInterrupt] = useState<Record<string, unknown>>(),
    [thread, setThread] = useState("");
  const abort = useRef<AbortController>();
  const runId = useRef("");
  const state = useRef(initialAnalysisState());
  useEffect(() => () => abort.current?.abort(), []);
  async function send(resume = false, accepted = false) {
    setError("");
    setBusy(true);
    const id = resume ? thread : crypto.randomUUID();
    setThread(id);
    if (!resume) {
      state.current = initialAnalysisState();
      setAnswer("");
    }
    setInterrupt(undefined);
    const controller = new AbortController();
    abort.current = controller;
    try {
      const started = await api<{ run_id: string }>(
        `${path(workspace)}/analysis`,
        {
          thread_id: id,
          workspace_id: Number(workspace),
          application_context: { application_id: "pharma-finance" },
          messages: resume ? [] : [{ role: "user", content: query }],
          ...(resume
            ? { interrupt_feedback: accepted ? "accepted" : query }
            : {}),
          locale: "zh-CN",
          enable_web_search: false,
          auto_accepted_plan: false,
          session_outcome_goals: ["data_analysis"],
          analysis_scope: {
            period_start: period,
            period_end: period,
            entities: entity === "all" ? [] : [entity],
            currency: "CNY",
            consolidation_mode:
              entity === "all"
                ? consolidated
                  ? "consolidated"
                  : "aggregate"
                : "single_entity",
          },
        }
      );
      runId.current = started.run_id;
      while (!controller.signal.aborted) {
        const current = await api<{
          status: string;
          snapshot?: Record<string, unknown>;
        }>(`${path(workspace)}/analysis/${started.run_id}`);
        if (controller.signal.aborted) break;
        if (current.snapshot) {
          state.current = analysisReducer(state.current, {
            event: "stream_snapshot",
            data: current.snapshot,
          });
          setAnswer(Object.values(state.current.messages).join("\n\n"));
          setInterrupt(state.current.interrupt);
        }
        if (current.status !== "running") {
          if (["failed", "abandoned"].includes(current.status))
            setError("分析已中断，请检查服务或重新运行。");
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  async function stop() {
    abort.current?.abort();
    setBusy(false);
    if (runId.current)
      try {
        await api(`${path(workspace)}/analysis/${runId.current}/cancel`, {});
      } catch (e) {
        setError((e as Error).message);
      }
  }
  return (
    <section className="ph-panel">
      <h2>医药问数分析室</h2>
      <p>
        使用当前空间已绑定资源。所有业务数据均为模拟；遇到口径不清时先确认。
      </p>
      <textarea
        aria-label="医药分析问题"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="例如：哪些医院应收已逾期，金额最大的客户有哪些？"
      />
      <button
        disabled={busy || !query.trim()}
        onClick={() => void send(!!interrupt)}
      >
        {interrupt ? "补充口径并继续" : "开始分析"}
      </button>
      {interrupt && (
        <button disabled={busy} onClick={() => void send(true, true)}>
          确认并继续
        </button>
      )}
      {busy && <button onClick={() => void stop()}>取消分析</button>}
      {error && <p role="alert">{error}</p>}
      {interrupt && (
        <p>
          需要补充口径：
          {String(
            interrupt.message ||
              interrupt.content ||
              interrupt.reason ||
              "请明确主体、期间和比较口径后继续。"
          )}
        </p>
      )}
      <RichText>
        {answer || (busy ? "正在查询已授权资源…" : "分析结果将在这里展示。")}
      </RichText>
    </section>
  );
}

function EvidenceChart({ analysis }: { analysis: Analysis }) {
  const table = analysis.tables.find(
    (t) =>
      t.rows.length > 0 &&
      ["revenue", "影响", "baseline", "余额", "value", "spend"].some(
        (k) => k in t.rows[0]
      )
  );
  if (!table) return null;
  const field = ["revenue", "影响", "baseline", "余额", "value", "spend"].find(
    (k) => k in table.rows[0]
  )!;
  const rows = table.rows.slice(0, 12),
    max = Math.max(1, ...rows.map((r) => Math.abs(Number(r[field]))));
  return (
    <figure aria-label={`${table.title}金额比较`}>
      <figcaption>{table.title} · 金额比较（元，最多12项）</figcaption>
      {rows.map((r, i) => (
        <div className="ph-bar" key={i}>
          <span>
            {String(
              r.product_id ||
                r.entity_id ||
                r.因素 ||
                r.账龄 ||
                r.project ||
                r.week ||
                i + 1
            )}
          </span>
          <i
            style={{
              width: `${Math.max(1, (Math.abs(Number(r[field])) / max) * 65)}%`,
              background: Number(r[field]) < 0 ? "#b66e4d" : "#16796b",
            }}
          />
          <strong>
            {Number(r[field]).toLocaleString("zh-CN", {
              maximumFractionDigits: 2,
            })}
          </strong>
        </div>
      ))}
    </figure>
  );
}

function Workspace({ workspace }: { workspace: string }) {
  const [context, setContext] = useState<Context>(),
    [error, setError] = useState(""),
    [entity, setEntity] = useState("all"),
    [period, setPeriod] = useState("");
  const [page, setPage] = useState("场景中心"),
    [app, setApp] = useState<App>(),
    [analysis, setAnalysis] = useState<Analysis>(),
    [runs, setRuns] = useState<Run[]>([]),
    [busy, setBusy] = useState(false),
    [preview, setPreview] = useState(""),
    [selectedRun, setSelectedRun] = useState<Run>(),
    [reviewPayload, setReviewPayload] = useState<Record<string, unknown>>({}),
    [question, setQuestion] = useState("");
  const generation = useRef(0);
  const key = useRef<{ params: string; id: string }>();
  useEffect(() => {
    let live = true;
    api<Context>(`${path(workspace)}/context`)
      .then((c) => {
        if (live) {
          setContext(c);
          setPeriod(c.periods.at(-1) || "");
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
      generation.current++;
    };
  }, [workspace]);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const r = await api<{ items: Run[] }>(`${path(workspace)}/runs`);
        if (live) setRuns(r.items);
      } catch (e) {
        if (live) setError((e as Error).message);
      }
      if (live) timer = setTimeout(poll, 4000);
    }
    void poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [workspace]);
  async function execute(report = false) {
    if (!context || !app || busy) return;
    const g = ++generation.current;
    setBusy(true);
    setError("");
    setAnalysis(undefined);
    setPreview("");
    setSelectedRun(undefined);
    const body = { entity, period, context_revision: context.context_revision };
    const params = JSON.stringify({ app: app.app_id, ...body });
    if (key.current?.params !== params)
      key.current = { params, id: crypto.randomUUID() };
    try {
      if (report) {
        await api(`${path(workspace)}/apps/${app.app_id}/runs`, {
          ...body,
          idempotency_key: key.current.id,
        });
        if (g === generation.current) {
          key.current = undefined;
          setPage("分析记录");
        }
      } else {
        const result = await api<Analysis>(
          `${path(workspace)}/apps/${app.app_id}/calculation`,
          body
        );
        if (g === generation.current) setAnalysis(result);
      }
    } catch (e) {
      if (g === generation.current) setError((e as Error).message);
    } finally {
      if (g === generation.current) setBusy(false);
    }
  }
  async function show(run: Run) {
    const g = ++generation.current;
    setPreview("");
    setSelectedRun(undefined);
    try {
      const r = await api<{ document_html: string }>(
        `${path(workspace)}/runs/${run.id}/document`
      );
      const payload = await api<Record<string, unknown>>(
        `${path(workspace)}/runs/${run.id}/review-state`
      );
      if (g === generation.current) {
        setPreview(r.document_html);
        setSelectedRun(run);
        setReviewPayload(payload);
      }
    } catch (e) {
      if (g === generation.current) setError((e as Error).message);
    }
  }
  function changeScope() {
    generation.current++;
    setAnalysis(undefined);
    setPreview("");
    setSelectedRun(undefined);
    setBusy(false);
  }
  if (!context)
    return (
      <section className="ph-panel">
        <p role={error ? "alert" : "status"}>
          {error || "正在核验空间资源与数据口径…"}
        </p>
        <p>此空间需要先安装医药应用并绑定数据与知识库。</p>
      </section>
    );
  return (
    <>
      <nav>
        {["场景中心", "问数分析室", "分析记录", "知识依据", "资源状态"].map(
          (p) => (
            <button
              className={page === p ? "active" : ""}
              key={p}
              onClick={() => {
                setPage(p);
                setPreview("");
                setSelectedRun(undefined);
              }}
            >
              {p}
            </button>
          )
        )}
      </nav>
      <div className="ph-scope">
        <label>
          主体{" "}
          <select
            value={entity}
            onChange={(e) => {
              changeScope();
              setEntity(e.target.value);
            }}
          >
            <option value="all">
              {context.entities.some((e) => e.entity_id === "MFG") &&
              context.entities.some((e) => e.entity_id === "DIST")
                ? "集团合并（模拟抵销口径）"
                : "范围内主体汇总（不抵销）"}
            </option>
            {context.entities.map((e) => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          会计期间{" "}
          <select
            value={period}
            onChange={(e) => {
              changeScope();
              setPeriod(e.target.value);
            }}
          >
            {context.periods.map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <span>人民币 · 收入不含税 · 应收含税</span>
      </div>
      {error && (
        <p role="alert" className="ph-error">
          {error}
        </p>
      )}
      {page === "场景中心" && (
        <>
          <div className="ph-heading">
            <small>PHARMACEUTICAL FINANCE</small>
            <h1>看清经营变化，追溯每一项财务判断</h1>
            <p>
              从产品、集采到回款与研发，让集团财务分析有数据、有口径、有证据。
            </p>
          </div>
          <div className="ph-grid">
            {context.apps.map((a) => (
              <article
                key={a.app_id}
                className={app?.app_id === a.app_id ? "chosen" : ""}
              >
                <small>{a.category}</small>
                <h2>{a.name}</h2>
                <p>{a.business_question}</p>
                <button
                  onClick={() => {
                    changeScope();
                    setApp(a);
                  }}
                >
                  选择分析
                </button>
                <button
                  className="secondary"
                  onClick={() => {
                    setQuestion(a.business_question);
                    setPage("问数分析室");
                  }}
                >
                  追问
                </button>
              </article>
            ))}
          </div>
          {app && (
            <section className="ph-panel">
              <h2>{app.name}</h2>
              <button disabled={busy} onClick={() => void execute()}>
                计算与查看明细
              </button>{" "}
              <button disabled={busy} onClick={() => void execute(true)}>
                生成冻结报告
              </button>
              {busy && <p role="status">正在执行…</p>}
              {analysis && (
                <>
                  <div className="ph-metrics">
                    {Object.entries(analysis.metrics).map(([k, m]) => (
                      <div key={k}>
                        <small>{m.label}</small>
                        <strong>
                          {m.value === null
                            ? "不适用"
                            : Number(m.value).toLocaleString("zh-CN", {
                                maximumFractionDigits: 2,
                              })}
                          <em>{m.unit}</em>
                        </strong>
                      </div>
                    ))}
                  </div>
                  <EvidenceChart analysis={analysis} />
                  {analysis.tables.map((t, i) => (
                    <details key={i} open>
                      <summary>
                        {t.title} · {t.rows.length}条
                      </summary>
                      <div className="ph-table">
                        <table>
                          <thead>
                            <tr>
                              {Object.keys(t.rows[0] || {}).map((k) => (
                                <th key={k}>{labels[k] || k}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {t.rows.map((r, j) => (
                              <tr key={j}>
                                {Object.entries(r).map(([k, v]) => (
                                  <td key={k}>{String(v ?? "")}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  ))}
                  {analysis.warnings.map((w) => (
                    <p key={w} className="ph-note">
                      {w}
                    </p>
                  ))}
                  <h3>方法依据</h3>
                  {analysis.evidence.map((e) => (
                    <p key={e.id}>
                      {e.title} · v{e.version}
                    </p>
                  ))}
                </>
              )}
            </section>
          )}
        </>
      )}
      {page === "问数分析室" && (
        <AnalysisRoom
          key={`${workspace}:${entity}:${period}`}
          workspace={workspace}
          entity={entity}
          period={period}
          question={question}
          consolidated={
            context.entities.some((e) => e.entity_id === "MFG") &&
            context.entities.some((e) => e.entity_id === "DIST")
          }
        />
      )}
      {page === "分析记录" && (
        <section className="ph-panel">
          <h2>后台运行与冻结成果</h2>
          {!runs.length && <p>暂无运行记录。从场景中心生成第一份报告。</p>}
          {runs.map((r) => (
            <div className="ph-run" key={r.id}>
              <span>
                {r.result?.title ||
                  context.apps.find((a) => a.app_id === r.app_id)?.name}{" "}
                ·{" "}
                {(
                  {
                    queued: "排队中",
                    running: "执行中",
                    completed: "已生成 · 待复核",
                    failed: "失败",
                  } as Record<string, string>
                )[r.status] || r.status}
              </span>
              {r.status === "completed" && (
                <button onClick={() => void show(r)}>查看报告</button>
              )}
              {r.error && <p role="alert">{r.error}</p>}
            </div>
          ))}
        </section>
      )}
      {preview && (
        <>
          <iframe title="医药冻结报告" sandbox="" srcDoc={preview} />
          {selectedRun?.result && (
            <ReportReview
              id={selectedRun.result.artifact_id}
              workspace={workspace}
              payload={reviewPayload}
              endpoint={`${path(workspace)}/runs/${selectedRun.id}`}
              onChange={async () => {
                await show(selectedRun);
              }}
            />
          )}
        </>
      )}
      {page === "知识依据" && (
        <section className="ph-grid">
          {context.knowledge.map((k) => (
            <article key={k.id}>
              <small>
                {k.kind === "public"
                  ? "公开资料"
                  : k.kind === "demo_policy"
                  ? "模拟企业制度"
                  : "分析方法"}
              </small>
              <h3>{k.title}</h3>
              <p>
                {k.applicable_region} · v{k.version}
              </p>
              {k.source_url && (
                <a href={k.source_url} target="_blank" rel="noreferrer">
                  查看原始来源 ↗
                </a>
              )}
            </article>
          ))}
        </section>
      )}
      {page === "资源状态" && (
        <section className="ph-panel">
          <h2>当前应用已绑定资源</h2>
          {context.resources.map((r) => (
            <p key={r.key}>
              {r.key} · {r.kind} · {r.status}
            </p>
          ))}
          {context.limitations.map((l) => (
            <p className="ph-note" key={l}>
              {l}
            </p>
          ))}
        </section>
      )}
    </>
  );
}

export function PharmaCenter() {
  const [token, setToken] = useState(platformToken()),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [spaces, setSpaces] = useState<{ id: number; name: string }[]>([]),
    [workspace, setWorkspace] = useState("");
  useEffect(() => {
    const changed = () => {
      setToken(platformToken());
      setSpaces([]);
      setWorkspace("");
    };
    window.addEventListener("finance-platform-auth", changed);
    return () => window.removeEventListener("finance-platform-auth", changed);
  }, []);
  useEffect(() => {
    let live = true;
    if (token)
      api<{ workspaces: { id: number; name: string }[] }>(
        "/api/application-center/v1/apps/pharma/workspaces"
      )
        .then((r) => {
          if (live) {
            setSpaces(r.workspaces);
            setWorkspace(
              String(
                r.workspaces.find((s) => s.name.includes("医药集团"))?.id ||
                  r.workspaces[0]?.id ||
                  ""
              )
            );
          }
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    return () => {
      live = false;
    };
  }, [token]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api<{ token: string }>("/api/user/login", {
        login_identifier: username,
        password,
        login_type: "username",
      });
      if (!r.token) throw new Error("登录响应缺少认证信息");
      setPassword("");
      setPlatformToken(r.token);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="pharma">
      <header>
        <a className="ph-brand" href="/pharma-finance/">
          ✚ <strong>医药财务分析中心</strong>
        </a>
        <span className="ph-badge">模拟集团 · 演示环境</span>
        {token && (
          <>
            <select
              aria-label="问数空间"
              value={workspace}
              onChange={(e) => setWorkspace(e.target.value)}
            >
              {spaces.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            <button className="secondary" onClick={() => setPlatformToken("")}>
              退出
            </button>
          </>
        )}
      </header>
      {error && <p role="alert">{error}</p>}
      {!token ? (
        <section className="ph-login">
          <small>PHARMA FINANCE WORKSPACE</small>
          <h1>
            连接业务与财务，
            <br />
            让经营判断有据可循。
          </h1>
          <p>六大专题 · 十二个分析应用 · 全链路成果复核</p>
          <form onSubmit={login}>
            <h2>登录分析平台</h2>
            <label>
              账号
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label>
              密码
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <button disabled={busy}>
              {busy ? "正在登录…" : "进入工作空间"}
            </button>
          </form>
        </section>
      ) : workspace ? (
        <Workspace
          key={`${token.slice(-12)}:${workspace}`}
          workspace={workspace}
        />
      ) : (
        <p>当前账号暂无授权空间。</p>
      )}
      <footer>
        医药财务分析中心 · 数据与制度均明确标注来源 · 分析结果须经人工复核
      </footer>
    </main>
  );
}
