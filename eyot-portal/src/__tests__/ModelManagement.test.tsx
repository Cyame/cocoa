import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ModelInputCombobox } from '@/components/ModelInputCombobox';

const options = [
  { id: 'gpt-4o', name: 'GPT-4o' },
  { id: 'deepseek-v4', name: 'DeepSeek V4' },
];

describe('ModelInputCombobox', () => {
  it('shows placeholder when no value selected', () => {
    render(
      <ModelInputCombobox
        value=""
        onChange={() => {}}
        options={options}
        placeholder="Select a model"
      />,
    );
    expect(screen.getByRole('combobox')).toHaveTextContent('Select a model');
  });

  it('displays selected model id and name when different', () => {
    render(<ModelInputCombobox value="gpt-4o" onChange={() => {}} options={options} />);
    const btn = screen.getByRole('combobox');
    expect(btn.textContent).toContain('gpt-4o');
    expect(btn.textContent).toContain('GPT-4o');
  });

  it('renders as a button not a text input', () => {
    render(<ModelInputCombobox value="" onChange={() => {}} options={options} />);
    expect(screen.getByRole('combobox').tagName).toBe('BUTTON');
  });

  it('opens dropdown on click and shows options', () => {
    render(<ModelInputCombobox value="" onChange={() => {}} options={options} />);
    fireEvent.click(screen.getByRole('combobox'));
    expect(screen.getByRole('button', { name: /gpt-4o/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /deepseek-v4/ })).toBeInTheDocument();
  });

  it('selects option and calls onChange', () => {
    const onChange = vi.fn();
    render(<ModelInputCombobox value="" onChange={onChange} options={options} />);
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByRole('button', { name: /gpt-4o.*GPT-4o/ }));
    expect(onChange).toHaveBeenCalledWith('gpt-4o');
  });

  it('closes dropdown after selection', () => {
    const onChange = vi.fn();
    render(<ModelInputCombobox value="" onChange={onChange} options={options} />);
    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(screen.getByRole('button', { name: /deepseek-v4/ }));
    expect(screen.queryByRole('button', { name: /gpt-4o/ })).not.toBeInTheDocument();
  });

  it('shows selected id only when name matches id', () => {
    const sameOptions = [{ id: 'gpt-4o', name: 'gpt-4o' }];
    render(<ModelInputCombobox value="gpt-4o" onChange={() => {}} options={sameOptions} />);
    const btn = screen.getByRole('combobox');
    expect(btn.textContent).toBe('gpt-4o');
  });

  it('disables button when disabled prop is true', () => {
    render(<ModelInputCombobox value="" onChange={() => {}} options={options} disabled />);
    expect(screen.getByRole('combobox')).toBeDisabled();
  });
});
