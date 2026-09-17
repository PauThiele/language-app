\# Project Instructions



\## Before changing code

\- Inspect the existing implementation first.

\- Do not rewrite working code unnecessarily.



\## After changing code

\- Run the relevant tests.

\- Run the type checker.

\- Check git diff.

\- Tell me what changed and whether tests passed.



\## Safety

\- Never modify .env files.

\- Never delete files unless explicitly requested.

\- Never run destructive git commands.

\- Do not install dependencies without asking first.



\## Code style

\- Follow the existing project conventions.

\- Prefer existing utilities/components over creating duplicates.



\## Windows patching

\- Do not invoke or retry the `apply_patch.bat` wrapper from PowerShell: it corrupts multiline patch payloads on Windows.

\- Instead, invoke the wrapper's underlying `codex.exe --codex-run-as-apply-patch` runner with .NET `ProcessStartInfo.ArgumentList`, passing the entire patch as one raw argument.
