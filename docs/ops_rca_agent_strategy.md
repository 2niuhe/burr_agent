# Operations & Root Cause Analysis (RCA) Agent Strategy

## 1. The Challenge: Linear Planning vs. Troubleshooting
The standard **Vibe Workflow (Linear Planning)** is ill-suited for Operations and Root Cause Analysis.

*   **Software Engineering (Builder Pattern):** You know the destination. "Build a login page" -> Step 1, 2, 3 (Linear).
*   **RCA (Detective Pattern):** You do NOT know the destination. "Site is down" -> Step 1 (Check Logs) -> Result determines Step 2 (Dynamic).

**Why Linear Planning Fails in Ops:**
*   It encourages hallucinated plans (e.g., "Step 2: Restart Database" before even checking if the DB is the issue).
*   It lacks the agility to pivot based on new evidence.

**Why Pure TODO Lists Fail in Ops:**
*   High risk of "Rabbit Holes" (Endlessly trying unrelated fixes).
*   Lack of **SOP (Standard Operating Procedure)** adherence.
*   Dangerous "Try-and-Error" on production systems.

---

## 2. Recommended Architecture: The Diagnostic Loop (OODA)

Instead of `Plan -> Execute`, use an **OODA Loop** (Observe, Orient, Decide, Act) state machine.

### The Workflow State Machine
1.  **Triage (Observe):**
    *   Input: Alerts, User Report, Recent Logs.
    *   Action: Summarize the current state.
2.  **Hypothesis Generation (Orient):**
    *   Agent proposes *probabilistic* root causes based on symptoms.
    *   *Example:* "Hypothesis A: Disk Full (60%)", "Hypothesis B: App Crash (40%)".
3.  **Verification (Decide & Act):**
    *   **Crucial:** Select a **Read-Only Skill** to verify the hypothesis.
    *   *Action:* Call `check_disk_usage` or `tail_app_logs`.
    *   *Constraint:* Strictly NO state-changing actions (writes/restarts) in this phase.
4.  **Decision (Reflect):**
    *   If Root Cause Found -> Move to **Remediation**.
    *   If Not Found -> Loop back to **Hypothesis**.

---

## 3. Skill Categorization for Ops

Skills in an Ops Agent must be strictly categorized to ensure safety.

### A. Diagnostic Skills (Safe / Read-Only)
*   `check_resource_usage` (CPU/RAM/Disk)
*   `query_logs` (Elasticsearch/Grep)
*   `check_process_status` (Systemd/K8s)
*   `network_connectivity_test` (Ping/Curl)
*   *Implementation:* These should be encapsulated atomic tools provided via MCP.

### B. Remediation Skills (High Risk / Human-in-the-Loop)
*   `restart_service`
*   `clean_disk_space`
*   `scale_cluster`
*   *Implementation:* These must trigger a `Human Confirm` state in the Burr workflow before execution.

---

## 4. Implementation Strategy

### Step 1: Build the "Toolbelt"
*   Develop standard MCP servers for the infrastructure (Kubernetes, Linux Shell, Cloud Provider).
*   Ensure "Read" and "Write" operations are clearly distinguished.

### Step 2: Define "SOP Skills"
*   Instead of generic coding skills, define SOPs as `SKILL.md` files.
*   *Example `skills/k8s_pod_crash/SKILL.md`:*
    > "When a pod crashes: 1. `kubectl describe` events. 2. `kubectl logs --previous`. 3. Check OOMKilled status."

### Step 3: The Troubleshooter Workflow
*   Modify `vibe_workflow` to support a **Looping Topology** for the diagnosis phase.
*   Add a logic gate: **"Found Root Cause?"**
    *   **No:** Re-enter Investigation Loop.
    *   **Yes:** Enter Remediation Plan (Linear Vibe Plan).

## Summary
For Ops/RCA, the Agent is a **Senior Engineer with an SOP Manual**. It must follow a strict diagnostic tree (Hypothesis -> Verification) to prevent dangerous operations, only switching to linear execution once the root cause is confirmed and the fix is approved.
