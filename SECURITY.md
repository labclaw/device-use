# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.0.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security issues via [GitHub Security Advisories](https://github.com/labclaw/device-use/security/advisories/new).

Include:

- Description of the vulnerability
- Steps to reproduce
- Affected component
- Potential impact assessment

## Response Timeline

| Stage              | Target            |
|--------------------|-------------------|
| Acknowledgment     | 48 hours          |
| Initial assessment | 5 business days   |
| Fix or mitigation  | 30 days           |
| Public disclosure  | After fix release |

## Scope

### In scope

- Injection vulnerabilities (SQL, command, path traversal)
- Device command safety bypass (sending unapproved commands to devices)
- Credential or API key exposure
- Privilege escalation
- Plugin sandbox escape

### Out of scope

- Denial of service against local-only services
- Bugs in third-party dependencies (report upstream)
- Social engineering

## Lab Safety Considerations

Device-use controls physical laboratory hardware via computer-use agents. Security vulnerabilities that could result in:

- **Uncontrolled device activation** (lasers, motors, high-voltage equipment)
- **Safety interlock bypass**
- **Calibration data corruption**
- **Unauthorized experiment execution**

are treated as **critical severity** regardless of software impact assessment.

## Secret Rotation

- API tokens and deploy SSH keys: rotate every 90 days.
- Emergency rotation: within 24 hours of suspected compromise.
- Never log secret values or full token identifiers.
