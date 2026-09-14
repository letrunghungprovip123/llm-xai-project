import type { PromptBuildResult, PromptMetrics } from "../../../../contracts/narrative";

export function buildPromptMetrics(prompt: PromptBuildResult): PromptMetrics {
  return {
    prompt_char_count: prompt.message_text.length,
    prompt_estimated_token_count: Math.ceil(prompt.message_text.length / 4),
    has_prediction_section: prompt.section_flags.has_prediction_section,
    has_evidence_section: prompt.section_flags.has_evidence_section,
    has_constraints_section: prompt.section_flags.has_constraints_section,
    has_output_schema_section: prompt.section_flags.has_output_schema_section,
    has_entropy_policy_section: prompt.section_flags.has_entropy_policy_section,
    has_concept_grouping_section:
      prompt.section_flags.has_concept_grouping_section,
    has_backend_skeleton_section:
      prompt.section_flags.has_backend_skeleton_section,
  };
}
