# Security Policy

## Supported Versions

pyeffect is pre-1.0 software. Only the latest published release is
supported with security fixes; backports to older versions are not
provided.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

pyeffect is a pure-Python library with no runtime dependencies and no
native code, so the attack surface is small — but bugs that could corrupt
state, panic on untrusted input, or enable denial of service are treated
seriously.

**Please report vulnerabilities privately.** Do not open a public issue
for security problems.

1. **Preferred:** open a private security advisory on GitHub at
   <https://github.com/Tomperez98/pyeffect/security/advisories/new>.
2. **Fallback:** email the maintainer at
   `tomasperezalvarez@gmail.com` with the subject
   `[pyeffect security] ...`.

Include whatever you can: the affected version, a minimal reproducer, and
(if known) the impact.

You should receive an acknowledgement within 72 hours. After that, we will
keep you updated as the report is triaged. If the report is accepted, a
fix will be released and the advisory published; if it is declined, we
will explain why.
