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
  readonly blackboard_ref: string | null;
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
