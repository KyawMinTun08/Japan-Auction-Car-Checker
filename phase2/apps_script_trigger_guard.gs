/**
 * JACC Phase 2 Apps Script trigger safety helper.
 *
 * STAGED ONLY. Add this file to the Apps Script project during the coordinated
 * Phase 2 rollout. These functions are manual editor/admin tools only; they are
 * intentionally not exposed through doGet(e) or doPost(e).
 *
 * The legacy monthlyPasswordReset() function rotates every active WEB member's
 * password and invalidates tokens. That conflicts with Phase 2 password
 * preservation and can unexpectedly lock members out. Phase 2 therefore
 * requires its time-driven trigger to be absent unless the owner deliberately
 * chooses to restore that policy later.
 */

var JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER = "monthlyPasswordReset";

function jaccPhase2TriggerHealth_() {
  var projectTriggers = ScriptApp.getProjectTriggers();
  var matches = [];

  for (var i = 0; i < projectTriggers.length; i++) {
    var trigger = projectTriggers[i];
    var handler = String(trigger.getHandlerFunction() || "");
    if (handler !== JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER) continue;

    matches.push({
      handler: handler,
      eventType: String(trigger.getEventType() || ""),
      triggerSource: String(trigger.getTriggerSource() || "")
    });
  }

  return {
    status: "ok",
    safe: matches.length === 0,
    monthlyPasswordResetTriggerCount: matches.length,
    monthlyPasswordResetEnabled: matches.length > 0,
    matches: matches
  };
}

/**
 * Manual one-time migration helper. Run from the Apps Script editor only after
 * reviewing jaccPhase2TriggerHealth_(). It deletes only triggers whose handler
 * function is exactly monthlyPasswordReset; every unrelated trigger remains.
 */
function jaccDisableMonthlyPasswordResetTriggers_() {
  var projectTriggers = ScriptApp.getProjectTriggers();
  var deleted = 0;

  for (var i = 0; i < projectTriggers.length; i++) {
    var trigger = projectTriggers[i];
    var handler = String(trigger.getHandlerFunction() || "");
    if (handler !== JACC_LEGACY_MONTHLY_PASSWORD_RESET_HANDLER) continue;

    ScriptApp.deleteTrigger(trigger);
    deleted++;
  }

  var health = jaccPhase2TriggerHealth_();
  return {
    status: health.safe ? "ok" : "error",
    deleted: deleted,
    safe: health.safe,
    monthlyPasswordResetTriggerCount: health.monthlyPasswordResetTriggerCount
  };
}
