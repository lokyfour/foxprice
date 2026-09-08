# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x     | ✅ Active  |

Foxprice is currently pre-1.0. Security fixes are applied to the latest
`main` branch only.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting instead:

1. Go to https://github.com/lokyfour/foxprice/security/advisories
2. Click **"Report a vulnerability"**
3. Fill in the details

We aim to respond within **72 hours** and to publish a fix within **14 days**
for confirmed vulnerabilities.

If you are unable to use GitHub's private reporting, email the maintainer
directly (address in the GitHub profile).

## What to Include

A useful report includes:

- Description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected version(s)
- Any suggested fix, if you have one

## Known Security Requirements

These are documented hard requirements — violations are treated as bugs:

| Requirement | Reason |
|---|---|
| Playwright ≥ 1.55.1 | CVE-2025-59288 — insecure `curl -k` during browser download enables MitM RCE on macOS |
| No `shell=True` in subprocess calls | Prevents command injection via user-supplied adapter names |
| JWT stored in `HttpOnly + Secure + SameSite` cookie | Prevents XSS-based token theft in the web panel |
| No credentials in code or git history | Credentials must live in `.env` (gitignored) or a secret manager |
| Web panel not exposed to the public internet | No DDoS/auth protection beyond application-layer rate limiting |

## Scope

In scope:

- Remote code execution, privilege escalation, or authentication bypass
- Credential or secret leakage
- Command injection via adapter names, parts input, or web panel fields
- Dependency vulnerabilities with a CVSS score ≥ 7.0

Out of scope:

- Vulnerabilities in sites that adapters connect to (those are third-party)
- Theoretical issues without a practical attack path
- Rate limiting or DoS against the web panel in local deployments

## Disclosure Policy

We follow coordinated disclosure. Once a fix is released, we will publish a
GitHub Security Advisory crediting the reporter (unless they prefer to remain
anonymous).
