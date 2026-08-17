#!/usr/bin/env bash
# v4.9.1 Wave 4 用户验收一键脚本（orbstack）
# 用法: bash scripts/v4-9-1-acceptance.sh
# 前置: kubectl context = orbstack; eyot namespace 3 pods Ready
set -euo pipefail

echo "== 1. context 检查 =="
CTX=$(kubectl config current-context)
echo "context: $CTX"
[ "$CTX" = "orbstack" ] || { echo "FAIL: 非 orbstack, 中止"; exit 1; }

echo "== 2. pods 状态 =="
kubectl get pods -n eyot

echo "== 3. 后端 health =="
kubectl port-forward -n eyot svc/eyot-backend 4510:4510 >/dev/null 2>&1 &
PF1=$!
sleep 2
curl -s http://localhost:4510/health || true
echo
kill $PF1 2>/dev/null || true

echo "== 4. Portal 页脚版本（应含 4.9.1）=="
kubectl port-forward -n eyot svc/eyot-portal 5173:5173 >/dev/null 2>&1 &
PF2=$!
sleep 2
JS=$(curl -s http://localhost:5173/ | grep -oE 'src="[^"]*"' | head -1 | sed 's/src="//;s/"//')
echo "bundle: $JS"
curl -s "http://localhost:5173/$JS" | grep -o '4\.9\.[0-9]' | sort -u | head -1
kill $PF2 2>/dev/null || true

echo "== 5. alembic head（应 ddb7bd415907）=="
kubectl exec -n eyot deploy/eyot-backend -- alembic current 2>/dev/null | tail -1

echo
echo "== 6. 浏览器人工验收（浏览器打开 http://localhost:5173）=="
echo "   a) 登录后进入任一 workspace -> Brain 区 -> Cerebellum -> restart"
echo "      应看到状态走 restarting -> deploying（真实部署, 非直接 running）"
echo "   b) 引入化身下拉: 不应出现小脑实体（is_cerebellum 过滤）"
echo "   c) 侧栏页脚版本: v4.9.1"
echo
echo "完成 6a/6b/6c 后确认, orchestrator 勾选 Wave 4 Acceptance 收工"
