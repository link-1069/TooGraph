export type CapabilitySelectionDiagnostic = {
  visible: boolean;
  selectionReason: string;
};

export function buildCapabilitySelectionDiagnostic(reasonValue: unknown): CapabilitySelectionDiagnostic {
  const selectionReason = textFromUnknown(reasonValue);
  return {
    visible: Boolean(selectionReason),
    selectionReason,
  };
}

export function listCapabilitySelectionReasonLabels(reasonValue: unknown) {
  const selectionReason = textFromUnknown(reasonValue);
  return selectionReason ? [`reason: ${selectionReason}`] : [];
}

function textFromUnknown(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
