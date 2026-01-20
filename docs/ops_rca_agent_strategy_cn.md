# 运维与根因分析 (RCA) Agent 策略

## 1. 挑战：线性规划 vs. 故障排查
标准的 **Vibe Workflow (线性规划)** 并不适合运维和根因分析。

*   **软件工程 (建造者模式):** 你知道目的地。"构建一个登录页面" -> 步骤 1, 2, 3 (线性)。
*   **RCA (侦探模式):** 你**不知道**目的地。"网站挂了" -> 步骤 1 (查日志) -> 结果决定步骤 2 (动态)。

**为什么线性规划在运维中失效：**
*   它鼓励幻觉计划 (例如：在检查 DB 是否有问题之前，就计划"步骤 2：重启数据库")。
*   缺乏根据新证据转向的敏捷性。

**为什么纯 TODO 列表在运维中失效：**
*   高风险陷入“兔子洞” (无休止地尝试无关的修复)。
*   缺乏 **SOP (标准作业程序)** 约束。
*   在生产环境上进行危险的“试错”。

---

## 2. 推荐架构：诊断循环 (OODA)

不要使用 `Plan -> Execute`，而是使用 **OODA 循环** (观察-调整-决策-行动) 状态机。

### 工作流状态机
1.  **分诊 (Observe):**
    *   输入：报警、用户报告、近期日志。
    *   动作：总结当前状态。
2.  **假设生成 (Orient):**
    *   Agent 基于症状提出 *概率性* 的根因。
    *   *示例：* "假设 A: 磁盘已满 (60%)", "假设 B: 应用崩溃 (40%)"。
3.  **验证 (Decide & Act):**
    *   **关键：** 选择一个 **只读 Skill** 来验证假设。
    *   *动作：* 调用 `check_disk_usage` 或 `tail_app_logs`。
    *   *约束：* 此阶段严禁任何改变状态的操作 (写入/重启)。
4.  **决策 (Reflect):**
    *   如果找到根因 -> 进入 **修复阶段 (Remediation)**。
    *   如果未找到 -> 循环回到 **假设阶段**。

---

## 3. 运维 Skill 分类

运维 Agent 中的 Skill 必须严格分类以确保安全。

### A. 诊断 Skill (安全 / 只读)
*   `check_resource_usage` (CPU/内存/磁盘)
*   `query_logs` (Elasticsearch/Grep)
*   `check_process_status` (Systemd/K8s)
*   `network_connectivity_test` (Ping/Curl)
*   *实现：* 这些应作为原子工具通过 MCP 提供。

### B. 修复 Skill (高风险 / 人机交互)
*   `restart_service`
*   `clean_disk_space`
*   `scale_cluster`
*   *实现：* 执行前必须触发 Burr 工作流中的 `Human Confirm` (人工确认) 状态。

---

## 4. 实施策略

### 步骤 1：构建 "工具带 (Toolbelt)"
*   为基础设施 (Kubernetes, Linux Shell, Cloud Provider) 开发标准的 MCP 服务器。
*   确保明确区分 "读" 和 "写" 操作。

### 步骤 2：定义 "SOP Skills"
*   定义 SOP 为 `SKILL.md` 文件，而不是通用的编码 Skill。
*   *示例 `skills/k8s_pod_crash/SKILL.md`:*
    > "当 Pod 崩溃时：1. `kubectl describe` events。 2. `kubectl logs --previous`。 3. 检查 OOMKilled 状态。"

### 步骤 3：排查工作流 (The Troubleshooter)
*   修改 `vibe_workflow` 以支持诊断阶段的 **循环拓扑 (Looping Topology)**。
*   增加逻辑门：**"找到根因了吗？"**
    *   **否：** 重新进入调查循环。
    *   **是：** 进入修复计划 (线性 Vibe Plan)。

## 总结
对于运维/RCA，Agent 是一个 **手持 SOP 手册的高级工程师**。它必须遵循严格的诊断树 (假设 -> 验证) 以防止危险操作，只有在确认根因并获得批准后，才切换到线性执行模式。
