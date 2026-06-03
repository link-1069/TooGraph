import type { StateFieldType } from "../workspace/statePanelFields.ts";
import {
  isInputBoundaryConfigType,
  normalizeInputBoundaryConfigType,
  resolveInputBoundarySelection,
  type InputBoundarySelection,
} from "../../lib/input-boundary.ts";
import type { InputBoundaryConfigType } from "../../types/node-system.ts";
import { createDefaultLocalFolderInputValue } from "./localFolderInputModel.ts";

export type InputBoundaryType = InputBoundaryConfigType | "folder";
export type { InputBoundarySelection };

export function resolveStateTypeForInputBoundary(type: InputBoundaryType): StateFieldType {
  if (type === "folder") {
    return "file";
  }
  return type;
}

export function resolveNextInputValueForBoundaryType(input: {
  nextType: Extract<InputBoundaryType, "text" | "file" | "folder">;
  currentType: string | null;
  currentValue: unknown;
}) {
  if (input.nextType === "file") {
    return "";
  }

  if (input.nextType === "folder") {
    return createDefaultLocalFolderInputValue();
  }

  if (isUploadedAssetBoundaryType(input.currentType)) {
    return "";
  }

  return typeof input.currentValue === "string" ? input.currentValue : "";
}

export function isSwitchableInputBoundaryType(type: string): type is Extract<InputBoundaryType, "text" | "file" | "folder"> {
  return type === "text" || type === "file" || type === "folder";
}

export { isInputBoundaryConfigType, normalizeInputBoundaryConfigType, resolveInputBoundarySelection };

function isUploadedAssetBoundaryType(type: string | null) {
  return type === "file" || type === "folder" || type === "image" || type === "audio" || type === "video";
}
