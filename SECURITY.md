# Security policy

## Reporting a vulnerability

**Please do not report it in public.** Use GitHub's private vulnerability
reporting on this repository: the **Security** tab, then *Report a
vulnerability*. It reaches only the maintainer and does not require
exchanging email addresses. If it is unavailable to you, get in touch through
**[radioterapia.ai](https://radioterapia.ai)** and say only that you have a
security report; the details can then move to a private channel.

**Never attach patient data**, here or anywhere else: no DICOM series, no
RTSTRUCT, no screenshot of a patient image, no log with a patient ID, a UID
or a series path. Describe the problem in words, or reproduce it with the
synthetic phantoms the batteries build.

## What is in scope

The code in this repository: the engine, the folder watcher, *Run now* and
*View segmentation*. The installer, the updater and the shell shared by the
six apps live in the [Local Suite](https://github.com/drhenriquebraga/local-suite)
repository; a finding there can be reported here or there. The findings that
matter most:

- Anything that sends an image, a structure or a patient identifier off the
  workstation. There is no upload function, by design.
- Anything that makes the engine write somewhere other than the destination
  configured for the series.
- Anything that makes a structure reach the planning system marked as
  approved, or a detection task run without the operator's declared act.

The segmentation models and the third-party libraries are their authors'
work: a problem in one of them belongs with its authors, listed in
[NOTICE](NOTICE).

## Not a medical device

Teaching and research material, not a medical device, not validated for
clinical use: a clinically wrong result is a correctness bug, not a
vulnerability, and is welcome through
**[radioterapia.ai](https://radioterapia.ai)**, without patient data.

## Supported versions

The latest Local Suite release, and the tag of this app that it pins.
Single maintainer, no backports.
