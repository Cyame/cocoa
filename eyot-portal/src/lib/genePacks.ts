/**
 * Gene pack catalog for portal UI.
 * Source of truth: eyot-backend/app/core/gene_pack_seeds.json (keep portal copy in sync; see genePacks.test.ts).
 */
import seedData from '@/lib/gene_pack_seeds.json';

export type GenePackSeed = {
  readonly id: string;
  readonly label_key: string;
  readonly slugs: readonly string[];
};

export type GenePackSeedsFile = {
  readonly packs: readonly GenePackSeed[];
};

const seeds = seedData as GenePackSeedsFile;

export const GENE_PACKS: readonly GenePackSeed[] = seeds.packs;
