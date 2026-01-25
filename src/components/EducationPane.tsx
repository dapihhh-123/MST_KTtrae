import { useMemo, useState } from "react";

export default function EducationPane(props: {
  diagnosis: { data: any; traceId?: string } | null;
  intervention: { data: any; traceId?: string } | null;
  onSubmitUnlock: (payload: { answer: string; correct: boolean; thread_id?: string; trace_id?: string }) => void;
  onSubmitRecap: (payload: { response: string; thread_id?: string; trace_id?: string }) => void;
}) {
  const [unlockAnswer, setUnlockAnswer] = useState("");
  const [recapText, setRecapText] = useState("");

  const diag = props.diagnosis?.data;
  const plan = props.intervention?.data;

  const unlockRequired = !!plan?.unlock_required;
  const unlockQuestion = plan?.unlock_question || "";
  const isDebtRecap = !!plan?.is_debt_recap;

  const traceId = props.intervention?.traceId || props.diagnosis?.traceId;
  const threadId = diag?.thread_id || diag?.threadId;

  const leaf = useMemo(() => {
    const level = plan?.leaf_level;
    const fading = plan?.fading_direction;
    if (level === undefined && fading === undefined) return null;
    return { level, fading };
  }, [plan]);

  return (
    <div className="educationPane">
      <div className="educationHeader">EDUCATION GUIDE</div>

      {leaf && (
        <div className="educationRow">
          <div className="pill">LEAF {leaf.level ?? "-"}</div>
          <div className="pill ghost">{leaf.fading ?? "-"}</div>
          {traceId && <div className="pill ghost">trace {traceId}</div>}
        </div>
      )}

      {diag && (
        <div className="educationCard">
          <div className="educationTitle">Diagnosis</div>
          {diag.label && <div className="educationLine"><b>label</b>: {String(diag.label)}</div>}
          {diag.evidence && <div className="educationLine"><b>evidence</b>: {String(diag.evidence)}</div>}
          {diag.recommendations && <div className="educationLine"><b>recommend</b>: {String(diag.recommendations)}</div>}
        </div>
      )}

      {unlockRequired && (
        <div className="educationCard">
          <div className="educationTitle">理解解锁</div>
          <div className="educationLine">{unlockQuestion || "请用一句话解释你将如何修改代码。"} </div>
          <textarea
            className="educationTextarea"
            value={unlockAnswer}
            onChange={(e) => setUnlockAnswer(e.target.value)}
            placeholder="你的回答..."
          />
          <div className="educationActions">
            <button
              className="btn"
              onClick={() => {
                props.onSubmitUnlock({ answer: unlockAnswer, correct: false, thread_id: threadId, trace_id: traceId });
                setUnlockAnswer("");
              }}
            >
              未通过
            </button>
            <button
              className="btn primary"
              onClick={() => {
                props.onSubmitUnlock({ answer: unlockAnswer, correct: true, thread_id: threadId, trace_id: traceId });
                setUnlockAnswer("");
              }}
            >
              通过
            </button>
          </div>
        </div>
      )}

      {isDebtRecap && (
        <div className="educationCard">
          <div className="educationTitle">学习债务复盘</div>
          <textarea
            className="educationTextarea"
            value={recapText}
            onChange={(e) => setRecapText(e.target.value)}
            placeholder="用一句话复盘你学到了什么..."
          />
          <div className="educationActions">
            <button
              className="btn primary"
              onClick={() => {
                props.onSubmitRecap({ response: recapText, thread_id: threadId, trace_id: traceId });
                setRecapText("");
              }}
            >
              提交复盘
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

