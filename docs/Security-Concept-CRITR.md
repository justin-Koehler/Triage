# Security Concept CRITR

Paste the sections below into the Confluence page. Policy text stays as in the template. Only the solution content is filled. Items in square brackets are not in the repository and must be entered in IT4you before the page is approved. No personal names.

## 0 General References

| Category | link to IT4you | comment |
|---|---|---|
| PRA | [PRAxxxx — not in the repository] | Protection requirement analysis for CRITR. Number starts with PRA. |
| SARA | RA0205043 | Risk assessment in My Risk Assessments. |
| ASRA | ASRA0018132 | Already on the page. |
| IT4you App | [application issue — not in the repository] | Create the application in IT4you and link it here. |

## 1 Scope

This security concept applies to **CRITR** (Change-Request Intake and Triage).

CRITR is an internal web application. A user writes a short sentence. The application drafts a change or IT-request brief (description, benefit, problem, solution, risks). The person reviews the draft. The local database is the source of truth. Jira receives the ticket only after that review, asynchronously through an outbox. The model writes prose from the given text and does not invent figures, systems, or names.

In scope:

- Browser UI (workspace, intake chat, settings)
- Application service (FastAPI)
- Database (PostgreSQL in the composed deployment, SQLite only for local development)
- Reverse proxy with TLS (Caddy; host name on the deployment file is `scscm.stackit.gg`)
- Login via Cidaas (OpenID Connect, authorization code with PKCE)
- Outbound interfaces: Jira REST (ticket create and user lookup), LLM provider (Ollama or an approved API)

Out of scope of this concept: Jira itself, Cidaas, the LLM provider, and the STACKIT platform. Their own security concepts apply.

```
Browser
  |  HTTPS
  v
Caddy (only published ports 80/443)
  |  internal
  v
CRITR app ---- HTTPS ----> Cidaas (login)
  |                 \-----> Jira (outbox, user lookup)
  |                 \-----> LLM (draft text only)
  v
PostgreSQL (not published)
```

The application is not in production operation yet. Kubernetes manifests exist as templates. Until go-live, the pilot must not be exposed on the open internet.

Dependencies: Cidaas security concept, Jira security concept, STACKIT / platform security concept once the workload is placed there, and the PRA/SARA issues above once they exist.

Criticality: no SBF rating is available in the repository. Personal data in the pilot are display name, e-mail, and free text that can contain names. Until the PRA is linked, treat confidentiality as internal business data and do not publish the service.

## 2 Responsibility

No names. Replace the brackets with the IT4you groups.

| Role | IT4you group | Does |
|---|---|---|
| Lane owner | [group] | Lane priority and business use of the intake |
| Product owner | [group] | What the product may do, acceptance of changes |
| Application owner / solution owner | [group] | This concept, accounts, patches of the application, PRA measures |
| Security | [group] | SIMPL interpretation, deviations, risk acceptance |
| Platform / runtime | [group, or STACKIT if the platform is theirs] | Host, network, OS patches, backup product |

Support:

- First level: service desk of the lane. Password resets for workforce accounts stay with the identity provider, not in CRITR.
- Second level: application group. Intake, sync, configuration.
- Third level: platform group for the runtime, and the vendor process for Cidaas, Jira, and the LLM.

## 3 Security Requirements

No content from the solution owner. Information Security maintains the control table.

## 4 Vulnerability Management (SIMPL 6.2)

The requirements are **not** fully implemented as in the policy. Deviations:

- There is no production IP range yet, so the system is not in the central SIT vulnerability scanner. Qualys (or the SIT scanner) has not been run. After an address exists, the application owner requests asset registration and scanner access from Exposure Management. Scans then follow the SIT cadence (at least monthly). Findings are classified with CVSS v3. Deadlines: critical 1 month, high 3 months, medium 6 months, and before go-live for medium and above.
- Code and image findings today:
  - `pip-audit` on every push and pull request (`requirements.txt`, strict).
  - Trivy on the container image. Critical unfixed findings fail the build. A CycloneDX SBOM is stored as a build artifact.
  - Snyk and SonarQube are not used.
  - Azure Defender is not used. The deployment target in the proxy file is STACKIT, not Azure.
- Findings are handled in the GitHub project and issues of CRITR, not yet as IT4you tickets or a Jour fixe agenda. Before go-live, medium and higher findings are copied into IT4you tickets.
- No third-party newsletter is subscribed. Patch notices come from the CI scanners, Python advisories, and the image base.
- If the platform is later run by SIT, vulnerability scans of the infrastructure are done by the SIT infrastructure team, not by the application group.

## 5 Security Patch Management (SIMPL 6.3)

The requirements are **not** fully implemented as in the policy, because there is no live server yet.

- Sources: GitHub dependency and image scan on each change; Python package advisories; base-image releases; vendor notices for Cidaas and Jira (those products patch themselves).
- Classification and deadlines: same CVSS bands as SIMPL 6.2. Critical and high before go-live.
- Every application change is built and tested in CI (lint, unit, contract) before an image exists. Production deploy is a separate, reviewed step. Four-eyes applies once a production environment exists.
- OS and platform patches are not done by the application group. They follow the platform patch window. Application image updates are planned in a change outside business hours once the service is live. Proposed window: [weekday, time, to be agreed with the platform group].
- End of support: Python and the image base must stay on a supported release. No migration project is open because the service is not live.

## 6 User Management (SIMPL 9.1)

Account administration for workforce users is not done inside CRITR. CRITR creates a local user row on first successful login (display name, e-mail, subject). Disabling the person in the identity provider stops the next login. Local rows of people who left are removed by the application owner when the identity provider account is gone. Country-specific accounts are removed when the country manager notifies the application group. There is no automatic join to the HR leaving feed yet. That is a deviation until go-live.

| Account type | In CRITR |
|---|---|
| Personalized standard users | Exist. Identity is Cidaas (OIDC). Intended target is the workforce identity (SIAM / equivalent). Locally the app only stores the profile. Mark: **under the identity provider**, not SIAM-managed inside CRITR. |
| Personalized administrator users | Do not exist as a separate login. Settings are available to any signed-in user in the current build. Before go-live, administration is limited to the application group. Deviation until that restriction is on. |
| Functional users | Do not exist. |
| Functional administrator users | Do not exist as a shared admin login. |
| Emergency account | Does not exist. Not required while there is no production system. Before go-live: one emergency account, secret in the operations safe, documented with purpose and the group allowed to use it. Never disabled. |
| Technical users | One integration identity for Jira (API token) and one for the LLM (API key), stored encrypted in the database. Purpose: ticket sync and draft text. Responsible: application owner group. No interactive login. |
| Technical administrator users | Do not exist. |
| Default accounts | The development build contains local accounts (`dev`, `alex`, `sam`) and a Jira-name login. They are not for production. Deviation: they must be switched off before any shared or external deployment. |

Inactive personalized accounts: no 90-day lock inside CRITR. Lock follows the identity provider. Local profile rows are reviewed by the application owner at least yearly.

## 6.1 Secure Authentication (SIMPL 9.2)

Implemented differently from a pure SIAM SSO description. Detail:

| Account | How they sign in |
|---|---|
| Personalized standard users | OpenID Connect to Cidaas, authorization code with PKCE (S256). Scopes: openid, profile, email. The app session is an HMAC-signed cookie (HttpOnly, SameSite=Lax, Secure when TLS is on). The cookie holds no password. |
| Personalized administrator users | Same login. No second factor inside CRITR. If the service is reachable from outside the internal network, MFA must be enforced at Cidaas before go-live (SIMPL 9.2-2). |
| Functional users | Do not exist. |
| Functional administrator / emergency | Not in place. When created: secret handed over in person or by encrypted message, changed after each emergency use. |
| Technical users | No interactive login. API tokens. Injected into configuration, not stored in git. |
| Technical administrator users | Do not exist. |

Password management:

- Workforce passwords are not stored or reset in CRITR. Complexity, history, and lockout are the identity provider’s.
- Initial password of a workforce user is not issued by CRITR.
- Technical secrets are encrypted with Fernet before they are written to the database. They are masked in the settings UI. They are changed when someone who knew them leaves the application group, or on suspicion of compromise.
- Default passwords of the development accounts must not be used outside a workstation.

Session:

- Application session ends after 12 hours (cookie max-age). The policy for an internal browser application is 8 hours. **Deviation:** reduce the session to 8 hours before go-live, or accept 12 hours in the risk record.
- OIDC handshake cookie expires after 10 minutes.
- There is no separate idle timer of 5 minutes. The service is not an internet application. If it becomes reachable from the internet, the 5-minute idle end from the policy applies.

Transport of the login is HTTPS via the reverse proxy. The app does not speak Kerberos.

## 6.2 Authorization Management (SIMPL 9.3)

The permission concept is this section until a separate authorization document exists. Place of the documentation: this security concept and the repository file `docs/Sicherheit.md`.

| Permission | Who | Criticality | SoD |
|---|---|---|---|
| Use intake and workspace | Any signed-in workforce user | Low, pre-approved for the lane | No admin rights |
| Change LLM and Jira settings, read technical secrets | Application owner group only (target). Today: every signed-in user. **Deviation** until the role check is enforced. | High | The person who changes a secret is not the only person who approves the production change |
| Emergency administration | Emergency account, after written instruction | High | Not the escalation manager |

Assignment is not yet in an IDM workflow. Until go-live, access is “can log in at the identity provider”. Admin rights, once split off, are requested by the manager and approved by the application owner (four eyes). Nobody approves their own admin right.

Removal: when the person leaves the company, login dies with the identity account the same day. Extra rights in CRITR are removed within 8 days. A move inside the company is checked by the releasing and the receiving manager within 30 days. Country accounts are removed when the country manager sends a deletion notice. There is no automatic department-change feed. **Deviation** until that notice process is agreed.

Recertification: the application owner reviews who can sign in and who can open settings at least once a year. The result is stored with the service documentation.

CRITR is not treated as a year-end financial system. Export of permission changes for auditors is not built.

## 7 Data and Disk Encryption (SIMPL 10.4)

- Data on the public network (browser, Cidaas, Jira, LLM) is sent over TLS.
- Login secrets of the workforce are not stored in CRITR.
- Technical secrets in the database are encrypted (Fernet).
- Session cookies are signed, not a store of passwords.
- Disk encryption of the database volume is a platform duty (STACKIT or the host). It is not implemented inside the application. Confirm it in the platform concept before go-live.
- Laptops that hold a local SQLite copy fall under the workplace encryption standard, not under this application.

## 8 Logging and Monitoring (SIMPL 12)

Implemented differently from a full SIEM integration.

- The process log records application errors and request handling. It must not contain passwords, API tokens, or private keys.
- Failed logins at Cidaas are logged by Cidaas, not by CRITR.
- CRITR logs the authenticated subject on privileged actions only to the extent the runtime log captures the HTTP call. A dedicated audit trail for account create, password reset, and emergency use is **not** complete. Deviation until those events are written without secrets.
- Log content, where the platform provides it: time, account or service id, source IP if the proxy forwards it, action, success or failure, object id.
- Logs are not yet shipped to the central logging service or the CDC. Retention target once operated: 30 days for technical logs, 90 days for access and admin logs. Not GoBD. Not a 15-month financial-audit log.
- Access to logs that contain personal data needs data-protection approval. Technical logs do not.
- Time sync is the platform NTP (stratum ≤ 3). The application does not run its own time source.
- Capacity: no production monitor yet. After go-live the platform group alerts on process down and disk of the database. There are no scheduled business jobs beyond the outbox worker inside the app process.

## 9 Network Segmentation (SIMPL 13.2)

Target placement, to be confirmed with the platform group: Internal Standard Zone, sub-zone PNS (non-SAP service for users), security group of the CRITR application. Not HSZ. Not directly reachable from the internet.

- Users reach only the reverse proxy on 443.
- The database accepts connections only from the application (network policy in the Kubernetes template).
- The application may call DNS, the database, and TCP 443 (Cidaas, Jira, LLM). No direct user-to-database path.
- Firewall rules are the platform’s. ANY rules are not requested.
- DNS: the current proxy name is under `stackit.gg`, not under `.lidl` or `.schwarz`. A future internal name uses `.internal`, `app.internal`, or `app.schwarz` as in the policy. No new internal zone under `.lidl` or `.schwarz`.

## 10 Secure Development (SIMPL 14.1)

**Confirmation**

- [ ] The requirements are implemented as described in the guideline above.
- [x] The following requirements are implemented in different ways.
- [x] The detailed documentation of the implementation required by the specification is this security concept (sections 1, 4, 10) and the Git repository.
- PRA measures: observe the PRA in IT4you once the issue exists. Number is not in the repository yet. Link: [PRA — fill in IT4you].
- Responsibilities: see chapter 2. Application owner / solution owner runs the process. A named Security Delegate, Security Champion, and Software Engineering Security Expert in IT4you groups are **not assigned**. **Deviation.** Until assignment, the application owner group covers the engineering security tasks.
- Implementation and configuration: this concept; GitHub Actions workflow; `Dockerfile`; `docker-compose.yml`.
- Infosec control activity tests: [IT4you CAT — fill in].
- Infosec risks in the red box: [IT4you risk — fill in]. SARA RA0205043, ASRA ASRA0018132.

The grace period of SIMPL 14.1 runs until **30.09.2026**. CRITR is make-code (Python FastAPI), not buy-software, not SAP, not low-code, not a legacy freeze. Sections 8.1 and 8.2 of the policy do **not** apply as an exemption. Remaining gaps stay as documented deviations until the grace period ends or they are closed.

### 1 General

This policy applies to CRITR source, infrastructure-as-code (`Dockerfile`, Compose, Caddyfile), and every change intended for the live host `scscm.stackit.gg`.

### 2 Organisation and documentation

**2.1 Roles.** Product / solution owner: application owner group (IT4you group still to be named). Engineer: the CRITR engineering team. Architect: not a separate named person; architecture is this concept and section 1. Security Delegate / Champion / Software Engineering Security Expert: not named. **Deviation.** KPI reporting to a central engineering-security team is not in place.

**2.2 Documentation.** Central entry: this Confluence security concept (paste of this file) plus the Git repository. Access follows SIMPL 9 (workforce login to Confluence / Git). Source, tests, Compose, and the Caddyfile live in Git. Secrets (`deploy/compose.env`, API keys, session secret, encryption key) are **not** in Git. Operator notes that do not belong in Git stay in Confluence. Naming follows the repository paths and this concept’s section numbers.

### 3 Security requirements

**3.1 Standard solutions (implemented differently).**

- **Identity.** Workforce login is Cidaas OIDC (authorization code + PKCE). Not Entra ID, not MyAPI, not Azure managed identities. Session: HMAC-signed cookie, HttpOnly, SameSite=Lax, Secure when `APP_ENV` is not `dev`. No passwords in Git or in the cookie. Technical secrets (Jira, LLM) are encrypted (Fernet) in PostgreSQL and injected from `deploy/compose.env` on the host. Production secrets are not used on developer laptops as the live env file. Least privilege for the container: non-root, `cap_drop: ALL`, read-only root filesystem. **Deviation:** no Key Vault / HSM; secrets sit in the host env file and encrypted DB rows.
- **Interfaces.** Browser → Caddy :443 TLS → app (internal). App → PostgreSQL (internal network only). App → Cidaas, Jira, STACKIT Model Serving over HTTPS.
- **Logging and monitoring.** Application process log without secrets. Not forwarded to the central SIEM / CDC. **Deviation** (see section 8).
- **Tools.** GitHub Actions, Ruff, pytest, pip-audit, Trivy, CycloneDX SBOM. Not the full Cyber Security approved SAST/SCA catalogue (no SonarQube, no Snyk). **Deviation** until those tools are approved or the current set is accepted in the risk record.
- **Cryptography.** TLS at Caddy. Session HMAC. Fernet for technical secrets. Certificate lifecycle of the public name is Caddy / STACKIT, not an application-owned PKI process.

**3.2 Further software requirements.** Security goals for CRITR: (1) only authenticated workforce users reach the UI; (2) secrets never enter Git; (3) the model receives ticket text for drafting only and is not used to train a local model; (4) Jira is written through an outbox after review. These are application-specific. They are not written as a full OWASP ASVS checklist. **Deviation:** no yearly ASVS review with a Software Engineering Security Expert yet.

### 4 Secure architecture and design

**4.1–4.3.** Building blocks: Caddy, FastAPI app, PostgreSQL, Cidaas, Jira, STACKIT Model Serving. Diagram: section 1 of this concept. Shared security services in use: Cidaas (SSO), Caddy (TLS), STACKIT (host, backup product), GitHub (CI). **Deviation:** no Architecture Runtime Model (ARM / S-ARM) in the architecture toolset; no Architecture Product Evaluation recorded. Until architecture publishes ARM, this concept is the architecture document.

**4.4 Threat analysis.** Threats and mitigations are this concept (auth, session, outbox, secrets, LLM prompt, Jira). Residual risks that cannot be closed here follow SIMPL 2.1 and SARA RA0205043. **Deviation:** no separate Threat-Modelling-SIMPL workshop artefact in the repository.

Entry points and hardening intent:

| Entry | Control |
|---|---|
| HTTPS :443 | Caddy only published port; TLS |
| Login | Cidaas OIDC + PKCE; invalid callback returns to login, not a JSON error |
| Session cookie | HttpOnly, signed, Secure in production |
| Jira | Outbound REST with stored token; outbox; no inbound Jira admin |
| LLM | Outbound Chat Completions; no training; key encrypted |
| Database | Internal network; not published |

### 5 Secure implementation

**5.1 Practices.** Python 3.13, pinned `requirements.txt`, FastAPI / SQLAlchemy. No unmanaged C. No ODJ IaC templates; Compose is the deployment description.

**5.2 Configuration.** Live (STACKIT VM + Compose) is separate from local SQLite/dev. `DEV_LOGIN_ENABLED` is off in the production env example. Production data are not loaded into pytest. IDE / compiler hardening is the engineer workstation standard, not enforced by CRITR.

**5.3 Secure code / SBOM / review.** CycloneDX SBOM is produced in CI (Trivy) and stored as a build artefact. SCA: pip-audit (strict) on every push/PR; Trivy on the image (critical, fail the job; image, base, and packages). Integrity of the image tag is the Git SHA (`critr:${GITHUB_SHA}`), not `latest`. Manual four-eyes: pull request. **Deviation:** no Cyber Security–approved SAST tool (Ruff is lint, not SAST). Container config scan beyond Trivy is not a separate CIS benchmark job.

**5.4 Tests in implementation.** Unit and contract tests in CI, including auth (Cidaas callback), Jira field mapping, and effort-sheet rules. They cover happy path and several negative cases. They are **not** a complete set of security-requirement test cases derived from ASVS. **Deviation.** Manual review of security-relevant changes is the PR, not a second Security Delegate. No fuzzing harness.

### 6 Secure software verification

**6.1 Test plan.** CI is the test plan: lint → unit → contract → pip-audit → image → non-root → Trivy → SBOM. Expected result: all jobs green. A failed job blocks merge to `main` for PRs. Previously known issues are tracked in GitHub issues, not a separate security regression suite.

**6.2 Abuse tests.** Contract tests cover invalid OIDC callback and empty fields. There is no systematic fuzzing or DoS test. Availability class is not “high availability” in the PRA (not set). **Deviation.**

**6.3 Pipeline.** GitHub Actions is automated on push to `main` and on pull requests. Quality gate: CI green. Deploy to STACKIT is **not** the same pipeline; it is a separate host rebuild from the tree. **Deviation:** deploy is not a fully automated gated release from Artifactory with signature verification (see 7.1).

**6.4 Test environment and data.** Tests run on GitHub runners with synthetic fixtures. No production personal data. Local SQLite is developer data. The live VM is not used as the test bed.

### 7 Deployment, operations, maintenance

**7.1.1 Process.** Repeatable path: CI on GitHub → copy tree to `/opt/apps/critr` on the STACKIT VM → `docker compose --env-file deploy/compose.env up --build -d`. Image name `critr:${IMAGE_TAG:-local}`. Target: SHA tag in production, not `latest`. Human trigger. Rollback: previous image / previous tree plus database backup. RTO is not measured; STACKIT standard BSL would be 4 h, current host backup is daily (section 12). **Deviation** vs automated E2E deploy and vs binary signing (SIMPL 10.1) at deploy time.

**7.1.1.2 Artefacts.** Deploy depends on a successful local/CI test set, not on a signed artefact store. Failed Trivy critical stops CI. Failed deploy is a stopped compose recreate; no automatic traffic switch. **Deviation:** no Artifactory archive, no deploy-time signature check against a trust store.

**7.1.1.3 Accountability.** Who deployed is the SSH user on the VM plus Git history. Version is the Git revision / image digest. Not a SIMPL 12-compliant deploy ledger. **Deviation.**

**7.1.2 Secrets.** Live secrets only in `deploy/compose.env` (mode restricted on the host) and Fernet-encrypted DB settings. Not in Git. Developers do not receive the production env file through the repository. There is **no** pre-commit secret scanner in CI. **Deviation.** No vault injection, no production-secret access SIEM alerts, no automated secret rotation. Production and development secrets are different files.

**7.1.3 External audits.** No penetration test recorded. Order one if the PRA requires it (SIMPL 4). **Deviation** until then.

**7.2 Operations.** Vulnerability and patch: sections 4 and 5. Logging: section 8. Change: section 11. Incident, ITSCM, backup, hardening: platform + this concept. Inventory of versions: Git tags/commits and the image SHA. Unused services are not installed in the app image.

### 8 Exceptions

Not buy-software, not SAP, not low-code, not a frozen legacy system. No section-8 exemption. Residual gaps are SIMPL 2.1 deviations, not a legacy waiver.

---

## 11 Secure Change Procedures (SIMPL 14.2)

**Confirmation**

- [ ] The requirements are implemented as described in the guideline above.
- [x] The following requirements are implemented in different ways.
- [x] Documentation: this section and Git history / pull requests.
- PRA: [link when the issue exists].
- Responsibilities: application owner group for product changes; platform group for host OS. Not ARIS as the operational tool.
- Implementation: GitHub pull requests; live deploy on the STACKIT VM.
- Infosec CAT / risk: [fill in IT4you].

### 1 Change management (implemented differently)

CRITR is **not** on the central ARIS change workflow as the daily tool. Changes are:

1. Requested and described in a GitHub pull request (or an equivalent reviewed commit path).
2. Tested in CI (lint, unit, contract, pip-audit, image, Trivy).
3. Released by deploying a reviewed tree/image to the live host.
4. Versioned by Git SHA / image tag. Not `latest` as the production contract.

Asset Security Risk Analysis: SARA RA0205043 / this concept. Update this concept and operator docs in the same change when security-relevant behaviour changes.

Four-eyes for production: the author of the change is not the only person who may approve the pull request / production rollout. **Deviation until strictly enforced:** live deploys have been performed from the engineering workstation; name a second person for production apply.

Function tests and defect fixes run in CI before the image is used. Critical/high findings: section 4.

Production personal data are **not** copied into non-production. Tests use fixtures. If a copy is ever required, it is anonymised first or the non-production system must meet production controls.

### 2 Rights to make changes

Only IT staff with Git and host access change the system. Workforce users cannot install software or change workstation policy through CRITR. End users cannot change the CRITR server configuration. Third-party libraries are consumed as released packages so they remain updateable (`requirements.txt`, not vendored forks), except documented application code.

### 3 High-security zone (HSZ)

Not applicable. CRITR is not in the HSZ. No HSZ IT4you ticket process.

### 4 Year-end relevant systems

**Not applicable.** CRITR is not in the IT year-end / financial-auditor scope. No GoBD change export. Categories Standard / Normal / Emergency / Technical Change are therefore not implemented as SAP-style change types. Emergency fixes still need two persons and a recorded PR after the fact.

---

## 12 Backup Procedures and Storage (SIMPL 18.1)

**Confirmation**

- [ ] The requirements are implemented as described in the guideline above (GOLD / tape library).
- [x] The following requirements are implemented in different ways: **STACKIT section 8**, with a weaker RPO than STACKIT Standard 4 h.
- [x] Documentation: this section.
- PRA measures: [link].
- Responsibilities: application owner requests restore; STACKIT / platform backup product executes. SoD: host admin vs backup admin is a platform duty, not implemented inside CRITR.
- Implementation: STACKIT server backup of the live VM. No tapes, no SIT barcode library.
- Infosec CAT / risk: [fill in].

### What is backed up

| Relevant (must restore) | Not relevant (rebuild) |
|---|---|
| PostgreSQL volume (requests, comments, users, encrypted settings) | Container image (rebuild from Git) |
| `deploy/compose.env` on the host (secrets) | Local developer SQLite |
| Caddy data (certificates) if on the same VM | Knowledge markdown in Git |

No backup on laptops. No application-level backup tool besides the platform product.

### Service level (deviation from STACKIT Standard 8.2.1)

STACKIT Standard BSL in the policy: RPO **4 h**, RTO **4 h**, retention 2 weeks daily.  
**Actual:** daily **STACKIT server backup** of the VM. RPO is therefore about **24 h**. RTO, retention, and whether the copy is offline / in another fire compartment are **not confirmed** with the STACKIT backup product. Restore test: **open**. **Deviation.** Document this in SIMPL 2.1 if 4 h RPO is required by the business.

No GOLD/SILBER tape scheme. Section 3–6 (tape systems, barcodes, offsite trucks) **do not apply**. Encryption of backup media is the STACKIT backup product (SIMPL 10.4 at platform level).

Exceptions: none recorded. Domain controllers are not in scope.

Restore authorisation: application owner group. Execution: platform / STACKIT backup operators. A qualified deputy must be named in the operations handbook.

---

## 13 Archiving and retention (SIMPL 18.3)

**Confirmation**

- [x] The requirements are implemented as described for **Type 1** (data remain in the leading system).
- [x] The following are implemented in different ways: no automated deletion job yet.
- Documentation of the retention place: this section. Copy the periods into the processing record (VVZ) when data protection confirms them.
- PRA: [link].
- Responsibilities: solution owner together with the process owner define retention. Application owner deletes. No SIT Archiving Services (Type 2 not used).
- Infosec CAT / risk: [fill in].

CRITR can hold its own data for the retention period. **Type 2 external archive is not used.** No Archiving Services monitoring, no yearly readability sample of an external archive.

Proposed periods (confirm with process owner and DPO, then lock in the VVZ):

| Data | Retention |
|---|---|
| Change briefs, chat, comments, status updates | 3 years after the request is closed, then delete |
| User profile row | When the person can no longer sign in and the IdP account is gone |
| Technical logs | 30 days |
| Access and admin logs | 90 days (not financial-audit, not GoBD) |

After the period, delete according to SIMPL 7. **Deviation:** deletion is **manual** by the application owner; no cron job. Backups of the VM follow section 12 until they age out of the backup product.

---

## 14 System Hardening (SIMPL 20)

**Confirmation**

- [ ] The requirements are implemented as described for every OS control (GRUB, SNMPv3, Powerbroker).
- [x] The following requirements are implemented in different ways: **application and container hardening** in CRITR; **OS, BIOS, SNMP, domain controller** are STACKIT / platform, not this application.
- [x] Hardening parameters for the application stack: this section, `Dockerfile`, `docker-compose.yml`, Caddyfile.
- PRA: [link].
- Responsibilities: application owner for the CRITR image and Compose; platform owner for the VM OS.
- Infosec CAT / risk: [fill in].

### 1 General (application)

Minimal install: Python slim image, only the CRITR app, Caddy, PostgreSQL 16. No compiler, no telnet, no ftp in the app image. Only needed ports: 80/443 on Caddy; app and database unpublished. Non-root user `appuser` (uid 10001). `no-new-privileges`, `cap_drop: ALL`, read-only root, tmpfs `/tmp`. Healthcheck on `/api/live` or `/api/ready`. Support: Python 3.13 and the pinned base image must stay in vendor support. Solution owner keeps the image current via CI + redeploy.

Login banner: not used (no extra system/company text).

### 2 Additional

**Cookies (external / TLS site).** Session cookie: **HttpOnly**, **Secure** in production, SameSite=Lax. OIDC handshake cookie same flags. No session token in JavaScript.

**Server / Linux / SNMP / BIOS / Domain controller.** Not configured by CRITR. They belong to the STACKIT VM hardening concept. Certificate store of Caddy should contain only required CAs (platform). Machine certificate: STACKIT / Caddy-managed for `scscm.stackit.gg`.

### 3 Technical data-protection controls

**3.1 Erasure, correction, provision.** The application owner corrects or deletes a profile row and request text on request (manual, including admin access to tables). No self-service erasure. Restriction / stop of processing: disable the person in Cidaas (login ends) and delete or blank the local row. **Deviation** until a product delete action exists or the manual process is accepted in the VVZ.

**3.2 Consent log.** Consent is **not** the legal basis. No digital consent, no consent log.

**3.3 Deletion concept.** See the table below. Technical deletion concept = this table. Confirm with the DPO before go-live sign-off.

**3.4 Separation of data.** One controller, one PostgreSQL database, separated by tables (users, requests, fields, comments, settings). Not multi-tenant by country. No second controller on this database.

### Data protection deletion routines

| Data | When | Where documented | How |
|---|---|---|---|
| User accounts | Person leaves or no longer accesses the system (IdP account removed). Check operational/legal hold. | This concept §§ 6 and 13; VVZ [id] | **Manual** deletion by the application owner. Not automated. |
| Access and admin logging | Target 90 days. Not financial-auditor 15 months. Not GoBD 12 years. | This concept § 8 | Platform log retention. Not inside the app. |
| Functional logs (workflows, request text, master-data-like field changes) | Proposal: 3 years after closure | VVZ [id] | Manual review and deletion until a job exists |
| Personal data A (profile: name, e-mail, subject) | With the user account | VVZ [id] | Manual |
| Personal data B (names in tickets, comments, roles) | With the request | VVZ [id] | Manual |
| Personal data in archive | No archive (Type 1 only) | — | — |
