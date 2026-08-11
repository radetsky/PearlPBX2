# Contributing to PearlPBX2

Thanks for your interest in contributing.

## Before you start

- For anything beyond a small bugfix, open an issue first to discuss the approach before writing code.
- Skim `CLAUDE.md` for an overview of the project architecture (Django app layout, standalone `services/`, config generation flow).

## Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run the test suite (see below)
5. Push and open a Pull Request against `main`

## Code style

- Python: PEP 8
- All text in code — comments, docstrings, UI strings, log/error messages — must be in English
- Prefer clear naming over explanatory comments; keep changes minimal and scoped to the task
- Django model or permission changes must include the corresponding migration (`python manage.py makemigrations`)

## Testing

```bash
python manage.py test
python manage.py test core
python manage.py test apps.api
python manage.py test apps.callback
python manage.py test apps.dashboard
python manage.py test apps.provision
python manage.py test apps.reports
```

Verbose output: `python manage.py test --verbosity=2`

## Code review

Pull requests are reviewed before merge. Opening a PR does not guarantee it will be accepted — acceptance is at the maintainer's discretion.

## License

PearlPBX2 is distributed under the [PolyForm Shield License 1.0.0](LICENSE) (see also [NOTICE](NOTICE)). By submitting a contribution, you agree it is distributed under the same license. Using this project — including your contribution — to build or operate a competing product or service remains prohibited under [LICENSE](LICENSE). You retain copyright to your own contribution; do not remove existing copyright or `Required Notice:` lines when modifying files.

## Reporting issues

Use the GitHub issue tracker. Include steps to reproduce, expected vs. actual behavior, and relevant logs (Asterisk CLI, Django, or service logs).
