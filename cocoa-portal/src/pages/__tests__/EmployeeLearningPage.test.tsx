import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import EmployeeLearningPage from '@/pages/EmployeeLearningPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const EMPLOYEE_ID = 'employee-1';

const SUMMARY_RESPONSE = {
  employee_id: EMPLOYEE_ID,
  aggregated_counts: {
    experience: 3,
    lesson: 5,
    decision: 2,
    problem: 1,
    total: 11,
  },
  sample_lessons: [
    'Always verify DB constraints before dropping columns.',
    'Alembic autogenerate cannot detect column renames.',
    'Partial unique indexes are required for soft-delete schemas.',
    'Use POST /resources/{id}/action for actions, not :action syntax.',
    'Never hardcode hex colors; use design tokens.',
  ],
  sample_keys_by_kind: {
    lesson: ['db-migration', 'api-design'],
    decision: ['soft-delete'],
  },
};

const EMPLOYEE_RESPONSE = {
  id: EMPLOYEE_ID,
  name: '密士',
  slug: 'mishi',
  rank: 'researcher',
  preset_slug: 'mishi-base',
  display_name: null,
  display_color: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const DISTILL_RESPONSE = {
  new_preset_id: 'preset-9',
  new_preset_slug: 'mishi-base-skill-code-review',
  new_preset_name: 'Skill: code-review',
  manifest_preview: {
    model: 'tbd',
    prompt: 'Review code carefully and surface issues.',
    skills: ['code-review', 'lint'],
    tools: [],
    commands: ['review', 'lint'],
  },
  aggregated_memory: {
    experience: 3,
    lesson: 5,
    decision: 2,
    problem: 1,
    total: 11,
  },
  source_employee_id: EMPLOYEE_ID,
  source_preset_slug: 'mishi-base',
};

function renderLearningPage() {
  return render(
    <MemoryRouter initialEntries={[`/employees/${EMPLOYEE_ID}/learning`]}>
      <Routes>
        <Route path="/employees/:employeeId/learning" element={<EmployeeLearningPage />} />
        <Route path="/employee-presets/:slug" element={<div>Preset detail stub</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  mockedApi.mockImplementation((path) => {
    if (path === `/learning/memories/${EMPLOYEE_ID}/summary`) {
      return Promise.resolve(SUMMARY_RESPONSE);
    }
    if (path === `/employees/${EMPLOYEE_ID}`) {
      return Promise.resolve(EMPLOYEE_RESPONSE);
    }
    return Promise.reject(new Error(`Unmocked path: ${path}`));
  });
});

describe('EmployeeLearningPage', () => {
  it('renders summary counts and sample lessons from the API', async () => {
    renderLearningPage();

    expect(
      await screen.findByRole('heading', { name: 'Learning & distillation' }),
    ).toBeInTheDocument();

    expect(screen.getByTestId('count-experience')).toHaveTextContent('3');
    expect(screen.getByTestId('count-lesson')).toHaveTextContent('5');
    expect(screen.getByTestId('count-decision')).toHaveTextContent('2');
    expect(screen.getByTestId('count-problem')).toHaveTextContent('1');

    expect(
      screen.getByText('Always verify DB constraints before dropping columns.'),
    ).toBeInTheDocument();
    expect(mockedApi).toHaveBeenCalledWith(`/learning/memories/${EMPLOYEE_ID}/summary`);
  });

  it('submits the distill form, calls POST /distill, and shows the result modal', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === `/learning/memories/${EMPLOYEE_ID}/summary`) {
        return Promise.resolve(SUMMARY_RESPONSE);
      }
      if (path === `/employees/${EMPLOYEE_ID}`) {
        return Promise.resolve(EMPLOYEE_RESPONSE);
      }
      if (path === `/learning/employees/${EMPLOYEE_ID}/distill` && init?.method === 'POST') {
        return Promise.resolve(DISTILL_RESPONSE);
      }
      return Promise.reject(new Error(`Unmocked call: ${init?.method ?? 'GET'} ${path}`));
    });

    renderLearningPage();
    await screen.findByRole('heading', { name: 'Learning & distillation' });

    fireEvent.change(screen.getByLabelText(/Target skill slug/i), {
      target: { value: 'code-review' },
    });
    fireEvent.change(screen.getByLabelText(/Source preset slug/i), {
      target: { value: 'mishi-base' },
    });
    fireEvent.click(screen.getByRole('checkbox', { name: 'Lesson' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Decision' }));

    fireEvent.click(screen.getByRole('button', { name: /^Distill$/i }));

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();

    expect(screen.getByText('mishi-base-skill-code-review')).toBeInTheDocument();
    expect(screen.getByText('Skill: code-review')).toBeInTheDocument();
    expect(screen.getByText('code-review, lint')).toBeInTheDocument();

    await waitFor(() => {
      const distillCall = mockedApi.mock.calls.find(
        ([path, init]) =>
          path === `/learning/employees/${EMPLOYEE_ID}/distill` && init?.method === 'POST',
      );
      expect(distillCall).toBeDefined();
      if (distillCall === undefined) {
        throw new Error('Expected POST /distill call');
      }
      const init = distillCall[1] as RequestInit;
      const body = JSON.parse(init.body as string);
      expect(body).toEqual({
        target_skill_slug: 'code-review',
        memory_kind_filter: expect.arrayContaining(['lesson', 'decision']),
        source_preset_slug: 'mishi-base',
        target_preset_name: null,
      });
      expect(body.memory_kind_filter).toHaveLength(2);
    });
  });

  it('disables submit and shows validation error for invalid skill slug', async () => {
    renderLearningPage();
    await screen.findByRole('heading', { name: 'Learning & distillation' });

    const slugInput = screen.getByLabelText(/Target skill slug/i);
    fireEvent.change(slugInput, { target: { value: 'Invalid Skill' } });
    fireEvent.blur(slugInput);

    expect(await screen.findByText(/Skill slug must be kebab-case/i)).toBeInTheDocument();

    const submitButton = screen.getByRole('button', { name: /^Distill$/i });
    expect(submitButton).toBeDisabled();

    fireEvent.click(submitButton);
    expect(mockedApi).not.toHaveBeenCalledWith(
      `/learning/employees/${EMPLOYEE_ID}/distill`,
      expect.anything(),
    );
  });
});
