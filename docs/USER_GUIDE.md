# UT-Analyst User Guide

## Startup and Login

The system creates the first administrator on first launch. Subsequent launches
use local accounts managed by the administrator. The system provides
administrator, engineer, operator, and viewer roles, with role-based access to
detection, configuration, record management, report editing, user management,
and audit functions.

## Detection

1. Configure the probe, gain, range, Gate A, and independent Gate B/C settings.
2. Build TCG depth/gain profiles for amplitude compensation.
3. Start live acquisition or perform a single-shot acquisition.
4. Enable defect recording to collect traceable depth, amplitude, time, and
   waveform-snapshot records.
5. Review gate peaks, cursor measurements, defect statistics, and B/C-Scan
   imagery in the analysis panels.

Live acquisition runs on a worker thread. Acquisition frames and processing
metadata are written to the session store for later replay and analysis.

## Replay

Open `View -> Data Replay`, select a session, and navigate through stored
frames. Playback supports previous/next navigation, slider positioning, speed
selection, and loop playback. Saved base waveforms remain available for
reprocessing with filtering and TCG settings. Valid session chunks are retained
when other chunks require recovery.

## Reports

Create a report from the current frame and fill in the standard, workpiece,
company, project, personnel, location, and notes fields. HTML and PDF reports
share the same content and include the detection summary, waveform overview,
defect snapshots, report hash, and signer information. The database records the
final file SHA-256, report format, path, signing user, signing time, and
signature.

## Audit

Session start/stop, defect changes, report export, and report signatures create
audit events linked by a previous-hash chain. The audit viewer displays the
event history and verifies that historical records have not been altered.

## Advanced Features

- Gate A/B/C support independent enablement, position, width, threshold, and
  visual state.
- B/C-Scan provides raster position mapping, grid imaging, and amplitude
  distribution views.
- User administration supports local account creation and role assignment.
- Report and audit records preserve the active user identity for traceability.
