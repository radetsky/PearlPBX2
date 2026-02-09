# Changelog

All notable changes to the Callback Service will be documented in this file.

## [Unreleased]

### Changed
- "No destinations to call" message now logged at DEBUG level instead of INFO.
- Replaced `--loglevel` (int) CLI argument with `--debug` boolean flag.
- Debug logging is now enabled exclusively via `--debug` flag.
- Removed `LOGLEVEL` environment variable.

### Fixed
- "No destinations to call" used `logging.info()` (module-level) instead of `self.logger.debug()` (instance logger).

## [1.0.0] - 2024-12-21

### Added
- Initial stable release of the Callback Service.
- PostgreSQL polling for callback requests from `callback_number` table.
- Outbound call initiation via Asterisk AMI `Originate` action.
- Multi-process mode via `--process_count` / `VA_PROCESS_COUNT` with `os.fork()`.
- Row-level locking (`SELECT ... FOR UPDATE SKIP LOCKED`) for safe concurrent processing.
- Automatic AMI reconnection on disconnect.
- Configuration via environment variables and CLI arguments.
- `--dump_config` flag for configuration verification.
- Dial status lifecycle: NEW -> PENDING -> ANSWERED/BUSY.
- AMI event listener for `DialEnd` events tracking.
- `test_insert.py` utility for inserting test callback entries.
- Systemd unit file (`Callback.service`) for production deployment.
- Signal handling (SIGTERM, SIGINT) for graceful shutdown.
