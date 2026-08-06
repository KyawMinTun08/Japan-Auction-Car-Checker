/**
 * JACC Phase 2 Apps Script route adapter.
 *
 * Add this as a separate .gs file together with the membership security,
 * payment approval, and device-binding modules. It keeps the deployed doPost
 * edit small and makes protected Phase 2 routes impossible to reach before the
 * server-key/schema preflight.
 */

function jaccPhase2Handled_(response) {
  return {handled: true, response: response};
}

function jaccPhase2NotHandled_() {
  return {handled: false, response: null};
}

function jaccPhase2PreflightAndRoute_(data) {
  var guard = jaccMembershipPreflight_(data);
  if (guard) return jaccPhase2Handled_(guard);

  var action = String((data && data.action) || "").trim();
  switch (action) {
    case "approveMembershipPayment":
      return jaccPhase2Handled_(jaccApproveMembershipPayment_(data));

    case "resetMemberDevice":
      return jaccPhase2Handled_(jaccResetMemberDevice_(data));

    default:
      return jaccPhase2NotHandled_();
  }
}

/**
 * REQUIRED doPost integration immediately after parsing request data and
 * before handlePhase3PaymentAction_(data):
 *
 *   var data = JSON.parse(e.postData.contents);
 *   var phase2 = jaccPhase2PreflightAndRoute_(data);
 *   if (phase2.handled) return _json(phase2.response);
 *
 * Existing legacy switch/cases remain below those lines unchanged.
 *
 * Keep the current production doGet(e) unchanged. It is the public price-data
 * endpoint. The Railway compatibility proxy converts the one historical GET
 * getMembers caller into authenticated POST JSON before network access.
 *
 * Do not send JACC_SERVER_KEY from browser, PWA, or Flutter code and do not put
 * it in URL query parameters.
 */
