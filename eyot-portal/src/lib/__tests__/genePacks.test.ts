import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import portalSeeds from '@/lib/gene_pack_seeds.json';
import { GENE_PACKS } from '@/lib/genePacks';

const here = dirname(fileURLToPath(import.meta.url));
const backendSeedsPath = join(here, '../../../../eyot-backend/app/core/gene_pack_seeds.json');

describe('genePacks', () => {
  it('has unique pack ids', () => {
    const ids = GENE_PACKS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('GENE_PACKS matches portal gene_pack_seeds.json', () => {
    expect(GENE_PACKS).toEqual(portalSeeds.packs);
  });

  it('portal gene_pack_seeds.json deep-equals backend SoT', () => {
    const backendRaw = readFileSync(backendSeedsPath, 'utf8');
    const backendJson = JSON.parse(backendRaw) as unknown;
    expect(portalSeeds).toEqual(backendJson);
  });
});
