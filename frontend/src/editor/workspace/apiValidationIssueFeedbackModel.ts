import { ApiHttpError, type ApiValidationIssue } from "../../api/http.ts";

type Translate = (key: string, params?: Record<string, unknown>) => string;

const API_VALIDATION_ISSUE_LIMIT = 5;

export function hasApiValidationIssues(error: unknown): error is ApiHttpError {
  return error instanceof ApiHttpError && error.validationIssues.length > 0;
}

export function formatApiValidationErrorDetail(error: unknown, fallbackMessage: string, translate: Translate): string {
  if (hasApiValidationIssues(error)) {
    const displayedIssues = error.validationIssues.slice(0, API_VALIDATION_ISSUE_LIMIT);
    const issueMessages = displayedIssues
      .map((issue) => formatApiValidationIssue(issue, translate))
      .filter(Boolean);
    const remainingCount = error.validationIssues.length - displayedIssues.length;
    if (remainingCount > 0) {
      issueMessages.push(
        translate("editor.validationIssueRemainingCount", {
          count: remainingCount,
        }),
      );
    }

    const validationMessage = issueMessages.join("; ");
    if (validationMessage) {
      return validationMessage;
    }
  }

  return error instanceof Error && error.message ? error.message : fallbackMessage;
}

function formatApiValidationIssue(issue: ApiValidationIssue, translate: Translate): string {
  if (issue.code === "input_node_write_count_invalid") {
    return translate("editor.validationInputNodeWriteCountInvalid", {
      node: extractNodeIdFromIssue(issue),
      path: issue.path ?? "",
    });
  }

  if (issue.code === "condition_rule_value_type_mismatch") {
    const details = extractConditionRuleValueDetails(issue);
    return translate("editor.validationConditionRuleValueTypeMismatch", {
      node: details.node,
      stateType: localizeStateType(details.stateType, translate),
      state: details.state,
      reason: localizeConditionRuleReason(details.reason, translate),
      path: issue.path ?? "",
    });
  }

  const message = issue.message || issue.code;
  if (!message) {
    return "";
  }
  if (issue.path) {
    return translate("editor.validationIssueWithPath", {
      message,
      path: issue.path,
    });
  }
  return message;
}

function extractNodeIdFromIssue(issue: ApiValidationIssue): string {
  const pathMatch = issue.path?.match(/^nodes\.([^.]+)\./);
  if (pathMatch?.[1]) {
    return pathMatch[1];
  }

  const messageMatch = issue.message.match(/(?:Input|Condition) node '([^']+)'/);
  return messageMatch?.[1] ?? "";
}

function extractConditionRuleValueDetails(issue: ApiValidationIssue) {
  const messageMatch = issue.message.match(
    /^Condition node '([^']+)' has an invalid value for ([^ ]+) state '([^']+)':\s*(.+)$/,
  );

  return {
    node: extractNodeIdFromIssue(issue) || messageMatch?.[1] || "",
    stateType: messageMatch?.[2] ?? "",
    state: messageMatch?.[3] ?? "",
    reason: trimTrailingPeriod(messageMatch?.[4] ?? issue.message),
  };
}

function localizeStateType(stateType: string, translate: Translate): string {
  if (stateType === "boolean") {
    return translate("editor.validationStateTypeBoolean");
  }
  if (stateType === "number") {
    return translate("editor.validationStateTypeNumber");
  }
  return stateType;
}

function localizeConditionRuleReason(reason: string, translate: Translate): string {
  if (reason === "Boolean condition value must be true or false") {
    return translate("editor.validationConditionBooleanValueInvalid");
  }
  if (reason === "Number condition value must be a finite number") {
    return translate("editor.validationConditionNumberValueInvalid");
  }
  return reason;
}

function trimTrailingPeriod(value: string): string {
  return value.trim().replace(/\.$/, "");
}
