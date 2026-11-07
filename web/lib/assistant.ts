export type AssistantProfile = { id: number; name: string };

export const OPEN_ASSISTANT_EVENT = 'scholargraph:open-assistant';

export function openAssistantForProfile(profile: AssistantProfile) {
  window.dispatchEvent(new CustomEvent(OPEN_ASSISTANT_EVENT, { detail: profile }));
}
