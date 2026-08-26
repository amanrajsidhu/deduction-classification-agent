# Security and data boundary

## Public demonstration

Only committed synthetic data may be used. The repository does not accept or
request real settlement exports, accrual ledgers, customer names, invoices,
portal credentials or other confidential information.

## If someone offers real data

Do not ask them to email it, upload it to this repository or place it in a public
demo. Stop and agree a separate authorised engagement covering the processing
environment, access, retention, deletion, controller/processor responsibilities
and the client's own legal, security and procurement requirements.

## Public build limitations

- The workflow is a demonstration, not a production control.
- The AI proposes classifications; it cannot post, approve, dispute or write off.
- Human review remains mandatory for conflicting or insufficient evidence.
- API credentials, host-specific paths and live n8n instance/workflow identifiers
  must never be committed. Portable container paths used by the synthetic demo
  may be documented.
- Public workflow exports must remain inactive, unavailable over MCP and use
  placeholder credential references. Select credentials only after local import.
- Output workbooks generated from real data must never be committed.

This note is a product boundary, not legal advice or a compliance certification.
