# UT-Analyst User Guide

## Startup and Login

Create the first administrator on the first launch. Later launches require a
local account. Roles are administrator, engineer, operator, and viewer.

## Detection

1. Configure probe, gain, range, gate A, and optional Gate B/C settings.
2. Enable TCG and enter depth/gain points when compensation is required.
3. Start live acquisition or perform a single-shot acquisition.
4. Enable defect recording before collecting traceable defect records.

Live acquisition runs on a worker thread. The interface only renders and saves
the frames delivered by the acquisition source.

## Replay

Open `View -> Data Replay`, select a saved session, and choose a frame. Playback
supports speed selection and previous/next navigation. The original waveform is
stored independently from filtering and TCG processing.

## Reports

Create a report from the current frame and fill in the standard, workpiece,
company, project, personnel, location, and notes fields. HTML and PDF use the
same report content. Exporting a report records its SHA-256 hash and signs it
with the active user.

## Audit

Session start/stop, defect changes, and report signatures create audit events.
The audit chain verification detects changes to historical events.
