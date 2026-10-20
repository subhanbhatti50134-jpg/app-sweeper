# Security Policy

## Supported Versions

Security fixes are applied to the latest code on the `main` branch and released
as soon as practical.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report them privately via email to:

**subhanbhatti50134@gmail.com**

Include as much of the following as you can:

- A description of the vulnerability and its potential impact
- Steps to reproduce the issue
- Affected version(s), platform, and package manager
- Any relevant logs, screenshots, or proof-of-concept code

You should receive an acknowledgment within **72 hours**. You will then be kept
informed of the progress toward a fix and coordinated disclosure.

## Scope

This tool runs with elevated privileges and deletes files on the system, so the
following are especially important:

- Bypass of `PROTECTED_PATHS` safeguards
- Arbitrary file or directory deletion outside of leftover/clean targets
- Command injection through package names, paths, or backend responses
- Privilege escalation via the `pkexec`/`sudo` invocation path
- The local web UI server (`127.0.0.1`) accepting requests from other origins,
  or leaking data beyond the local machine

## Preferred Disclosure

We prefer coordinated disclosure: please report privately first and allow a
reasonable window for a fix before publishing details.
