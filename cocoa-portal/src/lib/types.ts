export type JsonPrimitive = boolean | number | string | null;

export type JsonValue =
  | JsonPrimitive
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export type JsonObject = { readonly [key: string]: JsonValue };

export type Workspace = {
  readonly id: string;
  readonly namespace_id: string;
  readonly name: string;
  readonly slug: string;
  readonly created_at: string;
  readonly updated_at: string;
};

/** @deprecated Use Workspace */
export type Office = Workspace;

export type Namespace = {
  readonly id: string;
  readonly org_id: string;
  readonly slug: string;
  readonly name: string;
  readonly description: string | null;
  readonly tags: readonly string[] | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type WorkspaceMember =
  | {
      readonly user_id: string;
      readonly instance_id: null;
    }
  | {
      readonly user_id: null;
      readonly instance_id: string;
    };

export type WorkspaceMembership = WorkspaceMember & {
  readonly id: string;
  readonly workspace_id: string;
  readonly posx: number;
  readonly posy: number;
  // v4.0: no static role — authorization is computed from Contract atoms.
  readonly permissions: JsonObject | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly entity_slug?: string | null;
  readonly entity_name?: string | null;
  readonly username?: string | null;
  readonly nickname?: string | null;
};

export type Membership = WorkspaceMembership;

/** @deprecated Use WorkspaceMembership */
export type OfficeMembership = WorkspaceMembership;

/** @deprecated Use WorkspaceMember */
export type OfficeMember = WorkspaceMember;

export type EmployeeRank = 'intern' | 'researcher';

export type Entity = {
  readonly id: string;
  readonly namespace_id: string;
  readonly name: string;
  readonly slug: string;
  readonly rank: EmployeeRank;
  readonly preset_slug: string | null;
  readonly display_name: string | null;
  readonly display_color: string | null;
  readonly created_at: string;
  readonly updated_at: string;
  /** v4.9.3: real knowledge assets held by this entity (slug list). */
  readonly has_knowledge?: readonly string[] | null;
};

/** @deprecated Use Entity */
export type Employee = Entity;

export type PresetManifest = {
  readonly model: string;
  readonly prompt: string;
  /** v4.0: skills/tools/commands are readonly mirrors aggregated from
   * junction rows (base_class_capabilities / entity_capabilities) by the
   * backend on read paths — never a write truth. Writes go through the
   * capability / gene junction APIs; the arrays here may be absent or stale
   * on write payloads and are always server-filled in GET responses. */
  readonly skills: readonly string[];
  readonly tools: readonly string[];
  readonly commands: readonly string[];
};

export type EmployeePreset = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly version: string | null;
  readonly manifest: PresetManifest;
  readonly created_at: string;
  readonly updated_at: string;
};

export type InstanceStatus =
  | 'creating'
  | 'pending'
  | 'deploying'
  | 'running'
  | 'restarting'
  | 'failed'
  | 'deleting';

/** Product-facing avatar status (not K8s / harness loop enums). */
export type AvatarDisplayStatus =
  | 'busy'
  | 'idle'
  | 'stopped'
  | 'starting'
  | 'restarting'
  | 'deleting'
  | 'start_failed';

export type Instance = {
  readonly id: string;
  readonly entity_id: string;
  readonly workspace_id: string;
  readonly workspace_path: string | null;
  readonly status: InstanceStatus;
  readonly runtime_config: JsonObject | null;
  readonly created_at: string;
  readonly updated_at: string;
  readonly display_status?: AvatarDisplayStatus | null;
  readonly in_conversation?: boolean;
};

export type LoopStatus = 'idle' | 'running' | 'paused' | 'interrupted' | 'completed' | 'failed';

/**
 * v4.7 harness-collab: payload kinds accepted by
 * ``POST /api/v1/instances/{id}/inject`` (V47-5).
 * ``file_touch`` exists in the plan but is out of this slice.
 */
export type InjectKind = 'collab_inject' | 'gene_inject' | 'capability_inject' | 'cerebellum_route';

/** v4.7 delivery triad (plan §9): notify / soft_inject / wake. */
export type InjectDeliveryMode = 'notify' | 'soft_inject' | 'wake';

/** Typed handoff content reference (hub / instance scope). */
export type InjectContentRef = {
  readonly scope: string;
  readonly path: string;
  readonly label?: string | null;
};

/** Operator inject body for ``POST /api/v1/instances/{id}/inject``. */
export type InjectPayload = {
  readonly kind: InjectKind;
  readonly delivery_mode: InjectDeliveryMode;
  readonly tldr?: string | null;
  readonly content_refs?: readonly InjectContentRef[];
  readonly gene_ids?: readonly string[];
  readonly capability_ids?: readonly string[];
};

export type InstanceLoopState = {
  readonly instance_id: string;
  readonly loop_status: LoopStatus;
  readonly continuation_count: number;
  readonly total_token_estimate: number;
  readonly last_checkpoint_at: string | null;
  readonly breaker_config: JsonObject;
};

export type BoulderSnapshot = {
  readonly boulder_snapshot: JsonObject;
  readonly continuation_count: number;
  readonly captured_at: string;
};

export type Event = {
  readonly id: string;
  readonly type: string;
  readonly actor_type: string;
  readonly actor_id: string | null;
  readonly resource_type: string | null;
  readonly resource_id: string | null;
  readonly payload: JsonObject;
  readonly request_id: string | null;
  readonly created_at: string;
};

export type MemoryKind = 'experience' | 'lesson' | 'decision' | 'problem' | 'notepad';

export type MemoryEntry = {
  readonly id: string;
  readonly entity_id: string;
  readonly kind: MemoryKind;
  readonly key: string | null;
  readonly content: string | null;
  readonly source_instance_id: string | null;
  readonly created_at: string;
};

export type CurrentUser = {
  readonly user_id: string;
  readonly username?: string;
  readonly nickname?: string | null;
  readonly email?: string;
  readonly is_super_admin: boolean;
  readonly identity?: string | null;
  readonly locked_gene_slugs?: readonly string[];
  readonly extra_gene_slugs?: readonly string[];
  readonly token: string | null;
};

export type AuthUserPayload = {
  readonly id: string;
  readonly username: string;
  readonly nickname?: string | null;
  readonly email: string;
  readonly is_super_admin: boolean;
  readonly identity?: string | null;
  readonly locked_gene_slugs?: readonly string[];
  readonly extra_gene_slugs?: readonly string[];
};

export type GlowIntensity = 'static' | 'weak' | 'low' | 'medium' | 'strong';

export type GlowColor = {
  readonly color: string;
  readonly intensity: GlowIntensity;
};

export type LiveStatusItem = {
  readonly membership_id: string;
  readonly posx: number;
  readonly posy: number;
  readonly node_type: 'user' | 'instance';
  readonly glow: GlowColor;
  readonly outdated: boolean;
  readonly active_hash: string | null;
  readonly instance_status?: string | null;
  readonly mentionable?: boolean;
  readonly display_status?: AvatarDisplayStatus | null;
};

export type TopologyNode = {
  readonly kind: 'membership' | 'hub';
  readonly id: string;
  readonly instanceId: string | null;
  readonly x: number;
  readonly y: number;
  readonly label: string;
  readonly slug: string;
  readonly status: string;
  readonly fillColor: string;
  readonly glowColor: string;
  readonly glowIntensity: GlowIntensity;
  readonly outdated: boolean;
  readonly activeHash: string | null;
  readonly instanceStatus: string | null;
  readonly mentionable: boolean;
  readonly displayStatus: AvatarDisplayStatus | null;
  /** True when this seat is the signed-in Awakened user. */
  readonly isCurrentUser: boolean;
};

export type Passage = {
  readonly id: string;
  readonly workspace_id: string;
  readonly from_membership_id: string;
  readonly to_membership_id: string;
  readonly is_active: boolean;
  /** Duplex by default; stored endpoints are lexicographically ordered. */
  readonly mode?: string;
  readonly edge_meta: JsonObject | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type AggregatedMemoryCount = {
  readonly experience: number;
  readonly lesson: number;
  readonly decision: number;
  readonly problem: number;
  readonly notepad: number;
  readonly total: number;
};

export type MemorySummaryOut = {
  readonly entity_id: string;
  readonly aggregated_counts: AggregatedMemoryCount;
  readonly sample_lessons: readonly string[];
  readonly sample_keys_by_kind: Readonly<Record<string, readonly string[]>>;
};

export type SkillManifestPreview = {
  readonly model: string;
  readonly prompt: string;
  readonly skills: readonly string[];
  readonly tools: readonly string[];
  readonly commands: readonly string[];
};

export type DistillRequest = {
  readonly target_skill_slug: string;
  readonly memory_kind_filter?: readonly MemoryKind[] | null;
  readonly source_preset_slug?: string | null;
  readonly target_preset_name?: string | null;
  /** v4.9.3: distillation engine — ``heuristic`` (default) or ``llm`` (degrades on missing provider). */
  readonly engine?: 'heuristic' | 'llm';
};

export type DistillEngine = 'heuristic' | 'llm';

/** One capability distilled from entity memory into the capability_market (v4.9.3). */
export type CapabilityCandidate = {
  readonly id?: string;
  readonly name: string;
  readonly type: string;
  readonly description: string | null;
  readonly config_template: JsonObject | null;
  /** Slugs the capability needs to function (== knowledge_entries keys == Instance env keys). */
  readonly required_knowledge: readonly string[];
  readonly created_via?: string;
};

/** Response for ``POST /api/v1/learning/entities/{eid}/distill`` (v4.9.3). */
export type DistillResultOut = {
  readonly status: string;
  readonly capability_candidates: readonly CapabilityCandidate[];
  readonly capability_market_created: number;
  readonly gene_suggestion: string | null;
  /** Engine actually used (``llm`` degrades to ``heuristic``). */
  readonly engine_used: DistillEngine | string;
  readonly warnings: readonly string[];
  readonly aggregated_memory: AggregatedMemoryCount;
  readonly source_entity_id: string;
  readonly source_preset_slug: string | null;
};

export type CapabilityType = 'skill' | 'tool' | 'mcp' | 'lsp' | 'command';

export type CapabilitySource = 'from_base_class' | 'extra_added';

export type Capability = {
  readonly name: string;
  readonly type: CapabilityType;
  readonly version: string | null;
  readonly source: CapabilitySource;
  readonly description: string | null;
  readonly tags: readonly string[];
};

export type AiGeneKind = 'tool-gene' | 'meta-gene' | 'genome' | 'workflow-gene';

export type AiGeneSource = 'from_base_class' | 'extra_added';

export type AiGene = {
  readonly slug: string;
  readonly name: string;
  readonly kind: AiGeneKind;
  readonly tags: readonly string[];
  readonly source: AiGeneSource;
};

export type BaseClass = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly display_name: string | null;
  readonly description: string | null;
  readonly manifest: JsonObject | null;
  readonly version: string | null;
  readonly tags: readonly string[] | null;
  readonly created_at: string;
  /** v4.9.3: real knowledge assets held by this base class (slug list). */
  readonly has_knowledge?: readonly string[] | null;
};

export type EntityInstanceStatus = {
  readonly id: string;
  readonly entity_id: string;
  readonly workspace_id: string;
  /** Lifecycle status from Instance.status (running/pending/…). */
  readonly status: string;
  /** Product-facing avatar status (busy/idle/stopped/…). */
  readonly display_status: AvatarDisplayStatus;
  readonly in_conversation: boolean;
  readonly continuation_count: number;
  readonly last_checkpoint_at: string | null;
  readonly pod_name: string | null;
  readonly spawn_time: string;
  readonly last_active_at: string | null;
};

export type EntityPatchPayload = {
  readonly name?: string;
  readonly display_name?: string | null;
  readonly display_color?: string | null;
  readonly preset_slug?: string | null;
  readonly rank?: EmployeeRank;
};

export type PromoteResult = {
  readonly status: string;
  readonly mode?: string;
  readonly promoted_at: string;
  readonly entity_id: string;
  readonly entity_promotion_migration_hash: string;
  readonly capability_promoted_count: number;
  readonly prompt_regenerated: boolean;
  readonly new_prompt_preview: string;
  readonly outdated_instances_count: number;
  readonly capability_market_uploaded: number;
  readonly new_entity_id?: string | null;
  /** v4.9.3: entity has_knowledge after the promote aggregate (union with source instance env keys). */
  readonly has_knowledge: readonly string[];
};

export type TransmuteResult = {
  readonly new_base_class_id: string;
  readonly new_base_class_slug: string;
  readonly new_base_class_name: string;
  readonly manifest_preview: JsonObject;
  readonly source_entity_id: string;
  /** v4.9.3: AiGene slugs written to the base_class_ai_genes junction. */
  readonly default_gene_refs: readonly string[];
  /** v4.9.3: has_knowledge mounted from the source Entity. */
  readonly has_knowledge: readonly string[];
};

export type ReapResult = {
  readonly status: string;
  readonly reaped_at: string;
  readonly instance_id: string;
  readonly memory_consumed: number;
  readonly capability_distilled: readonly JsonObject[];
  readonly capability_market_uploaded: number;
  readonly instance_local_added: number;
  readonly entity_changed: boolean;
};

export type CombineResult = {
  readonly new_gene_id: string;
  readonly new_gene_slug: string;
  readonly referenced_capabilities: readonly string[];
  readonly manifest_preview: JsonObject;
  readonly entity_id?: string | null;
  readonly base_class_id?: string | null;
};

export type KnowledgeEnvEntry = {
  readonly key: string;
  readonly value: string;
};

export type KnowledgeFileEntry = {
  readonly name: string;
  readonly size_bytes: number;
  readonly content_base64?: string;
};

export type EmployeeRuntimeConfig = {
  readonly knowledge_env?: readonly KnowledgeEnvEntry[];
  readonly knowledge_files?: readonly KnowledgeFileEntry[];
};

export type EntityConfigOverride = {
  readonly provider_id?: string | null;
  readonly model?: string | null;
  readonly runtime_config?: EmployeeRuntimeConfig;
};

export type OnboardingPayload = {
  readonly name: string;
  readonly slug: string;
  readonly rank: EmployeeRank;
  readonly preset_slug: string;
  readonly display_name: string;
  readonly system_prompt?: string | null;
  readonly config_override?: EntityConfigOverride | null;
};

export type KnowledgeScope = 'instance' | 'entity' | 'workspace';

export type UserBrief = {
  readonly id: string;
  readonly username: string;
  readonly email: string;
  readonly nickname: string | null;
};

export type GeneBrief = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
};

export type Organization = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly description: string | null;
  readonly system_hub_provider_id: string | null;
  readonly system_hub_model: string | null;
  readonly cerebellum_default_provider_id: string | null;
  readonly cerebellum_default_model: string | null;
  readonly use_proxy: boolean;
  readonly proxy_host: string | null;
  readonly proxy_port: number | null;
  readonly proxy_username: string | null;
  readonly proxy_password: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type OrgMember = {
  readonly id: string;
  readonly user: UserBrief;
  readonly atoms: readonly GeneBrief[];
  readonly created_at: string;
};

export type OrgIdentity = {
  readonly organization_id: string;
  readonly atoms: readonly string[];
  readonly display_label: string;
};

/** v4.8 meeting lifecycle status (see `.omo/plans/v4-8-meetings-schedules.md`). */
export type MeetingStatus = 'scheduled' | 'active' | 'ended' | 'cancelled';

/** One membership seat in a meeting (`meeting_participants` row). */
export type MeetingParticipant = {
  readonly id: string;
  readonly meeting_id: string;
  readonly membership_id: string;
  /** Free-form label, NOT an auth role (plan M3). */
  readonly role_in_meeting?: string | null;
};

/** `POST /api/v1/meetings` + `GET /api/v1/meetings/{id}` shape. */
export type Meeting = {
  readonly id: string;
  readonly workspace_id: string;
  readonly title: string;
  readonly agenda: string | null;
  readonly status: MeetingStatus;
  readonly scheduled_at: string;
  readonly ended_at: string | null;
  readonly created_by_user_id: string;
  readonly created_at: string;
  readonly updated_at: string | null;
  /** Only present on create / detail responses; list items carry an empty array. */
  readonly participants?: readonly MeetingParticipant[];
};

/** `brainstem_schedules` row — fired by the backend runner on cron. */
export type BrainstemSchedule = {
  readonly id: string;
  readonly central_hub_id: string;
  readonly name: string;
  readonly cron_expr: string;
  readonly action_payload: JsonObject | null;
  readonly enabled: boolean;
  readonly last_run_at: string | null;
  readonly next_run_at: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};
