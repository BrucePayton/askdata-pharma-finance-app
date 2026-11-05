import { useState } from "react";
import { platformRequest as api } from "./platform";

type ChapterReview = { id: string; title: string; status: string; decision: string; note: string };

export function ReportReview({ id, workspace, payload, onChange, endpoint }: {
  id: number | string; workspace: string; payload: Record<string, unknown>; onChange: () => Promise<void>; endpoint?: string;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [document, setDocument] = useState("");
  const [chapters, setChapters] = useState<ChapterReview[]>([]);
  const chapterIncomplete = chapters.some(c => !c.note.trim() || !c.decision || c.decision === "request_revision");
  const state = String(payload.review_status || "draft");
  async function act(action: string) {
    setBusy(true); setError("");
    try {
      if (action === "preview") {
        const result = await api<{ document_html: string; chapters?: { id: string; title: string; status: string }[] }>(`${endpoint || `/api/askdata/production-artifacts/${id}`}/review-document?workspace_id=${workspace}`);
        setDocument(result.document_html);
        setChapters((result.chapters || []).map(c => ({ ...c, decision: "", note: "" })));
      } else {
        if ((action === "publish" || action === "return") && !note.trim()) {
          setError("请先填写总体复核意见。");
          return;
        }
        if (action === "publish" && !document) {
          const result = await api<{ document_html: string; chapters?: { id: string; title: string; status: string }[] }>(`${endpoint || `/api/askdata/production-artifacts/${id}`}/review-document?workspace_id=${workspace}`);
          setDocument(result.document_html);
          setChapters((result.chapters || []).map(c => ({ ...c, decision: "", note: "" })));
          setError("已加载冻结正文，请逐章确认后再次点击“复核并发布”。");
          return;
        }
        if (action === "publish" && chapterIncomplete) {
          setError("请为每个冻结章节选择“通过”或“接受限制”，并填写章节复核依据。");
          return;
        }
        if (action === "revision") await api(`${endpoint || `/api/askdata/production-artifacts/${id}`}/revision?workspace_id=${workspace}`, {});
        else await api(`${endpoint || `/api/askdata/production-artifacts/${id}`}/review`, {
          workspace_id: Number(workspace), action, note,
          expected_revision: Number(payload.review_revision || 0),
          chapter_reviews: chapters.filter(c => action === 'publish' || (c.decision && c.note.trim())).map(c => ({ chapter_id: c.id, decision: c.decision, note: c.note })),
        });
        setDocument(""); setChapters([]); setNote(""); await onChange();
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <section aria-label={`报告 ${id} 复核`}>
    <p>复核状态：{({ draft: "草稿", pending_review: "待复核", published: "已发布" } as Record<string, string>)[state] || state}</p>
    {error && <p role="alert">{error}</p>}
    {state === "pending_review" && <label>复核意见<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={4000} /></label>}
    {state === "pending_review" && <p>财务报告请先“查看冻结正文”，按冻结版本逐章记录意见；未查看或未确认的章节不能发布。</p>}
    {state === "pending_review" && <div role="status" className="review-readiness"><strong>发布条件</strong><span>{document ? "✓" : "○"} 已加载冻结正文</span><span>{note.trim() ? "✓" : "○"} 已填写总体复核意见</span><span>{document && !chapterIncomplete ? "✓" : "○"} 已完成全部章节复核</span><small>发布操作需要平台管理员权限。</small></div>}
    {state === "pending_review" && chapters.length > 0 && <fieldset><legend>冻结版本逐章复核</legend>{chapters.map(chapter => <div key={chapter.id}>
      <label>{chapter.title}<select aria-label={`${chapter.title}复核决定`} value={chapter.decision} onChange={e => setChapters(items => items.map(c => c.id === chapter.id ? { ...c, decision: e.target.value } : c))}>
        <option value="">请选择复核决定</option>
        {chapter.status === "ready" && <option value="approve">通过</option>}
        <option value="accept_limitations">确认并接受已披露限制</option><option value="request_revision">需要修订</option>
      </select></label>
      <textarea aria-label={`${chapter.title}章节意见`} placeholder="逐章记录复核依据，不能代替专业人员签署" maxLength={2000} value={chapter.note} onChange={e => setChapters(items => items.map(c => c.id === chapter.id ? { ...c, note: e.target.value } : c))} />
    </div>)}</fieldset>}
    <div className="platform-toolbar">
      {state === "draft" && <button disabled={busy} onClick={() => void act("submit")}>提交复核</button>}
      {state === "pending_review" && <><button disabled={busy} onClick={() => void act("publish")}>复核并发布</button><button disabled={busy} onClick={() => void act("return")}>退回修订</button></>}
      {state === "published" && <button disabled={busy} onClick={() => void act("revision")}>创建修订版本</button>}
      {payload.review_snapshot_hash ? <button disabled={busy} onClick={() => void act("preview")}>查看冻结正文</button> : null}
    </div>
    {document && <iframe title={`报告 ${id} 冻结正文`} sandbox="" srcDoc={document} style={{ width: "100%", height: 640, border: 0 }} />}
    {Array.isArray(payload.review_history) && <details><summary>复核记录</summary>{payload.review_history.map((raw, i) => {
      const event = raw as Record<string, string>;
      const chapterNotes = (raw as { chapter_reviews?: { chapter_id: string; decision: string; note: string }[] }).chapter_reviews || [];
      return <div key={i}><p>{event.at} · {event.user_id} · {({ submit: "提交复核", publish: "发布", return: "退回" } as Record<string, string>)[event.action]}：{event.note}</p>
        {chapterNotes.length > 0 && <ul>{chapterNotes.map(c => <li key={c.chapter_id}>{c.chapter_id} · {({ approve: "通过", accept_limitations: "接受限制", request_revision: "需修订" } as Record<string, string>)[c.decision]}：{c.note}</li>)}</ul>}</div>;
    })}</details>}
  </section>;
}
