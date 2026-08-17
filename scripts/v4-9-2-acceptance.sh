#!/usr/bin/env bash
# v4.9.2 Wave 用户验收一键脚本（orbstack）
# 用法: bash scripts/v4-9-2-acceptance.sh
# 前置: kubectl context = orbstack; eyot namespace 3 pods Ready
# v4.9.2 = 基因/能力创建补全 + 基因多选能力（全走 manifest + 运行时展开去重）
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
kubectl get pods -n eyot

echo "== 3. 后端 health =="
kubectl port-forward -n eyot svc/eyot-backend 4510:4510 >/dev/null 2>&1 &
PF_PIDS+=($!)
sleep 2
HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:4510/health || true)
echo "health http: $HTTP"
[ "$HTTP" = "200" ] && echo "OK: /health 返回 200" || { echo "WARN: /health 非 200（$HTTP）, 继续走后续检查"; }
curl -s http://localhost:4510/health || true
echo

echo "== 4. Portal 页脚版本（应含 v4.9.2）=="
echo "   经 NodePort 30173 取 index.html -> JS bundle -> grep 版本"
JS=$(curl -s http://localhost:30173/ | grep -oE 'src="[^"]*"' | head -1 | sed 's/src="//;s/"//')
echo "bundle: $JS"
[ -n "$JS" ] || { echo "FAIL: 未取到 JS bundle"; }
VERSION=$(curl -s "http://localhost:30173/$JS" | grep -oE '4\.9\.[0-9]+' | sort -u | head -1 || true)
echo "bundle 内版本: $VERSION"
echo "（若上方无输出或为空, 请浏览器打开 http://localhost:30173/ 看侧栏页脚应显示 v4.9.2）"

echo "== 5. alembic head（应显示 head, 提示无新迁移）=="
kubectl exec -n eyot deploy/eyot-backend -- alembic current 2>/dev/null | tail -1
echo "   （v4.9.2 无 schema 变更: 无新迁移, head 即当前线上版本）"

echo
echo "== 6. 浏览器人工验收（浏览器打开 http://localhost:30173/）=="
echo "   a) Genes 页 -> 深海基因 -> 创建: 能力多选区出现（从能力市场拉 checkbox）"
echo "      勾选能力保存后, 基因 manifest 应含所选能力"
echo "   b) Capabilities 页: 创建能力时应见 config_template + tags 字段"
echo "   c) 闭环: 给实体 attach 含内联能力的基因 -> 实体能力列表含之"
echo "      同一能力单独 attach（不重复）: 实体能力列表不出现重复项"
echo "   d) 侧栏页脚版本: v4.9.2"
echo
echo "   可对照证据: .omo/evidence/v4-9-2-e2e-closed-loop.md（API 闭环 10/10）"
echo "             + .omo/evidence/v4-9-2-browser-qa.md（浏览器 PASS）"
echo
echo "完成 6a/6b/6c/6d 后确认, orchestrator 勾选 v4.9.2 Acceptance 收工"
