import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { PipelineStory } from '../components/PipelineStory';

vi.mock('motion/react', () => ({ useReducedMotion: () => true }));
afterEach(cleanup);

it('changes the method detail on hover and supports keyboard selection', () => {
  render(<PipelineStory />);
  expect(
    screen.getByRole('tab', { name: /source/i }).getAttribute('aria-selected'),
  ).toBe('true');
  expect(screen.getByLabelText('source process diagram')).toBeTruthy();
  const connect = screen.getByRole('tab', { name: /connect/i });
  fireEvent.mouseEnter(connect);
  expect(connect.getAttribute('aria-selected')).toBe('true');
  expect(
    screen.getByRole('heading', { name: 'See the connections.' }),
  ).toBeTruthy();
  expect(screen.getByLabelText('connect process diagram')).toBeTruthy();
  fireEvent.keyDown(connect, { key: 'ArrowDown' });
  expect(
    screen
      .getByRole('tab', { name: /retrieve/i })
      .getAttribute('aria-selected'),
  ).toBe('true');
  expect(
    screen.getByRole('heading', { name: 'Find the signal.' }),
  ).toBeTruthy();
});
