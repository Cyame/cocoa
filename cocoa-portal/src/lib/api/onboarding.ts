import { api } from '@/lib/api';
import { type BaseClassPage, fetchBaseClassesPage } from '@/lib/api/baseClasses';
import type { BaseClass, Employee, OnboardingPayload } from '@/lib/types';

export type { BaseClass, BaseClassPage };

export async function fetchBaseClasses(): Promise<readonly BaseClass[]> {
  const page = await fetchBaseClassesPage({ limit: 50, offset: 0 });
  return page.items;
}

export async function summonEntity(payload: OnboardingPayload): Promise<Employee> {
  return api<Employee>('/entities', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
