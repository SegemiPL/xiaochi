"""Run eight synthetic cases against real DeepSeek through Xiaochi's HTTP API.

Run from the repository root: python -m src.evals.xiaochi_smoke.
Credentials come from the private .env; reports contain no headers or configuration.
These cases check product behavior and one policy regression against its official text.
They do not establish accuracy across tax policy or the full evaluation set.
"""

from __future__ import annotations

import os

os.environ.setdefault("QWEN_AGENT_MAX_LLM_CALL_PER_RUN", "12")

import json
import logging
import re
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from qwen_agent.log import logger

from src.agent.conversations import ConversationStore
from src.config.env import get_env
from src.config.product import DISCLAIMER
from src.web.app import create_app

REPORT_PATH = Path(__file__).resolve().parents[1] / "workspace/eval/xiaochi-smoke.json"


def main() -> int:
    key = get_env("DEEPSEEK_API_KEY", "")
    if not key:
        print("Configure DEEPSEEK_API_KEY in the repository .env before running live evaluation.")
        return 1
    logger.setLevel(logging.WARNING)
    report = []
    with tempfile.TemporaryDirectory(prefix="xiaochi-smoke-") as directory:
        root = Path(directory)
        store = ConversationStore(root / "conversations")
        app = create_app(store=store, upload_root=root / "uploads")
        with TestClient(app) as client:

            def run(case, question, *, conversation=None, uploads=None):
                conversation = conversation or client.post("/api/conversations").json()["id"]
                start = time.monotonic()
                request_id = str(uuid4())
                stages = []
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pending = pool.submit(
                        client.post,
                        f"/api/conversations/{conversation}/messages",
                        json={
                            "message": question,
                            "attachments": uploads or [],
                            "request_id": request_id,
                        },
                    )
                    while True:
                        try:
                            response = pending.result(timeout=0.25)
                            break
                        except TimeoutError:
                            progress = client.get(
                                f"/api/conversations/{conversation}/progress/{request_id}"
                            )
                            if progress.status_code == 200:
                                snapshot = progress.json()
                                if not stages or stages[-1]["stage"] != snapshot["stage"]:
                                    stages.append(
                                        {
                                            "stage": snapshot["stage"],
                                            "seconds": snapshot["elapsed_seconds"],
                                        }
                                    )
                answer = response.json().get("answer", "")
                body = answer.removesuffix(DISCLAIMER).strip()
                public = client.get(f"/api/conversations/{conversation}").json()["messages"]
                private = store.load(conversation)
                tools = [m.get("name") for m in private["messages"] if m.get("role") == "function"]
                checks = {
                    "http_ok": response.status_code == 200,
                    "footer_once": answer.count(DISCLAIMER) == 1,
                    "final_only": not any(
                        "function_call" in m or "reasoning_content" in m for m in public
                    ),
                    "no_key": key not in response.text,
                    "complete_answer": "暂时未能形成完整答复" not in answer,
                }
                if case in {
                    "identity",
                    "calculation",
                    "followup_rewrite",
                    "attachment",
                    "cross_border_clarification",
                }:
                    checks["no_unneeded_search"] = not tools
                if case in {"calculation", "followup_rewrite"}:
                    compact = body.replace(",", "").replace("，", "")
                    checks["amounts_preserved"] = "1000" in compact and "130" in compact
                if case == "followup_rewrite":
                    checks["history_continues"] = len(public) == 4
                    checks["short_rewrite"] = len(body) <= 100
                if case == "missing_facts":
                    checks["concise_clarification"] = len(body) <= 400
                    checks["no_unverified_rates"] = not re.search(r"(?:13|9|6|3|5)\s*%", body)
                    checks["asks_identity"] = "一般" in body and "小规模" in body
                if case == "attachment":
                    checks["reads_material"] = all(
                        part in body for part in ("A", "B", "9:00", "17:00")
                    )
                if case == "cross_border_clarification":
                    checks["concise_clarification"] = len(body) <= 300
                    checks["asks_key_facts"] = (
                        any(term in body for term in ("身份", "个人", "企业"))
                        and any(term in body for term in ("国家", "地区"))
                        and "资金" in body
                    )
                    checks["no_unasked_tax_analysis"] = not any(
                        term in body for term in ("租金", "出租", "资本利得", "持有税")
                    )
                if case in {"official_search", "policy_scope"}:
                    checks["search_used"] = "WebSearchTool" in tools
                    checks["official_link"] = bool(
                        re.search(
                            r"https?://[^\s]*(?:gov\.cn|chinatax\.gov\.cn|mof\.gov\.cn)", body
                        )
                    )
                    checks["shows_real_progress"] = any(
                        item["stage"] == "searching" for item in stages
                    )
                    evidence = []
                    for message in private["messages"]:
                        if (
                            message.get("role") == "function"
                            and message.get("name") == "WebSearchTool"
                        ):
                            try:
                                payload = json.loads(message.get("content", ""))
                            except (TypeError, ValueError):
                                continue
                            evidence.extend(
                                item.get("source_text", "") for item in payload.get("results", [])
                            )
                    if case == "policy_scope":
                        checks["official_body_retrieved"] = any(
                            "2026年第27号" in text and "20%" in text for text in evidence
                        )
                        checks["formal_document"] = (
                            "关于外籍个人股息红利个人所得税政策有关事项的公告" in body
                        )
                        checks["document_number"] = bool(
                            re.search(r"2026\s*年\s*第?\s*27\s*号", body)
                        )
                        checks["execution_date"] = "2026年9月1日" in body or "2026-09-01" in body
                        checks["tax_rate"] = bool(re.search(r"20\s*%", body))
                        checks["applicable_scope"] = "外籍个人" in body and "外商投资企业" in body
                        checks["old_exemption_repealed"] = "1994" in body and "废止" in body
                        checks["answers_instead_of_refusing"] = not any(
                            term in body
                            for term in ("未取得该政策", "请提供该文件", "不能确认执行日期")
                        )
                        checks["source_reading_progress"] = any(
                            item["stage"] == "reading" for item in stages
                        )
                    elif case == "official_search":
                        checks["concise_locator"] = len(body) <= 800
                item = {
                    "case": case,
                    "question": question,
                    "answer": answer,
                    "seconds": round(time.monotonic() - start, 2),
                    "checks": checks,
                    "passed": all(checks.values()),
                    "internal_tools": tools,
                    "stages": stages,
                }
                report.append(item)
                REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
                REPORT_PATH.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2).replace(key, "[REDACTED]"),
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            "case": case,
                            "passed": item["passed"],
                            "checks": checks,
                            "seconds": item["seconds"],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
                return conversation

            run("identity", "你好，请用不超过100字说明你能怎样辅助税务部门工作。")
            calculation = run(
                "calculation",
                "仅按我给定的税率13%、含税金额1130元，计算不含税金额和税额。只做算术，不检索、不判断税率是否适用。",
            )
            run(
                "followup_rewrite", "将刚才的结果压缩为一句话，保留金额。", conversation=calculation
            )
            run("missing_facts", "请帮我计算我们企业本月应缴的增值税。")
            run("cross_border_clarification", "中国居民可以在国外购入房产吗")
            conversation = client.post("/api/conversations").json()["id"]
            file = (
                "测试材料.txt",
                "这是界面测试材料，不是政策。申请人需要提供材料A和B，窗口工作时间为9:00至17:00。".encode(),
                "text/plain",
            )
            upload = client.post(
                f"/api/conversations/{conversation}/attachments", files={"file": file}
            ).json()
            run(
                "attachment",
                "仅依据我上传的测试材料，列出所需材料和窗口工作时间。不检索。",
                conversation=conversation,
                uploads=[upload["id"]],
            )
            run(
                "official_search",
                "请定位《财政部 税务总局关于增值税小规模纳税人减免增值税政策的公告》（2023年第19号）的官方链接。只有取得原文或引用摘录时才概括其中政策，未取得时明确说明。不要扩展其他政策。",
            )
            run(
                "policy_scope",
                "截至2026年9月6日，外籍个人从中国境内外商投资企业取得股息红利，适用的近期政策是什么？请给出正式文件和执行日期，并说明这里的适用对象。",
            )
    passed = sum(item["passed"] for item in report)
    print(f"{passed}/{len(report)} live smoke cases passed. Report: {REPORT_PATH}")
    return 0 if passed == len(report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
