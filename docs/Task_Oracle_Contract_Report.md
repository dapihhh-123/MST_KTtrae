# Task Oracle 后端接口与前端交互契约报告

## 1. 概述
本报告定义了 Task Oracle 模块的前后端交互规范。该模块旨在通过 LLM 自动分析用户需求，生成形式化的任务规格说明书（Spec）和测试用例（Tests），并提供代码评测能力。

## 2. 鉴权与基础约定
*   **鉴权方式**: 当前系统采用无状态/工作区鉴权。API 请求头无需特殊 Token，但建议在请求头中携带 `x-session-id` 以便日志追踪。
*   **数据格式**: `Content-Type: application/json`
*   **字符编码**: UTF-8
*   **环境依赖**: 后端需配置 `OPENAI_API_KEY`。

## 3. 核心 API 契约 (OpenAPI/Swagger)

### 3.1 创建任务 (Create Task)
*   **Endpoint**: `POST /api/oracle/task`
*   **描述**: 初始化一个新的任务上下文。
*   **请求体**:
    ```json
    {
      "project_id": "optional-string"
    }
    ```
*   **响应体**:
    ```json
    {
      "task_id": "uuid-string"
    }
    ```

### 3.2 生成/更新规格 (Generate Spec)
*   **Endpoint**: `POST /api/oracle/task/{task_id}/version/spec`
*   **描述**: 基于自然语言描述生成任务规格。这是核心入口。
*   **请求体**:
    ```json
    {
      "task_description": "实现一个斐波那契数列函数...",
      "language": "python", // default: python
      "deliverable_type": "function", // function | cli | script
      "debug_invalid_mock": false
    }
    ```
*   **响应体**:
    ```json
    {
      "version_id": "uuid-string",
      "spec_summary": {
        "goal_one_liner": "...",
        "constraints": ["O(n) time"],
        "signature": { "function_name": "fib", "args": [...] }
      },
      "ambiguities": [
        {
          "ambiguity_id": "amb_1",
          "description": "Start form 0 or 1?",
          "choices": [{ "choice_id": "c1", "text": "0" }, { "choice_id": "c2", "text": "1" }]
        }
      ],
      "oracle_confidence_initial": 0.85,
      "log_id": "uuid"
    }
    ```
*   **错误码**:
    *   `422 Unprocessable Entity`: `analyze_failed` (LLM 分析失败), `schema_validation_failed` (格式错误).

### 3.3 确认歧义 (Confirm Ambiguities)
*   **Endpoint**: `POST /api/oracle/version/{version_id}/confirm`
*   **描述**: 用户选择歧义的解决方案，推进状态。
*   **请求体**:
    ```json
    {
      "selections": {
        "amb_1": "c1",
        "amb_2": "c3"
      }
    }
    ```
*   **响应体**:
    ```json
    {
      "version_id": "uuid",
      "status": "ready" // or "low_confidence"
    }
    ```

### 3.4 生成测试用例 (Generate Tests)
*   **Endpoint**: `POST /api/oracle/version/{version_id}/generate-tests`
*   **描述**: 在规格确认后，生成公开和隐藏的测试用例。
*   **请求体**:
    ```json
    {
      "public_examples_count": 5,
      "hidden_tests_count": 10,
      "difficulty_profile": null
    }
    ```
*   **响应体**:
    ```json
    {
      "version_id": "uuid",
      "status": "ready",
      "public_examples_preview": [
        { "input": "...", "expected": "..." }
      ],
      "hidden_tests_count": 10,
      "oracle_confidence": 0.92
    }
    ```

### 3.5 运行评测 (Run Oracle)
*   **Endpoint**: `POST /api/oracle/version/{version_id}/run`
*   **描述**: 使用生成的测试用例评测当前代码。
*   **请求体**:
    ```json
    {
      "code_text": "def fib(n): ...", // 或传 code_snapshot_id
      "timeout_sec": 2.5
    }
    ```
*   **响应体**:
    ```json
    {
      "run_id": "uuid",
      "pass_rate": 1.0,
      "passed": 15,
      "failed": 0,
      "failures_summary": [] // 仅包含部分脱敏的失败信息
    }
    ```

## 4. 状态机与页面流程

### 状态流转图
1.  **Init**: 用户输入需求 -> 调用 `create_spec`。
2.  **Awaiting Confirmation**: 如果返回 `ambiguities` 不为空 -> **前端展示歧义选择卡片**。
3.  **Ready**: 用户提交选择 (调用 `confirm`) 或无歧义 -> **前端展示“生成测试”按钮**。
4.  **Tests Generated**: 调用 `generate_tests` 成功 -> **前端展示测试用例预览和“运行评测”按钮**。
5.  **Low Confidence**: 任何阶段若 `oracle_confidence < 0.4` -> **前端展示警告：需求可能模糊或 AI 不确定**，建议用户修改描述重试。

### 前端展示逻辑
| 状态 (Status) | 前端 UI 行为 | 可执行操作 |
| :--- | :--- | :--- |
| `analyze_failed` | 显示错误提示和重试按钮 | 修改需求重试 |
| `awaiting_confirmation` | 显示“歧义消除”表单 | 提交选择 (`confirm`) |
| `ready` (无测试) | 显示 Spec 摘要 | 点击“生成测试用例” |
| `ready` (有测试) | 显示测试列表 + 评测面板 | 点击“运行评测” |
| `low_confidence` | 显示黄色警告条 | 强制继续 或 修改需求 |

## 5. 前端技术栈与组件规范

### 技术栈
*   **Core**: React 18 + TypeScript
*   **State**: `useReducer` (在 `IDE.tsx` 中) 或 `useState` (局部组件)
*   **Network**: `src/services/api.ts` (需扩展)
*   **Styling**: CSS Modules 或全局 CSS (当前项目习惯)

### 建议组件结构
1.  **`src/components/OraclePane.tsx`**: 主容器，通过 Tab 切换 "Spec", "Tests", "Run"。
2.  **`src/components/oracle/SpecViewer.tsx`**: 展示生成的 JSON Spec (只读)。
3.  **`src/components/oracle/AmbiguityForm.tsx`**: 渲染 Radio Group 供用户选择。
4.  **`src/components/oracle/TestRunner.tsx`**: 展示评测进度条和结果列表。

### 路由集成
建议在 `src/components/IDE.tsx` 的右侧面板 (`EducationPane` 旁边) 增加一个 "Oracle" 标签页，复用现有的布局系统，而不是单独开一个全屏页面。
