export type JsonPrimitive = boolean | number | string | null;

export type JsonValue =
  | JsonPrimitive
  | readonly JsonValue[]
  | { readonly [key: string]: JsonValue };

export type JsonObject = { readonly [key: string]: JsonValue };

export type Office = {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly central_hub_ref: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type OfficeRole = 'owner' | 'editor' | 'viewer';

export type OfficeMember =
  | {
      readonly user_id: string;
      readonly instance_id: null;
    }
  | {
      readonly user_id: null;
      readonly instance_id: string;
    };

export type OfficeMembership = OfficeMember & {
  readonly id: string;
  readonly office_id: string;
  readonly posx: number;
  readonly posy: number;
  readonly role: OfficeRole;
  readonly permissions: JsonObject | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type Membership = OfficeMembership;

export type EmployeeRank = 'intern' | 'researcher' | 'director';

export type Employee = {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly rank: EmployeeRank;
  readonly preset_slug: string | null;
  readonly display_name: string | null;
  readonly display_color: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type PresetManifest = {
  readonly model: string;
  readonly prompt: string;
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

export type Instance = {
  readonly id: string;
  readonly employee_id: string;
  readonly office_id: string;
  readonly workspace_path: string | null;
  readonly status: InstanceStatus;
  readonly runtime_config: JsonObject | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type LoopStatus = 'idle' | 'running' | 'paused' | 'interrupted' | 'completed' | 'failed';

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

export type MemoryKind = 'experience' | 'lesson' | 'decision' | 'problem';

export type MemoryEntry = {
  readonly id: string;
  readonly employee_id: string;
  readonly kind: MemoryKind;
  readonly key: string | null;
  readonly content: string | null;
  readonly source_instance_id: string | null;
  readonly created_at: string;
};

export type CurrentUser = {
  readonly user_id: string;
  readonly is_super_admin: boolean;
  readonly token: string | null;
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
};

export type TopologyNode = {
  readonly kind: 'membership' | 'corridor_node';
  readonly id: string;
  readonly instanceId: string | null;
  readonly x: number;
  readonly y: number;
  readonly label: string;
  readonly slug: string;
  readonly role: string;
  readonly status: string;
  readonly fillColor: string;
  readonly glowColor: string;
  readonly glowIntensity: GlowIntensity;
  readonly outdated: boolean;
  readonly activeHash: string | null;
};

export type CorridorNodeStatus = 'active' | 'paused' | 'archived';

export type AggregatedMemoryCount = {
  readonly experience: number;
  readonly lesson: number;
  readonly decision: number;
  readonly problem: number;
  readonly total: number;
};

export type MemorySummaryOut = {
  readonly employee_id: string;
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
};

export type DistillResultOut = {
  readonly new_preset_id: string;
  readonly new_preset_slug: string;
  readonly new_preset_name: string;
  readonly manifest_preview: SkillManifestPreview;
  readonly aggregated_memory: AggregatedMemoryCount;
  readonly source_employee_id: string;
  readonly source_preset_slug: string | null;
};

export type CorridorNode = {
  readonly id: string;
  readonly office_id: string;
  readonly posx: number;
  readonly posy: number;
  readonly display_name: string;
  readonly glow_color: string | null;
  readonly status: CorridorNodeStatus;
  readonly created_by: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type CapabilityType = 'skill' | 'tool' | 'mcp' | 'lsp';

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
};

export type EntityInstanceStatus = {
  readonly id: string;
  readonly loop_status: LoopStatus;
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
  readonly promoted_at: string;
  readonly entity_id: string;
  readonly entity_promotion_migration_hash: string;
  readonly capability_promoted_count: number;
  readonly prompt_regenerated: boolean;
  readonly new_prompt_preview: string;
  readonly outdated_instances_count: number;
  readonly capability_market_uploaded: number;
};

export type TransmuteResult = {
  readonly new_base_class_id: string;
  readonly new_base_class_slug: string;
  readonly new_base_class_name: string;
  readonly manifest_preview: JsonObject;
  readonly source_employee_id: string;
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
  readonly provider?: string | null;
  readonly model?: string | null;
  readonly knowledge_env?: readonly KnowledgeEnvEntry[];
  readonly knowledge_files?: readonly KnowledgeFileEntry[];
};

export type OnboardingPayload = {
  readonly name: string;
  readonly slug: string;
  readonly rank: EmployeeRank;
  readonly preset_slug: string;
  readonly display_name: string;
  readonly runtime_config?: EmployeeRuntimeConfig;
};

export type KnowledgeScope = 'instance' | 'entity' | 'workspace';
