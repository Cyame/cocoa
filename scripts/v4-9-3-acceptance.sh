#!/usr/bin/env bash
# v4.9.3 Wave 用户验收一键脚本（orbstack）
# 用法: bash scripts/v4-9-3-acceptance.sh
# 前置: kubectl context = orbstack; cocoa namespace 3 pods Ready
# v4.9.3 = 炼化体系对齐（distill=memory→capability / promote=Instance→Entity /
#          transmute=Entity→BaseClass）+ knowledge 双维度（require/has）+ spawn 自洽非阻断提示
set -euo pipefail

PF_PIDS=()
cleanup() {
  for pid in "${PF_PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

echo "== 1. context 检查 =="
CTX=$(kubectl config current-context)
echo "context: $CTX"
[ "$CTX" = "orbstack" ] || { echo "FAIL: 非 orbstack, 中止"; exit 1; }

echo "== 2. pods 状态（应 3 pods Ready）=="
kubectl get pods -n cocoa

echo "== 3. 后端 health + alembic head =="
kubectl port-forward -n cocoa svc/cocoa-backend 4510:4510 >/dev/null 2>&1 &
PF_PIDS+=($!)
sleep 2
HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:4510/health || true)
echo "health http: $HTTP"
curl -s http://localhost:4510/health || true; echo
echo "alembic head:"
kubectl exec -n cocoa deploy/cocoa-backend -- alembic current 2>/dev/null | tail -1

echo "== 4. v4.9.3 语义烟测（distill → capability_market + required_knowledge）=="
TS=$(date +%s)
BASE=http://localhost:4510/api/v1
# 注册用户
REG=$(curl -s -X POST "$BASE/auth/register" -H "Content-Type: application/json" \
  -d "{\"username\":\"e2e_493_$TS\",\"email\":\"e2e_493_$TS@cocoa.e2e\",\"password\":\"e2e-pass-493\"}")
TOKEN=$(echo "$REG" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
[ -n "$TOKEN" ] && echo "OK: register token" || { echo "FAIL: register 无 token: $REG"; exit 1; }
AUTH="Authorization: Bearer $TOKEN"

# 建 org/namespace/workspace
ORG=$(curl -s -X POST "$BASE/organizations" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"slug\":\"e2e493-org-$TS\",\"name\":\"e2e493 org $TS\"}")
ORG_ID=$(echo "$ORG" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "org: $ORG_ID"
NS=$(curl -s -X POST "$BASE/namespaces" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"slug\":\"e2e493-ns-$TS\",\"name\":\"e2e493 ns\",\"org_id\":\"$ORG_ID\"}")
NS_ID=$(echo "$NS" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "namespace: $NS_ID"
WS=$(curl -s -X POST "$BASE/workspaces" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"slug\":\"e2e493-ws-$TS\",\"name\":\"e2e493 ws\",\"namespace_id\":\"$NS_ID\"}")
WS_ID=$(echo "$WS" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "workspace: $WS_ID"

# 建 entity
ENT=$(curl -s -X POST "$BASE/entities" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"name\":\"E2E493 Agent\",\"slug\":\"e2e493-agent-$TS\",\"namespace_id\":\"$NS_ID\",\"rank\":\"intern\"}")
ENT_ID=$(echo "$ENT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "entity: $ENT_ID"

# 写一条 memory（lesson + kebab key 作 required 声明来源）
MEM=$(curl -s -X POST "$BASE/memory/entries" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"entity_id\":\"$ENT_ID\",\"kind\":\"lesson\",\"key\":\"debug-timeout-check\",\"content\":\"Always verify request timeouts before retrying idempotent calls to avoid duplicate side effects in long-running pipelines.\"}")
echo "memory: $(echo "$MEM" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('id', d))" 2>/dev/null)"

# spawn 自洽检查 + 建立 workspace 关联（distill 需 entity 有 Instance）
echo "== 4b. spawn 自洽检查（has ⊇ required, 缺 required → warning 但不阻断）=="
CAP=$(curl -s -X POST "$BASE/capability-market" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"name\":\"req-know-qa-$TS\",\"type\":\"skill\",\"scope\":\"org\",\"organization_id\":\"$ORG_ID\",\"required_knowledge\":[\"missing-knowledge-key\"]}")
CAP_ID=$(echo "$CAP" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "?")
echo "capability(with required_knowledge): $CAP_ID"
INST=$(curl -s -X POST "$BASE/instances" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"entity_id\":\"$ENT_ID\",\"workspace_id\":\"$WS_ID\"}")
echo "--- instance create response (自洽 warning 部分) ---"
echo "$INST" | python3 -c "
import sys,json
d=json.load(sys.stdin)
w=d.get('knowledge_consistency_warning')
if w:
    print('PASS: spawn 返回 knowledge_consistency_warning missing=%s（非阻断, 实例仍创建）' % w.get('missing'))
else:
    print('NOTE: 无自洽 warning（可能 required 为空或已满足）; instance id=%s' % d.get('id', d))
" 2>/dev/null || echo "$INST"
INST_ID=$(echo "$INST" | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
echo "instance: $INST_ID"

# distill 新语义：memory → capability_market（此时 entity 已有 Instance → workspace 解析成功）
DIST=$(curl -s -X POST "$BASE/learning/entities/$ENT_ID/distill" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"target_skill_slug\":\"timeout-qa\",\"engine\":\"heuristic\"}")
echo "--- distill response ---"
echo "$DIST" | python3 -m json.tool 2>/dev/null | head -40 || echo "$DIST"
echo "$DIST" | python3 -c "
import sys,json
d=json.load(sys.stdin)
cands=d.get('capability_candidates',[])
assert cands, 'FAIL: distill 无 capability_candidates'
assert d.get('engine_used')=='heuristic', f\"FAIL: engine_used={d.get('engine_used')}\"
c0=cands[0]
assert 'required_knowledge' in c0, 'FAIL: candidate 无 required_knowledge 字段'
print('PASS: distill 产出 capability_candidates=%d, engine_used=%s, first candidate name=%s required_knowledge=%s' % (
    len(cands), d.get('engine_used'), c0.get('name'), c0.get('required_knowledge')))
"

echo "== 5. capability_market 中 created_via=distill =="
# 列出市场里本次 distill 的条目（按时间最后几条过滤）
curl -s "$BASE/capability-market?limit=20" -H "$AUTH" | python3 -c "
import sys,json
d=json.load(sys.stdin)
items=d if isinstance(d,list) else d.get('items', d.get('data', []))
dist=[i for i in items if i.get('created_via')=='distill']
print('distill 条目数:', len(dist))
if dist:
    i=dist[-1]
    print('PASS: 存在 created_via=distill 条目 name=%s, required_knowledge=%s' % (i.get('name'), i.get('required_knowledge')))
else:
    print('WARN: 未在最近列表看到 distill 条目（可能分页）, 人工在 Portal 能力市场确认')
"

echo
echo "== 6. 浏览器人工验收（浏览器打开 http://localhost:30173/）=="
echo "   a) 眷族详情 -> Distill tab: 输入技能名 + heuristic/llm 切换 -> 提交后显示能力候选（name/type/required_knowledge）+ gene_suggestion + engine_used"
echo "   b) 能力市场 (/orgs/:id/capabilities): skill 型创建为结构化表单 + required_knowledge 多选; mcp/tool/command/lsp 分型渲染"
echo "   c) 深海基因编辑: required_knowledge 勾选 + 排序; 能力编排器"
echo "   d) Distill 结果弹窗: 字段与后端真实 manifest 对齐（default_gene_refs/has_knowledge 等）"
echo
echo "== 7. 版本（应 v4.9.3）=="
JS=$(curl -s http://localhost:30173/ | grep -oE 'src="[^"]*"' | head -1 | sed 's/src="//;s/"//')
VERSION=$(curl -s "http://localhost:30173/$JS" | grep -oE '4\.9\.3' | sort -u | head -1 || true)
echo "bundle 内版本: ${VERSION:-未检出（浏览器看侧栏页脚应 v4.9.3）}"
echo
echo "== DONE =="
