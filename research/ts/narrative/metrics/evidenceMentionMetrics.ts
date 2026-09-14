import type {
  EvidenceItem,
  EvidenceMentionMetrics,
  EvidencePackage,
  ExplanationOutput,
} from "../../../../contracts/narrative";
import { normalizeText } from "../../common/utils";

export function buildEvidenceMentionMetrics(
  packageItem: EvidencePackage,
  output: ExplanationOutput | null,
): EvidenceMentionMetrics {
  const selectedEvidence = packageItem.prompt_payload.selected_evidence || [];
  const allowedFeatureIds = new Set(
    packageItem.prompt_payload.constraints.allowed_feature_ids || [],
  );
  const allowedConceptIds = new Set(
    packageItem.prompt_payload.constraints.allowed_concept_ids || [],
  );

  if (!output) {
    return emptyMetrics(selectedEvidence.length, allowedConceptIds.size);
  }

  const outputText = normalizeText(collectOutputText(output));
  const mentionedFeatures = selectedEvidence.filter((item) => {
    return isEvidenceItemMentioned(item, output, outputText);
  });

  const exposedConceptIds = collectExposedConceptIds(packageItem);
  const mentionedConceptIds = exposedConceptIds.filter((conceptId) => {
    return isConceptMentioned(conceptId, packageItem, output, outputText);
  });

  const declaredFeatureIds = uniqueStrings(
    output.factors.flatMap((factor) => factor.declared_feature_ids),
  );
  const declaredConceptIds = uniqueStrings(
    output.factors.flatMap((factor) => factor.declared_concept_ids),
  );

  const validDeclaredFeatures = declaredFeatureIds.filter((id) =>
    allowedFeatureIds.has(id),
  );
  const validDeclaredConcepts = declaredConceptIds.filter((id) =>
    allowedConceptIds.has(id),
  );

  return {
    selected_feature_count: selectedEvidence.length,
    selected_feature_mention_count: mentionedFeatures.length,
    selected_feature_mention_rate:
      selectedEvidence.length > 0
        ? mentionedFeatures.length / selectedEvidence.length
        : null,
    top1_mention_rate: calculateTopRate(selectedEvidence, mentionedFeatures, 1),
    top3_mention_rate: calculateTopRate(selectedEvidence, mentionedFeatures, 3),
    top5_mention_rate: calculateTopRate(selectedEvidence, mentionedFeatures, 5),
    exposed_concept_count: exposedConceptIds.length,
    concept_mention_count: mentionedConceptIds.length,
    concept_mention_rate:
      exposedConceptIds.length > 0
        ? mentionedConceptIds.length / exposedConceptIds.length
        : null,
    declared_feature_count: declaredFeatureIds.length,
    valid_declared_feature_count: validDeclaredFeatures.length,
    invalid_declared_feature_count:
      declaredFeatureIds.length - validDeclaredFeatures.length,
    declared_concept_count: declaredConceptIds.length,
    valid_declared_concept_count: validDeclaredConcepts.length,
    invalid_declared_concept_count:
      declaredConceptIds.length - validDeclaredConcepts.length,
  };
}

function emptyMetrics(
  selectedFeatureCount: number,
  exposedConceptCount: number,
): EvidenceMentionMetrics {
  return {
    selected_feature_count: selectedFeatureCount,
    selected_feature_mention_count: 0,
    selected_feature_mention_rate: selectedFeatureCount > 0 ? 0 : null,
    top1_mention_rate: selectedFeatureCount > 0 ? 0 : null,
    top3_mention_rate: selectedFeatureCount > 0 ? 0 : null,
    top5_mention_rate: selectedFeatureCount > 0 ? 0 : null,
    exposed_concept_count: exposedConceptCount,
    concept_mention_count: 0,
    concept_mention_rate: exposedConceptCount > 0 ? 0 : null,
    declared_feature_count: 0,
    valid_declared_feature_count: 0,
    invalid_declared_feature_count: 0,
    declared_concept_count: 0,
    valid_declared_concept_count: 0,
    invalid_declared_concept_count: 0,
  };
}

function collectOutputText(output: ExplanationOutput): string {
  return [
    output.prediction_summary,
    ...output.factors.map(
      (factor) => `${factor.factor_name} ${factor.explanation}`,
    ),
    output.uncertainty_note,
    output.distributed_evidence_note,
    output.safe_summary,
  ].join(" ");
}

function isEvidenceItemMentioned(
  item: EvidenceItem,
  output: ExplanationOutput,
  normalizedOutputText: string,
): boolean {
  const featureId = item.feature_id || "";

  const declared = output.factors.some((factor) => {
    return factor.declared_feature_ids.includes(featureId);
  });

  if (declared) {
    return true;
  }

  const aliases = [
    item.feature_id,
    item.feature_name,
    item.display_name,
  ].filter((value): value is string => Boolean(value && value.trim()));

  return aliases.some((alias) => {
    const normalizedAlias = normalizeText(alias);
    return (
      normalizedAlias.length >= 3 &&
      normalizedOutputText.includes(normalizedAlias)
    );
  });
}

function collectExposedConceptIds(packageItem: EvidencePackage): string[] {
  const ids = new Set<string>();

  for (const item of packageItem.prompt_payload.selected_evidence) {
    if (item.concept) {
      ids.add(item.concept);
    }
  }

  for (const item of packageItem.prompt_payload.concept_evidence) {
    if (item.concept) {
      ids.add(item.concept);
    }
  }

  return [...ids];
}

function isConceptMentioned(
  conceptId: string,
  packageItem: EvidencePackage,
  output: ExplanationOutput,
  normalizedOutputText: string,
): boolean {
  const declared = output.factors.some((factor) => {
    return factor.declared_concept_ids.includes(conceptId);
  });

  if (declared) {
    return true;
  }

  const aliases = new Set<string>([conceptId]);

  for (const item of packageItem.prompt_payload.selected_evidence) {
    if (item.concept === conceptId && item.concept_display_name) {
      aliases.add(item.concept_display_name);
    }
  }

  for (const item of packageItem.prompt_payload.concept_evidence) {
    if (item.concept === conceptId && item.concept_display_name) {
      aliases.add(item.concept_display_name);
    }
  }

  return [...aliases].some((alias) => {
    const normalizedAlias = normalizeText(alias);
    return (
      normalizedAlias.length >= 3 &&
      normalizedOutputText.includes(normalizedAlias)
    );
  });
}

function calculateTopRate(
  selectedEvidence: EvidenceItem[],
  mentionedEvidence: EvidenceItem[],
  topK: number,
): number | null {
  if (selectedEvidence.length === 0) {
    return null;
  }

  const topItems = selectedEvidence.slice(
    0,
    Math.min(topK, selectedEvidence.length),
  );
  const mentionedIds = new Set(
    mentionedEvidence.map((item) => item.feature_id),
  );
  const count = topItems.filter((item) =>
    mentionedIds.has(item.feature_id),
  ).length;

  return topItems.length > 0 ? count / topItems.length : null;
}

function uniqueStrings(values: string[]): string[] {
  return [
    ...new Set(
      values.filter((value) => typeof value === "string" && value.length > 0),
    ),
  ];
}
