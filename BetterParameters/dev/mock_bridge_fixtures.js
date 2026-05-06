(function () {
  // Mock fixtures are pinned to BACKEND_API contract version below.
  // Update this when contract examples change.
  var CONTRACT_VERSION = "2026-04-17";

  function parsePayload(payloadJson) {
    if (!payloadJson || typeof payloadJson !== "string") {
      return {};
    }
    try {
      return JSON.parse(payloadJson || "{}");
    } catch (_) {
      return {};
    }
  }

  function isIn(list, value) {
    return Array.isArray(list) && list.indexOf(value) >= 0;
  }

  function resolve(args) {
    var action = args && args.action;
    var payloadJson = args && args.payloadJson;
    var fixtureMode = String((args && args.fixtureMode) || "").trim().toLowerCase();
    var statePayload = (args && args.statePayload) || null;
    var actionMap = (args && args.actionMap) || {};
    var mutating = (args && args.mutatingActions) || [];
    var readOnly = (args && args.readOnlyOrValidationActions) || [];

    if (!actionMap || !action) {
      return null;
    }

    if (fixtureMode === "malformed_missing_state") {
      return { ok: true, message: "mock malformed" };
    }
    if (fixtureMode === "malformed_bad_api") {
      var badApiState = Object.assign({}, statePayload || {}, { apiVersion: 999 });
      return { ok: true, message: "", state: badApiState };
    }
    if (fixtureMode === "error_mutating" && isIn(mutating, action)) {
      return { ok: false, message: "Mock mutating failure: " + action, errorCode: "TRANSPORT_ERROR", state: null, traceback: "" };
    }
    if (fixtureMode === "error_readonly" && action === actionMap.GET_TEXT_TUNER_STATE) {
      return { ok: false, message: "Mock read-only failure: getTextTunerState", errorCode: "TRANSPORT_ERROR", state: null, traceback: "" };
    }
    if (fixtureMode === "error_validation" && isIn(readOnly, action) && action !== actionMap.GET_TEXT_TUNER_STATE) {
      return { ok: false, message: "Mock validation failure: " + action, errorCode: "VALIDATION_ERROR", state: null, traceback: "" };
    }
    if (
      fixtureMode === "error_metadata"
      && (action === actionMap.SYNC_METADATA_JSON_TO_FUSION || action === actionMap.SYNC_METADATA_FUSION_TO_JSON || action === actionMap.REPAIR_METADATA)
    ) {
      return { ok: false, message: "Mock metadata failure: " + action, errorCode: "TRANSPORT_ERROR", state: null, traceback: "" };
    }

    if (action === actionMap.GET_BACKEND_CONTRACT_INFO) {
      return {
        ok: true,
        message: "",
        state: null,
        contractVersion: CONTRACT_VERSION,
        bpmetaSchemaVersion: 1,
        metadataSchemaVersion: 2,
        actions: {
          readOnly: readOnly.slice(),
          mutating: mutating.slice()
        }
      };
    }

    if (action === actionMap.GET_PARAMETER_DEPENDENCY_GRAPH) {
      return { ok: true, message: "", state: null, nodes: [], edges: [] };
    }

    if (action === actionMap.RUN_SELF_TEST_SUITE) {
      return {
        ok: true,
        message: "",
        state: null,
        totalCount: 1,
        passedCount: 1,
        failedCount: 0,
        results: [{ name: "mock.smoke", passed: true, failures: [] }]
      };
    }

    if (action === actionMap.IMPORT_PARAMETERS) {
      var importPayload = parsePayload(payloadJson);
      var isDryRun = importPayload.dryRun === true;
      if (fixtureMode === "m4_import_cancel") {
        return { ok: false, message: "Import cancelled.", errorCode: "DIALOG_CANCELLED", state: null, importedCount: 0, skippedCount: 0, failedCount: 0, failedRows: [], filePath: "" };
      }
      if (isDryRun) {
        return {
          ok: true,
          message: "",
          state: null,
          dryRun: true,
          filePath: "C:\\mock\\BetterParameters-import.csv",
          importedCount: 2,
          skippedCount: 1,
          failedCount: 0,
          failedRows: []
        };
      }
      return {
        ok: true,
        message: "",
        state: statePayload,
        dryRun: false,
        importedCount: 2,
        skippedCount: 1,
        failedCount: 0,
        failedRows: []
      };
    }

    if (action === actionMap.BATCH_UPDATE_PARAMETERS) {
      var batchPayload = parsePayload(payloadJson);
      var updates = Array.isArray(batchPayload.updates) ? batchPayload.updates : [];
      if (fixtureMode === "m4_batch_all_fail") {
        return {
          ok: false,
          message: "Batch update failed.",
          errorCode: "VALIDATION_ERROR",
          state: null,
          updatedCount: 0,
          failedRows: updates.map(function (item) {
            return {
              name: String((item && (item.name || item.key)) || ""),
              message: "Mock batch failure."
            };
          })
        };
      }
      return {
        ok: true,
        message: "",
        state: statePayload,
        updatedCount: updates.length,
        failedRows: []
      };
    }

    if (action === actionMap.VALIDATE_PARAMETERS_PACKAGE_IMPORT) {
      if (fixtureMode === "m6_validate_cancel") {
        return { ok: false, message: "Import cancelled.", errorCode: "DIALOG_CANCELLED", state: null, preview: null, filePath: "" };
      }
      if (fixtureMode === "m6_validate_success_with_warnings") {
        return {
          ok: true,
          message: "",
          state: null,
          filePath: "C:\\mock\\BetterParameters-import.bpmeta.json",
          preview: {
            addCount: 2,
            updateCount: 3,
            skipCount: 1,
            potentialFailCount: 1,
            warnings: ["1 row may fail because expression validation is uncertain until apply."],
            failedRows: []
          }
        };
      }
      if (fixtureMode === "m6_validate_success_with_fail_rows") {
        return {
          ok: true,
          message: "",
          state: null,
          filePath: "C:\\mock\\BetterParameters-import.bpmeta.json",
          preview: {
            addCount: 1,
            updateCount: 2,
            skipCount: 0,
            potentialFailCount: 1,
            warnings: [],
            failedRows: [{ row: 4, name: "bad", message: "Expression is required to create a new parameter." }]
          }
        };
      }
      return {
        ok: true,
        message: "",
        state: null,
        filePath: "C:\\mock\\BetterParameters-import.bpmeta.json",
        preview: {
          addCount: 2,
          updateCount: 3,
          skipCount: 1,
          potentialFailCount: 0,
          warnings: [],
          failedRows: []
        }
      };
    }

    if (action === actionMap.EXPORT_PARAMETERS_PACKAGE) {
      if (fixtureMode === "m6_export_cancel") {
        return { ok: false, message: "Export cancelled.", errorCode: "DIALOG_CANCELLED", state: null, exportedCount: 0, filePath: "", format: "bpmeta.json" };
      }
      return {
        ok: true,
        message: "",
        state: null,
        exportedCount: Array.isArray(statePayload && statePayload.parameters) ? statePayload.parameters.length : 0,
        filePath: "C:\\mock\\BetterParameters-export.bpmeta.json",
        format: "bpmeta.json"
      };
    }

    if (action === actionMap.IMPORT_PARAMETERS_PACKAGE) {
      var reqPayload = parsePayload(payloadJson);
      var dryRun = reqPayload.dryRun === true;
      if (fixtureMode === "m6_import_cancel") {
        return { ok: false, message: "Import cancelled.", errorCode: "DIALOG_CANCELLED", state: null, importedCount: 0, updatedCount: 0, skippedCount: 0, failedCount: 0, failedRows: [], filePath: "" };
      }
      if (dryRun) {
        return {
          ok: true,
          message: "",
          state: null,
          dryRun: true,
          filePath: "C:\\mock\\BetterParameters-import.bpmeta.json",
          importedCount: 2,
          updatedCount: 3,
          skippedCount: 1,
          failedCount: 0,
          failedRows: []
        };
      }
      if (fixtureMode === "m6_import_all_fail") {
        return {
          ok: false,
          message: "No parameters were imported.",
          errorCode: "VALIDATION_ERROR",
          state: null,
          importedCount: 0,
          updatedCount: 0,
          skippedCount: 0,
          failedCount: 2,
          failedRows: [
            { row: 3, name: "badA", message: "Invalid expression." },
            { row: 4, name: "badB", message: "Name is required." }
          ]
        };
      }
      if (fixtureMode === "m6_import_partial_fail") {
        return {
          ok: true,
          message: "",
          state: statePayload,
          dryRun: false,
          importedCount: 2,
          updatedCount: 1,
          skippedCount: 0,
          failedCount: 1,
          failedRows: [{ row: 5, name: "bad", message: "Invalid expression." }]
        };
      }
      if (fixtureMode === "m6_import_all_skipped") {
        return {
          ok: true,
          message: "",
          state: statePayload,
          dryRun: false,
          importedCount: 0,
          updatedCount: 0,
          skippedCount: 3,
          failedCount: 0,
          failedRows: []
        };
      }
      return {
        ok: true,
        message: "",
        state: statePayload,
        dryRun: false,
        importedCount: 2,
        updatedCount: 3,
        skippedCount: 1,
        failedCount: 0,
        failedRows: []
      };
    }

    if (action === actionMap.GET_TEXT_TUNER_STATE) {
      return { ok: true, message: "", state: null, values: (statePayload && statePayload.textTunerState) || {} };
    }

    if (action === actionMap.EXPORT_PARAMETERS) {
      if (fixtureMode === "m4_export_cancel") {
        return { ok: false, message: "Export cancelled.", errorCode: "DIALOG_CANCELLED", state: null, exportedCount: 0, filePath: "" };
      }
      return {
        ok: true,
        message: "",
        state: null,
        exportedCount: Array.isArray(statePayload && statePayload.parameters) ? statePayload.parameters.length : 0,
        filePath: "C:\\mock\\BetterParameters-export.csv"
      };
    }

    if (action === actionMap.OPEN_HELP_URL) {
      return { ok: true, message: "", state: null };
    }

    if (action === actionMap.PREVIEW_EXPRESSION) {
      return { ok: true, message: "", state: null, preview: "0 mm" };
    }

    if (action === actionMap.VALIDATE_EXPRESSION || action === actionMap.VALIDATE_PARAMETER_NAME || action === actionMap.VALIDATE_UNIT) {
      return { ok: true, message: "", state: null };
    }

    return null;
  }

  window.__BP_MOCK_FIXTURE_HELPER = {
    CONTRACT_VERSION: CONTRACT_VERSION,
    resolve: resolve
  };
})();
