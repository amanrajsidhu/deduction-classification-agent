"""Build the V2 n8n workflow deterministically from the committed V1 export."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workflows" / "MVP_VERSION_-_V1_-_DEDUCTION_CLASSIFICATION_(CSV_MATCH-CLASSIFY-VERIFY_XLSX).json"
DESTINATION = ROOT / "workflows" / "DEDUCTION_RESOLUTION_WORKBENCH_V2.json"

NORMALISE_SETTLEMENT = r"""const RULESET_VERSION = '2.0.0';
const ID_FIELD = 'deduction_id';
const DATE_FIELD = 'transaction_date';
const STOP_ON_IDENTIFIER_ERROR = false;
const REQUIRE_POSITIVE_AMOUNT = false;
function normaliseVendor(name) {
  return String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/\s+/g, ' ').trim();
}
function canonicalVendor(name) {
  const normal = normaliseVendor(name); const tokens = new Set(normal.split(' ').filter(Boolean));
  if (tokens.has('amazon') || tokens.has('amzn') || tokens.has('mktp')) return 'amazon';
  if (tokens.has('walmart')) return 'walmart';
  if (tokens.has('target')) return 'target';
  if (tokens.has('costco')) return 'costco';
  if (tokens.has('shopify')) return 'shopify direct';
  return normal;
}
function validUtcDate(year, month, day) {
  if (![year, month, day].every(Number.isInteger)) return null;
  const d = new Date(Date.UTC(year, month - 1, day));
  if (!Number.isFinite(d.getTime())) return null;
  if (d.getUTCFullYear() !== year || d.getUTCMonth() !== month - 1 || d.getUTCDate() !== day) return null;
  return d.toISOString().slice(0, 10);
}
function parseDateValue(raw) {
  const str = String(raw || '').trim();
  if (/^\d{5}$/.test(str)) { const serial = Number(str); const d = new Date(Date.UTC(1899, 11, 30) + serial * 86400000); if (Number.isFinite(d.getTime())) return { iso: d.toISOString().slice(0, 10), method: 'excel_serial', matchable: true, error: null }; }
  let m = str.match(/^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})$/);
  if (m) { const iso = validUtcDate(Number(m[1]), Number(m[2]), Number(m[3])); return iso ? { iso, method: 'iso', matchable: true, error: null } : { iso: null, method: 'invalid_calendar_date', matchable: false, error: 'invalid_calendar_date' }; }
  m = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (m) { const a = Number(m[1]), b = Number(m[2]), year = Number(m[3]); let iso = null, method = null; if (a > 12 && b <= 12) { iso = validUtcDate(year, b, a); method = 'slash_unambiguous_dmy'; } else if (b > 12 && a <= 12) { iso = validUtcDate(year, a, b); method = 'slash_unambiguous_mdy'; } else if (a <= 12 && b <= 12) return { iso: null, method: 'ambiguous_slash_date', matchable: false, error: 'ambiguous_slash_date' }; return iso ? { iso, method, matchable: true, error: null } : { iso: null, method: 'invalid_calendar_date', matchable: false, error: 'invalid_calendar_date' }; }
  return { iso: null, method: 'unparseable', matchable: false, error: 'unparseable_date' };
}
function parseAmountValue(raw) {
  const str = String(raw ?? '').trim();
  if (!/^[+-]?(?:\d+(?:\.\d{1,2})?|\.\d{1,2})$/.test(str)) return { value: null, error: 'invalid_amount' };
  const value = Number(str), cents = Math.round(Math.abs(value) * 100);
  if (!Number.isFinite(value) || !Number.isSafeInteger(cents) || cents <= 0 || (REQUIRE_POSITIVE_AMOUNT && value <= 0)) return { value: null, error: 'invalid_amount' };
  return { value, error: null };
}
function fnv1a(str) { let hash = 2166136261; for (let i = 0; i < str.length; i++) { hash ^= str.charCodeAt(i); hash = Math.imul(hash, 16777619); } return (hash >>> 0).toString(16); }
const sourceItems = $input.all();
const idCounts = new Map();
for (const item of sourceItems) { const id = String(item.json[ID_FIELD] ?? '').trim(); if (id) idCounts.set(id, (idCounts.get(id) || 0) + 1); }
const identifierProblems = sourceItems.filter(item => { const id = String(item.json[ID_FIELD] ?? '').trim(); return !id || idCounts.get(id) !== 1; });
if (STOP_ON_IDENTIFIER_ERROR && identifierProblems.length) throw new Error('Input stopped: every ' + ID_FIELD + ' must be present and unique.');
return sourceItems.map(item => {
  const j = item.json, identifier = String(j[ID_FIELD] ?? '').trim(), identifierValid = !!identifier && idCounts.get(identifier) === 1;
  const dateInfo = parseDateValue(j[DATE_FIELD]), amountInfo = parseAmountValue(j.amount), rawVendor = normaliseVendor(j.vendor_name), vendor = canonicalVendor(j.vendor_name);
  const valid = identifierValid && dateInfo.matchable && amountInfo.error === null && !!vendor;
  const error = !identifierValid ? 'missing_or_duplicate_' + ID_FIELD : (dateInfo.error || amountInfo.error || (!vendor ? 'invalid_vendor' : null));
  return { json: { ...j, [ID_FIELD]: identifier || j[ID_FIELD], amount: amountInfo.value, _raw_normalised_vendor: rawVendor, _normalised_vendor: vendor, _normalised_date: dateInfo.iso, _date_parse_method: dateInfo.method, matchable: valid, error: valid ? null : error, _match_key: valid ? fnv1a(dateInfo.iso + '|' + amountInfo.value.toFixed(2) + '|' + vendor) : null, _ruleset_version: RULESET_VERSION } };
});"""

NORMALISE_ACCRUAL = (
    NORMALISE_SETTLEMENT
    .replace("const ID_FIELD = 'deduction_id';", "const ID_FIELD = 'accrual_id';", 1)
    .replace("const DATE_FIELD = 'transaction_date';", "const DATE_FIELD = 'accrual_date';", 1)
    .replace("const STOP_ON_IDENTIFIER_ERROR = false;", "const STOP_ON_IDENTIFIER_ERROR = true;", 1)
    .replace("const REQUIRE_POSITIVE_AMOUNT = false;", "const REQUIRE_POSITIVE_AMOUNT = true;", 1)
)

DETERMINISTIC_MATCH = r"""const RULESET_VERSION = '2.0.0';
function vendorScore(a, b) { if (!a || !b) return 0; if (a === b) return 100; if (a.includes(b) || b.includes(a)) return 90; const aa = a.split(' ').filter(Boolean), bb = b.split(' ').filter(Boolean), setB = new Set(bb); const overlap = aa.filter(t => setB.has(t) && t.length >= 3); if (!overlap.length) return 0; return overlap.length >= Math.min(aa.length, bb.length) ? 70 : 60; }
function daysBetween(a, b) { const left = Date.parse(String(a || '') + 'T00:00:00Z'), right = Date.parse(String(b || '') + 'T00:00:00Z'); if (!Number.isFinite(left) || !Number.isFinite(right)) return null; return Math.round(Math.abs(left - right) / 86400000); }
function cents(n) { return Math.round(Math.abs(Number(n)) * 100); }
const all = $input.all();
const settlements = all.filter(i => i.json.deduction_id !== undefined).map(i => ({ ...i.json }));
const accruals = all.filter(i => i.json.accrual_id !== undefined).map(i => ({ ...i.json, _consumed: false }));
const candidates = [];
for (const s of settlements) {
  if (!s.matchable) continue;
  for (const a of accruals) {
    if (!a.matchable || a.evidence_scope !== 'transaction_match') continue;
    const amountDeltaCents = Math.abs(cents(s.amount) - cents(a.amount)); if (amountDeltaCents > 1) continue;
    const dateDelta = daysBetween(s._normalised_date, a._normalised_date); if (!Number.isFinite(dateDelta) || dateDelta > 1) continue;
    const vScore = vendorScore(s._normalised_vendor, a._normalised_vendor); if (vScore < 60) continue;
    candidates.push({ deduction_id: s.deduction_id, accrual_id: a.accrual_id, vScore, dateDelta, amountDeltaCents });
  }
}
candidates.sort((a, b) => b.vScore - a.vScore || a.dateDelta - b.dateDelta || a.amountDeltaCents - b.amountDeltaCents || a.deduction_id.localeCompare(b.deduction_id) || a.accrual_id.localeCompare(b.accrual_id));
const settlementById = new Map(settlements.map(s => [s.deduction_id, s])); const accrualById = new Map(accruals.map(a => [a.accrual_id, a])); const used = new Set();
for (const c of candidates) { const a = accrualById.get(c.accrual_id); if (used.has(c.deduction_id) || a._consumed) continue; a._consumed = true; used.add(c.deduction_id); settlementById.get(c.deduction_id)._match_result = { matched_accrual_id: a.accrual_id, matched_bucket: a.bucket, vendor_score: c.vScore, date_delta_days: c.dateDelta, match_reason: 'Amount within £0.01, date within ' + c.dateDelta + ' day(s), canonical vendor score ' + c.vScore + '; ruleset ' + RULESET_VERSION }; }
const results = [];
for (const s of settlements) { if (!s.matchable) results.push({ json: { ...s, _record_type: 'settlement', _route: 'data_quality_issue', matched: false } }); else if (s._match_result) { const match = s._match_result; delete s._match_result; results.push({ json: { ...s, _record_type: 'settlement', _route: 'auto_matched', matched: true, ...match } }); } else results.push({ json: { ...s, _record_type: 'settlement', _route: 'needs_classification', matched: false } }); }
for (const a of accruals) results.push({ json: { ...a, _record_type: 'accrual' } });
return results;"""

VERIFY_EVIDENCE = r"""const RULESET_VERSION = '2.0.0';
function vendorScore(a, b) { if (!a || !b) return 0; if (a === b) return 100; if (a.includes(b) || b.includes(a)) return 90; const aa = a.split(' ').filter(Boolean), bb = b.split(' ').filter(Boolean), setB = new Set(bb); const overlap = aa.filter(t => setB.has(t) && t.length >= 3); if (!overlap.length) return 0; return overlap.length >= Math.min(aa.length, bb.length) ? 70 : 60; }
function daysBetween(a, b) { const left = Date.parse(String(a || '') + 'T00:00:00Z'), right = Date.parse(String(b || '') + 'T00:00:00Z'); if (!Number.isFinite(left) || !Number.isFinite(right)) return null; return Math.round(Math.abs(left - right) / 86400000); }
function cents(n) { return Math.round(Math.abs(Number(n)) * 100); }
const allAccruals = $('Code (Deterministic Match: one-to-one)').all().map(i => i.json).filter(j => j._record_type === 'accrual' && j.matchable);
const accrualIds = allAccruals.map(a => String(a.accrual_id || '').trim()); if (accrualIds.some(id => !id) || new Set(accrualIds).size !== accrualIds.length) throw new Error('Evidence allocation stopped: accrual_id values must be present and unique.');
const pools = allAccruals.filter(a => a.evidence_scope === 'programme_pool' && !a._consumed).map(a => ({ ...a, _available_cents: cents(a.amount) }));
const input = $input.all().map(i => i.json); const ordered = [...input].sort((a, b) => cents(b.amount) - cents(a.amount) || String(a.deduction_id).localeCompare(String(b.deduction_id))); const routed = new Map();
for (const j of ordered) {
  if (j._route === 'needs_review') { routed.set(j.deduction_id, j); continue; }
  const amount = cents(j.amount);
  if (j.llm_bucket === 'Unresolvable') {
    const exact = allAccruals.find(a => { const delta = daysBetween(j._normalised_date, a._normalised_date); return cents(a.amount) === amount && Number.isFinite(delta) && delta <= 1 && vendorScore(j._normalised_vendor, a._normalised_vendor) >= 60; });
    if (exact) routed.set(j.deduction_id, { ...j, _route: 'needs_review', _evidence_agrees: false, _evidence_note: 'AI proposed Unresolvable, but same-vendor exact-amount near-date candidate ' + exact.accrual_id + ' exists; human review required.' });
    else routed.set(j.deduction_id, { ...j, _route: 'unresolvable', _evidence_agrees: true, _evidence_note: 'No same-vendor exact-amount near-date candidate exists in the supplied ledger.' });
    continue;
  }
  const candidates = pools.filter(a => { const delta = daysBetween(j._normalised_date, a._normalised_date); return a.bucket === j.llm_bucket && a._available_cents >= amount && vendorScore(j._normalised_vendor, a._normalised_vendor) >= 60 && Number.isFinite(delta) && delta <= 45; }).sort((a, b) => vendorScore(j._normalised_vendor, b._normalised_vendor) - vendorScore(j._normalised_vendor, a._normalised_vendor) || daysBetween(j._normalised_date, a._normalised_date) - daysBetween(j._normalised_date, b._normalised_date) || a.accrual_id.localeCompare(b.accrual_id));
  if (!candidates.length) { routed.set(j.deduction_id, { ...j, _route: 'needs_review', _evidence_agrees: false, _evidence_note: 'No same-vendor programme balance can support the proposed bucket and amount.' }); continue; }
  const evidence = candidates[0], before = evidence._available_cents; evidence._available_cents -= amount;
  routed.set(j.deduction_id, { ...j, _route: 'classified_verified', _evidence_agrees: true, _evidence_accrual_id: evidence.accrual_id, _allocated_amount: amount / 100, _evidence_balance_before: before / 100, _evidence_balance_after: evidence._available_cents / 100, _evidence_note: 'Allocated £' + (amount / 100).toFixed(2) + ' against programme balance ' + evidence.accrual_id + '; £' + (evidence._available_cents / 100).toFixed(2) + ' remains; ruleset ' + RULESET_VERSION + '.' });
}
return input.map(j => ({ json: routed.get(j.deduction_id) }));"""

COMPLETE_BRANCH_EXPORT = r"""const deterministic = $('Code (Deterministic Match: one-to-one)').all().map(i => i.json);
const verified = $input.all().map(i => i.json);
const branches = {
  'auto_matched.json': deterministic.filter(j => j._record_type === 'settlement' && j._route === 'auto_matched'),
  'data_quality_issues.json': deterministic.filter(j => j._record_type === 'settlement' && j._route === 'data_quality_issue'),
  'classified_verified.json': verified.filter(j => j._route === 'classified_verified'),
  'needs_review.json': verified.filter(j => j._route === 'needs_review'),
  'unresolvable.json': verified.filter(j => j._route === 'unresolvable')
};
return Object.entries(branches).map(([fileName, rows]) => ({
  json: { fileName, record_count: rows.length },
  binary: {
    data: {
      data: Buffer.from(JSON.stringify(rows, null, 2) + '\n', 'utf8').toString('base64'),
      mimeType: 'application/json',
      fileName
    }
  }
}));"""


def node_by_name(workflow, name):
    return next(node for node in workflow["nodes"] if node["name"] == name)


def strengthen_classification_controls(workflow):
    """Keep controlled finance aliases deterministic and leave only judgement to AI."""
    prompt_node = node_by_name(workflow, "Code (Build Classification Prompt)")
    prompt_code = prompt_node["parameters"]["jsCode"]
    prompt_marker = "\\n\\nCall the submit_classifications tool exactly once with your results."
    alias_guidance = (
        "\\n\\nThe finance team's configured reference aliases are authoritative for this demo: "
        "PROMO, MKTG-REBATE and TRADE-PROMO = Promotional Accrual; "
        "SHORT, QTY-SHORT and MISSING-UNITS = Shortage Claim; "
        "PRC-DISP, PRICE-ADJ and PPD = Price Dispute; "
        "DMG-CLAIM, DAMAGED-RMA and WHSE-DMG = Damaged Goods; "
        "CHB, MISC-ADJ and OTHER-DEDUCT = Chargeback/Other. "
        "These are disclosed configuration, not an AI inference."
    )
    if prompt_marker not in prompt_code:
        raise ValueError("Classification prompt marker was not found")
    prompt_node["parameters"]["jsCode"] = prompt_code.replace(
        prompt_marker, alias_guidance + prompt_marker, 1,
    )

    parse_node = node_by_name(workflow, "Code (Parse Classification Response)")
    parse_code = parse_node["parameters"]["jsCode"]
    parse_code = parse_code.replace(
        "  const callId = response.id || null;",
        "  const batchIds = originalItems.map(row => String(row.deduction_id || '')).filter(Boolean);\n"
        "  const batchRef = batchIds.length ? "
        "'batch:' + batchIds[0] + ':' + batchIds[batchIds.length - 1] + ':' + batchIds.length : null;",
        1,
    ).replace("_llm_call_id: callId", "_llm_batch_ref: batchRef")
    if "response.id" in parse_code or "_llm_call_id" in parse_code:
        raise ValueError("Provider response identifiers were not removed from the public workflow")
    valid_marker = "const validBuckets = new Set(['Promotional Accrual','Shortage Claim','Price Dispute','Damaged Goods','Chargeback/Other','Unresolvable']);\n"
    alias_function = r"""function configuredBucket(referenceCode) {
  const ref = String(referenceCode || '').trim().toUpperCase();
  const aliases = [
    [/^(PROMO-|MKTG-REBATE-|TRADE-PROMO-)/, 'Promotional Accrual'],
    [/^(SHORT-|QTY-SHORT-|MISSING-UNITS-)/, 'Shortage Claim'],
    [/^(PRC-DISP-|PRICE-ADJ-|PPD-)/, 'Price Dispute'],
    [/^(DMG-CLAIM-|DAMAGED-RMA-|WHSE-DMG-)/, 'Damaged Goods'],
    [/^(CHB-|MISC-ADJ-|OTHER-DEDUCT-)/, 'Chargeback/Other']
  ];
  const match = aliases.find(([pattern]) => pattern.test(ref));
  return match ? match[1] : null;
}
"""
    if valid_marker not in parse_code:
        raise ValueError("Classification parser bucket marker was not found")
    parse_code = parse_code.replace(valid_marker, valid_marker + alias_function, 1)
    old_block = """    const p = byId.get(orig.deduction_id);
    if (!p || !validBuckets.has(p.bucket)) {
      results.push({ json: { ...orig, _record_type: 'settlement', _route: 'needs_review', _classification_error: 'missing or invalid bucket for this line', _llm_batch_ref: batchRef, input_tokens: usage.input_tokens, output_tokens: usage.output_tokens, cache_creation_input_tokens: usage.cache_creation_input_tokens, cache_read_input_tokens: usage.cache_read_input_tokens } });
    } else {
      results.push({ json: { ...orig, _record_type: 'settlement', _route: 'pending_verification', llm_bucket: p.bucket, llm_confidence: p.confidence, llm_reasoning: p.reasoning, _classification_error: null, _llm_batch_ref: batchRef, input_tokens: usage.input_tokens, output_tokens: usage.output_tokens, cache_creation_input_tokens: usage.cache_creation_input_tokens, cache_read_input_tokens: usage.cache_read_input_tokens } });
    }
"""
    new_block = """    const p = byId.get(orig.deduction_id);
    const aliasBucket = configuredBucket(orig.reference_code);
    const proposed = aliasBucket ? { bucket: aliasBucket, confidence: 1, reasoning: 'Configured reference alias: ' + orig.reference_code } : p;
    if (!proposed || !validBuckets.has(proposed.bucket)) {
      results.push({ json: { ...orig, _record_type: 'settlement', _route: 'needs_review', _classification_error: 'missing or invalid bucket for this line', _llm_batch_ref: batchRef, input_tokens: usage.input_tokens, output_tokens: usage.output_tokens, cache_creation_input_tokens: usage.cache_creation_input_tokens, cache_read_input_tokens: usage.cache_read_input_tokens } });
    } else {
      results.push({ json: { ...orig, _record_type: 'settlement', _route: 'pending_verification', llm_bucket: proposed.bucket, llm_confidence: proposed.confidence, llm_reasoning: proposed.reasoning, _classification_method: aliasBucket ? 'configured_alias' : 'ai_proposal', _classification_error: null, _llm_batch_ref: batchRef, input_tokens: usage.input_tokens, output_tokens: usage.output_tokens, cache_creation_input_tokens: usage.cache_creation_input_tokens, cache_read_input_tokens: usage.cache_read_input_tokens } });
    }
"""
    if old_block not in parse_code:
        raise ValueError("Classification parser routing block was not found")
    parse_node["parameters"]["jsCode"] = parse_code.replace(old_block, new_block, 1)


def main() -> int:
    workflow = json.loads(SOURCE.read_text(encoding="utf-8"))
    workflow["name"] = "Deduction Resolution Workbench V2"
    workflow["active"] = False
    workflow.setdefault("settings", {})["availableInMCP"] = False
    workflow.pop("id", None)
    workflow.pop("versionId", None)
    metadata = workflow.get("meta")
    if isinstance(metadata, dict):
        metadata.pop("instanceId", None)
    node_by_name(workflow, "Read Settlement CSV")["parameters"]["fileSelector"] = "/files/deduction-workbench/v2/input/settlement_deductions.csv"
    node_by_name(workflow, "Read Accrual CSV")["parameters"]["fileSelector"] = "/files/deduction-workbench/v2/input/invoice_accruals.csv"
    node_by_name(workflow, "Code (Settlement: normalise + key)")["parameters"]["jsCode"] = NORMALISE_SETTLEMENT
    node_by_name(workflow, "Code (Accrual: normalise + key)")["parameters"]["jsCode"] = NORMALISE_ACCRUAL
    node_by_name(workflow, "Code (Deterministic Match: one-to-one)")["parameters"]["jsCode"] = DETERMINISTIC_MATCH
    node_by_name(workflow, "Code (Verify Classification Against Evidence)")["parameters"]["jsCode"] = VERIFY_EVIDENCE
    strengthen_classification_controls(workflow)
    node_by_name(workflow, "Sticky Note")["parameters"]["content"] = "V2: configured aliases, canonical vendors, deterministic matching, AI proposals, one full-run balance allocation, fail-closed routing, complete five-file export"
    for node in workflow["nodes"]:
        if "credentials" in node:
            for credential in node["credentials"].values():
                credential["id"] = "REPLACE_WITH_N8N_CREDENTIAL_ID"
                credential["name"] = "Select credential after import"
        if node["name"].startswith("Write ") and node["type"] == "n8n-nodes-base.readWriteFile":
            path = node["parameters"].get("fileName")
            if path and "/output/" in path:
                filename = path.rsplit("/", 1)[-1]
                node["parameters"]["fileName"] = f"/files/deduction-workbench/v2/output/{filename}"

    connections = workflow["connections"]
    connections["Code (Parse Classification Response)"]["main"] = [[{
        "node": "Loop Over Unmatched Lines", "type": "main", "index": 0,
    }]]
    connections["Loop Over Unmatched Lines"]["main"][0] = [{
        "node": "Code (Verify Classification Against Evidence)", "type": "main", "index": 0,
    }]
    connections["Code (Verify Classification Against Evidence)"]["main"] = [[{
        "node": "Route Classification Results", "type": "main", "index": 0,
    }, {
        "node": "Code (Build Complete Branch Exports)", "type": "main", "index": 0,
    }]]

    workflow["nodes"].extend([
        {
            "parameters": {"jsCode": COMPLETE_BRANCH_EXPORT},
            "id": "5bb417c8-d38b-4c8d-a9d7-e078f9e82c29",
            "name": "Code (Build Complete Branch Exports)",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [3152, 160],
        },
        {
            "parameters": {
                "operation": "write",
                "fileName": "=/files/deduction-workbench/v2/output/{{ $binary.data.fileName }}",
                "options": {},
            },
            "id": "901e62d7-19fe-45b0-b73a-aa22ed5af839",
            "name": "Write Complete Branch Exports",
            "type": "n8n-nodes-base.readWriteFile",
            "typeVersion": 1.1,
            "position": [3376, 160],
        },
    ])
    connections["Code (Build Complete Branch Exports)"] = {"main": [[{
        "node": "Write Complete Branch Exports", "type": "main", "index": 0,
    }]]}

    DESTINATION.write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf-8")
    print(DESTINATION)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
