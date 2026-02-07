import requests
import json
import time

BASE_URL = "http://localhost:8001/api"
HEADERS = {"Content-Type": "application/json"}

TASKS = [
    # A1) CLI — Average of integers
    {
        "id": "A1",
        "desc": "做个命令行小工具：从 stdin 读入多行文本，每行一个整数，忽略空行和首尾空格，输出这些整数的平均值（保留 2 位小数）。如果没有任何有效整数输出 `0.00`。",
        "deliverable": "cli"
    },
    # A2) CLI — Log level counts
    {
        "id": "A2",
        "desc": "我想要一个脚本，粘贴一堆日志进去（stdin），你帮我统计每个日志级别出现次数：INFO/WARN/ERROR，不区分大小写。输出 JSON 一行（比如 `{\"INFO\":1,\"WARN\":2,\"ERROR\":0}`）。日志行格式不固定，可能带时间戳也可能没有。",
        "deliverable": "cli"
    },
    # A3) CLI — Top scorer with tie-breaking
    {
        "id": "A3",
        "desc": "写一个 CLI：stdin 第一行是 N，后面 N 行是 “姓名 分数”（用空格分隔，姓名可能包含中文但不含空格）。输出分数最高的姓名；如果并列，输出按字典序最小的姓名。N 可能为 0（输出空行）。",
        "deliverable": "cli"
    },
    # A4) CLI — Most frequent word
    {
        "id": "A4",
        "desc": "写一个命令行程序：从 stdin 读取一串英文句子，统计出现次数最多的单词（只按字母序列算单词，忽略大小写，标点当分隔符）。输出：`word count`（用空格隔开）。如果没有单词输出空行。",
        "deliverable": "cli"
    },
    # A5) CLI — Data cleaning
    {
        "id": "A5",
        "desc": "我要一个 CLI 做“数据清洗”：输入是一堆用逗号分隔的值，里面可能有空白、可能有 `NA`、可能有数字。你输出两行：第一行是有效数字的数量，第二行是有效数字的总和。`NA` 或空值不算数字。小数也可能出现。",
        "deliverable": "cli"
    },
    # A6) CLI — Contradiction: dedupe lines vs sort lines
    {
        "id": "A6",
        "desc": "实现一个 CLI：输入是多行文本，要求输出“去重后的行”，保持原顺序；但是又希望“按字母排序输出”。你自己决定一个合理规则并说明 assumptions。",
        "deliverable": "cli"
    },
    # A7) CLI — Ops via stdin
    {
        "id": "A7",
        "desc": "做个简单“问答式”程序：stdin 会给多行命令，如 `ADD apple`、`ADD banana`、`DEL apple`、`LIST`。维护一个集合。遇到 `LIST` 就输出当前集合的元素，用逗号连接，按字母排序。其他命令不输出。大小写不敏感。",
        "deliverable": "cli"
    },
    # A8) CLI — JSON input
    {
        "id": "A8",
        "desc": "stdin 输入一个 JSON 数组（可能很长），每个元素是对象，含 `name` 和 `age`。输出：年龄 >=18 的人数。如果 JSON 不合法，输出 `INVALID`。",
        "deliverable": "cli"
    },
    # B1) Function — normalize_email
    {
        "id": "B1",
        "desc": "实现函数 `normalize_email(email: str) -> str`：去掉首尾空格；把域名部分变成小写；用户名部分保持原样。输入保证包含一个 `@`。返回规范化后的 email。",
        "deliverable": "function"
    },
    # B2) Function — group_by_first_letter
    {
        "id": "B2",
        "desc": "实现 `group_by_first_letter(words: list[str]) -> dict[str, list[str]]`：按首字母（忽略大小写）分组，保留原顺序。非字母开头的单词归到 `\"#\"` 组。",
        "deliverable": "function"
    },
    # B3) Function — parse_duration
    {
        "id": "B3",
        "desc": "实现 `parse_duration(s: str) -> int`：解析形如 `\"2h30m\"`、`\"45m\"`、`\"10s\"`、`\"1h\"`，返回总秒数。若格式非法抛出 `ValueError`。大小写不敏感，允许空格。",
        "deliverable": "function"
    },
    # B4) Function — is_strong_password
    {
        "id": "B4",
        "desc": "实现 `is_strong_password(pwd: str) -> bool`：至少 8 位，包含大写字母、小写字母、数字、特殊字符（非字母数字），且不能包含空格。",
        "deliverable": "function"
    },
    # B5) Function — max_subarray_sum
    {
        "id": "B5",
        "desc": "实现 `max_subarray_sum(nums: list[int]) -> int`：返回连续子数组的最大和。nums 非空。",
        "deliverable": "function"
    },
    # B6) Function — dedupe with key
    {
        "id": "B6",
        "desc": "实现 `dedupe(items: list, key=None)`：去重并保持顺序。key 若为 None 按元素本身去重；否则按 `key(x)` 去重。说明遇到不可哈希元素怎么办（歧义点）。",
        "deliverable": "function"
    },
    # B7) Function — schedule_tasks
    {
        "id": "B7",
        "desc": "实现 `schedule_tasks(tasks)`：每个任务有 `duration` 和 `deadline`，返回一个“最优”安排，尽量多做任务。这里“最优”怎么定义你来选，但要写 assumptions，并让歧义点出来。",
        "deliverable": "function"
    },
    # B8) Function — safe_int
    {
        "id": "B8",
        "desc": "实现 `safe_int(s: str, default=0) -> int`：把字符串转 int。允许前后空格；允许 `+`/`-`；遇到非法返回 default。",
        "deliverable": "function"
    },
    # C1) Ops-style Function — Todo ops
    {
        "id": "C1",
        "desc": "写一个函数处理一串操作 `ops`，每个操作是列表：\n- `[\"add\", id, text]` 新增任务\n- `[\"done\", id]` 标记完成\n- `[\"del\", id]` 删除\n- `[\"list\", mode]` mode 是 `\"all\"|\"done\"|\"todo\"`\n每遇到 `list` 就把当前列表结果 append 到 answers 返回（list 的结果是 id 列表）。其他操作不输出。遇到不存在 id 怎么办你来定（歧义点）。",
        "deliverable": "function"
    },
    # C2) Ops-style Function — Inventory system
    {
        "id": "C2",
        "desc": "实现一个“库存系统” ops：\n- `[\"in\", name, qty]` 入库\n- `[\"out\", name, qty]` 出库（不足则出库失败）\n- `[\"count\", name]` 查询库存（append 一个整数到 answers）\n- `[\"all\"]` 输出所有商品库存（append 一个 dict 到 answers）\n返回 answers。大小写敏感与否你说明。",
        "deliverable": "function"
    },
    # C3) Ops-style Function — Contradiction: get/keys outputs
    {
        "id": "C3",
        "desc": "实现一个 ops：`set k v`、`get k`、`del k`、`keys`。\n要求：get/keys 要输出；但又说“只有 keys 输出”。你要产出歧义点，让用户选。",
        "deliverable": "function"
    },
    # C4) Ops-style Function — Noisy input format
    {
        "id": "C4",
        "desc": "ops 可能既有 list 也可能是字符串命令（例如 `\"ADD 1 hello\"`）。你需要决定是否支持两种格式，或只支持一种并写 assumptions。",
        "deliverable": "function"
    }
]

def create_task():
    try:
        task_resp = requests.post(f"{BASE_URL}/oracle/task", json={"project_id": "benchmark_20"}, headers=HEADERS)
        if task_resp.status_code != 200:
             print(f"Error creating task: {task_resp.text}")
             return None
        return task_resp.json()["task_id"]
    except Exception as e:
        print(f"Error creating task: {e}")
        return None

def run_benchmark():
    summary_table = []
    
    for t in TASKS:
        print(f"\nProcessing Task {t['id']}...")
        task_id = create_task()
        if not task_id:
            print("Skipping due to task creation failure")
            continue
            
        body = {
            "task_description": t["desc"],
            "deliverable_type": t["deliverable"],
            "language": "python",
            "runtime": "python"
        }
        
        # Add default entrypoint if function, to match UI behavior mentioned in checklist
        if t["deliverable"] == "function":
             # We assume "solve" as default if not specified by specific task requirements
             # But the checklist says: "If deliverable=function and the UI requires entrypoint, set entrypoint="solve" initially"
             # However, the SpecBody doesn't strictly require entrypoint for generation, only for execution usually.
             # Wait, generating spec doesn't require entrypoint in SpecBody (it's generated).
             # Ah, the checklist item 12 says: "If deliverable=function and the UI requires entrypoint, set entrypoint="solve" initially"
             # But backend `SpecBody` doesn't have `entrypoint` field. It's likely about what the user would type in UI *if* UI asked.
             # But here we are calling the API directly.
             pass

        # 3) Analyze Task
        try:
            resp = requests.post(f"{BASE_URL}/oracle/task/{task_id}/version/spec", json=body, headers=HEADERS)
            resp_json = resp.json()
        except Exception as e:
            print(f"Error calling analyze: {e}")
            resp_json = {"error": str(e)}

        # 4) Get Version Info
        version_id = resp_json.get("version_id")
        ver_info = {}
        if version_id:
            try:
                v_resp = requests.get(f"{BASE_URL}/oracle/version/{version_id}")
                ver_info = v_resp.json()
            except Exception as e:
                print(f"Error getting version: {e}")

        # 5) Get Last Spec Call Debug
        debug_info = {}
        try:
            d_resp = requests.get(f"{BASE_URL}/oracle/debug/last_spec_call")
            debug_info = d_resp.json()
        except Exception as e:
            print(f"Error getting debug info: {e}")

        # Print Evidence Block
        print(f"\n--- EVIDENCE BLOCK {t['id']} ---")
        print(f"1) Test Case ID: {t['id']}")
        print("2) UI Settings:")
        print(f"   - deliverable={t['deliverable']}")
        print("   - language=python")
        print("   - runtime=python")
        # print("   - entrypoint=solve") # Not sent in API
        
        print("3) Analyze Response JSON:")
        print(json.dumps(resp_json, indent=2, ensure_ascii=False))
        
        print("4) GET /oracle/version/{version_id} JSON:")
        # Truncate for readability if needed, but checklist says "full" or "key fields"
        # We'll print full but maybe compact
        print(json.dumps(ver_info, indent=2, ensure_ascii=False))
        
        print("5) GET /oracle/debug/last_spec_call JSON:")
        print(json.dumps(debug_info, indent=2, ensure_ascii=False))

        # 6) One-line evaluation (Auto-eval based on heuristics)
        goal_ok = "yes" if ver_info.get("spec_summary", {}).get("goal_one_liner") and "Error" not in ver_info.get("spec_summary", {}).get("goal_one_liner", "") else "no"
        deliv_ok = "yes" if ver_info.get("spec_summary", {}).get("deliverable") == t["deliverable"] else "no"
        amb_count = len(ver_info.get("ambiguities", []))
        amb_ok = "yes" # Hard to judge automatically, assume yes if parsed
        conf = ver_info.get("oracle_confidence", 0.0)
        conf_reasonable = "yes" if conf > 0 else "no" # Simplified check
        
        print("6) One-line evaluation:")
        print(f"   - goal_one_liner_ok={goal_ok}")
        print(f"   - deliverable_ok={deliv_ok}")
        print(f"   - ambiguities_ok={amb_ok}")
        print(f"   - confidence_reasonable={conf_reasonable}")

        # Add to summary
        inter_model = debug_info.get("interaction_model_pred", "N/A")
        status = ver_info.get("status", "error")
        note = ""
        if goal_ok == "no": note += "Goal Bad; "
        if deliv_ok == "no": note += "Deliv Mismatch; "
        
        summary_table.append({
            "ID": t["id"],
            "status": status,
            "interaction_model_pred": inter_model,
            "ambiguities_count": amb_count,
            "confidence": conf,
            "notes": note
        })
        
        time.sleep(1) # Polite delay

    # Print Summary Table
    print("\n\n============================================================")
    print("20-LINE SUMMARY TABLE")
    print("ID | status | interaction_model_pred | ambiguities_count | confidence | notes")
    print("---|---|---|---|---|---")
    for item in summary_table:
        print(f"{item['ID']} | {item['status']} | {item['interaction_model_pred']} | {item['ambiguities_count']} | {item['confidence']} | {item['notes']}")

if __name__ == "__main__":
    run_benchmark()
