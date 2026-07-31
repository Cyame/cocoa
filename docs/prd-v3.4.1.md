# PRD-v3.4.1 — Composer 协议、流式终态与部署

> Product version: **3.4.1** (PATCH)  
> Follow-up: **3.4.2** = 全神职基础 gene/capability 包（空间会话 + 拓扑邻接说话）

## Scope

1. Provider 自定义时模型下拉无 inherit；切自定义清空 model  
2. Composer `@` 邻接补全 + `/` 四族贴输入框 + 分格预览 + Cmd/Ctrl+Enter  
3. 多路调度：`user_turn` + `LLMClient.stream` / stub + Composer SSE（`chat.response.chunk|done|error`）+ responding/done  
4. `deploy_existing_instance`；introduce 后自动 deploy  
5. 拓扑 fit-all + 「Composer 聊」预填 `@slug`

## Non-goals (→ 3.4.2 / later)

- 全神职基础 gene/capability 包  
- 迷失者互聊  
- 完整 Tunnel WS / multimodal session-engine  
