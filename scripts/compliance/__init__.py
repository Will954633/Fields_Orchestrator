"""
Compliance record-keeping (Property Occupations Act 2014 (Qld) + ACL).

Three record types, all stored primarily in MongoDB (system_monitor) and mirrored
to Google Drive (Compliance/ folder) for off-VM, auditor-friendly disaster recovery:

  K — appraisal_archive   : immutable, hash-chained snapshots of every delivered
                            'your home' appraisal/CMA (s215/Sch2; s212 reasonable-
                            grounds defence — prove what a seller saw, as at a date).
  L — credential_register : evidence backing each public credential claim (ACL —
                            no exaggerated experience/skills).
  N — licensee_signoff    : licensee (Principal) sign-off log for public copy
                            (PO Act ss209/215 — marketing checked by the licensee).

Records contain addresses / owner data → Mongo + Drive only, NEVER GitHub.
See: 09_Appraisals/your-home-minisite-compliance-audit-2026-06-21.md (items K, L, N).
"""

LICENSEE_NAME = "Will Simpson"
LICENCE_NO = "4832972"
AGENCY = "Fields Real Estate"
