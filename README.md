# ContourLab

**Part of the Radioterapia.AI Local Suite. ContourLab: several third-party AI segmentation models on the same exam, saved as unapproved RTSTRUCT suggestions — teaching and research material, not a medical device.**

`License: Apache-2.0` · `Component of: Radioterapia.AI Local Suite` · `Platform: Windows 10 and 11, 64-bit`

> **Teaching and research material. This is not a medical device.**
> It is **not** validated for clinical use, it has no ANVISA registration, no
> CE mark and no FDA clearance, and it must not be used as a production
> contouring tool. Every structure it writes is an **unapproved suggestion**
> (`ApprovalStatus = UNAPPROVED`); reviewing and approving it is a
> physician's act, in the planning system. Detection of findings is available
> and never runs by default: only by a declared act of whoever operates it,
> series by series. The model that draws the anatomy here —
> [TotalSegmentator][ts] — says the same about itself, in its own README:
> *"This is not a medical device and is not intended for clinical usage."*
> See [NOTICE](NOTICE).

## What it does

ContourLab is the segmentation module of the suite, and its flagship. It runs
third‑party models over a CT (or an MR) on the department's own Windows
workstation, turns what they draw into radiotherapy structures, and writes an
RTSTRUCT beside the series, so that the planning system imports them as
suggestions to review. It can also run several models over the same scan and
put their results side by side. The models are not trained on the
department's cases.

It has two tools and a night shift:

- **Run now** — pick a folder in the series pop‑up that opens on arrival;
  the folder is read in the background, with a filter by date, the series
  appear as they are found, and the pop‑up closes on its own when the
  reading ends. Choose the mode of each series, and start. The start dialog
  states that nothing comes out approved.
- **View segmentation** — the series, CT or MR, is chosen in a pop‑up over
  the work screen (the local archive, or a folder read in the background);
  two viewers side by side, one file per viewer, with slice, window and zoom
  locked together. The label map of a 3D
  study opens as one more set, and the visible set can be sent to the 3D
  Reconstructions module.
- **The night watcher** scans the folder of CT series set in *Settings →
  Folders and port* (or in the *Overnight Run* sheet) and runs AUTO on what
  arrives, one series at a time. Several workstations can
  share the same folder: they coordinate by marker files beside each series,
  with no central server. The *Overnight Run* enters the queue last, reads
  the folder it was given, puts the suggested series of each exam in AUTO
  (the same choice *Run now* makes; an MR only when the exam has no CT),
  processes them, reads the folder again when the queue empties, and keeps
  the workstation awake while it is open. It does not touch the
  workstation's programs or services.

There is one queue per workstation, and it lives in the Suite: what is put in
by hand (*Run now*, and series sent by the DicomBridge and Nidus RT modules)
and what the watcher found wait in the same bar, one segmentation at a time.
ContourLab is the executor.

### Three modes, series by series

| mode | where | what runs | what it writes |
|---|---|---|---|
| **FAST** | *Run now* | the anatomy base, plus, on a chest, the few tasks its own structures need | only `RadAI_STUDY_Fast` |
| **AUTO** | *Run now*, and always the night watcher | the base, then the tasks of each body region the base found; the CT brain model when the brain is in the field; the cervical nodal levels when the neck is confirmed in the field | `RadAI_FULL` + `RadAI_STUDY` |
| **CUSTOM** | *Run now* | protocols switch their own tasks on, any task can be switched on or off by hand, or a custom protocol of the workstation chooses the delivered structures; model comparison on request, and any structure can be dropped from the delivered set for that series | `RadAI_FULL` + `RadAI_STUDY` + the sets you asked for |

The anatomy base is TotalSegmentator's `total_v3` on CT and `total_mr` on MR.
What the base drew — not the text of the exam — decides which region tasks
AUTO adds.

### What each series gets

- **The complete set** (`RadAI_FULL`) is where all the post‑processing
  happens: parts and composites, margins, and the structures built from
  others — the radiotherapy heart, the bowel bags, the chest wall, the femur
  cut at the ischial tuberosity, the rectum split from the colon, the eye
  globe with its lens, the larynx, the two temporomandibular joints (left
  and right split by a midline plane through the skull, or, failing it, the
  brain, C1 or C2; the log says which), the two lungs summed and the
  mandible filled.
- **The delivered set** (`RadAI_STUDY`) is an exact **selection** of the
  complete one: the structures on an allow‑list, copied without rewriting.
  Its parotids come only from the nodal levels (level VIII minus the
  sternocleidomastoid); without the levels — in FAST, for example — it has
  no parotid, and the TotalSegmentator parotids stay in the complete set as
  `Parotid_L_ts` and `Parotid_R_ts`. The optic nerves, the optic chiasm,
  the pharyngeal constrictors and the thyroid keep their thin shape (no mask
  smoothing, no point reduction). The radiotherapy heart never loses a pixel
  of the pericardium, of the model's heart or of the pericardial effusion:
  the inferior vena cava leaves it only where it stands apart from them,
  and the oesophagus and the other neighbours outside the pericardium are
  taken out at the end. The bowel bag of the delivered set has the hole of
  each axial slice filled at the end. On a head and neck series without the
  chest, the summed lungs stand for the two lungs; the brain drawn on an MR
  stays in the complete set. A workstation can give the delivered
  structures its own names (each keeps its standard name in its
  description, and every reader decides by that name), or deliver its own
  selection with a custom protocol, in CUSTOM. If nothing is left for the
  delivered set — an MR where only the brain would come out —, the complete
  set is the delivery and the series is done.
- **Only when asked for, in CUSTOM**: the raw TotalSegmentator set
  (`RadAI_TS`, no post‑processing at all), the three comparison engines
  (NV‑Segment‑CT, CADS and MOOSE, each in a file of its own), the nodal
  levels' own file, and each optional task in a file of its own.

Before post‑processing, a few rules drop what should not be recorded at all —
such as a large organ that appears only in the edge slices of the scan, small
islands of an organ that is normally one piece, or anything entirely outside
the body. Each removal goes to the log and to the case registry, with the rule
and the volume.

Every RTSTRUCT is written in Implicit VR Little Endian, with every contour in
the plane of the series' own slices — an MR drawn on sagittal or oblique
slices gets its contours on those slices, and an axial series comes out as it
always did. Sets written by earlier versions (`RadAI_OAR`, `RadAI_OAR_Fast`,
`STUDY_full`) are still read, and a series segmented with them still counts
as done. Repeated vertices are
removed, a zero‑area contour (a one‑pixel‑wide slice) is redrawn from the
pixel outline, never dropped, and a contour that smoothing or point reduction
made cross itself goes back to its shape before them; the log says how many of
each were fixed, and how many still cross themselves. The delivered set is
written first and the complete set after it; each file is written whole or
not at all. The contour data goes into each file already converted, through
rt‑utils' own functions — the same RTSTRUCT that rt‑utils' own `add_roi`
writes (compared tag by tag, apart from UIDs and dates, on two chest CTs),
with 37 to 40% less CPU in the assembly; a battery
(`tools/test_velocidade.py`) compares every mask and every ROI of a synthetic
phantom with the `add_roi` path, value by value, and with a stored reference. A task whose memory estimate exceeds what the
workstation has free is skipped for that series, the rest is delivered, and
the queue card says which task was left out; the Suite's queue tries it again
later, when the workstation is idle.

**Detection is available, and never on by default.** The third‑party models
include tasks that look for findings (lung nodules, liver lesions). None of
them runs by omission: no region of AUTO contains one, no radiotherapy
protocol of CUSTOM switches one on, FAST never runs one, and the night watcher
always runs AUTO. Switching one on is a declared act — the task's own switch
in a series' CUSTOM panel, or a 3D Reconstructions study protocol, whose
output does not go to the planning system — and the log announces it with the
word `ACHADO`. A custom protocol that includes a finding asks for that
declaration every time the series is sent to the queue.

**The cervical nodal levels** come from the model of Weissmann et al. (2023),
with the names of the consensus of Grégoire et al. (`Lvl_Ia` to `Lvl_VIII`),
on CT and only with the head in the field. They go to the complete set; level IVb of each side loses the clavicle of the same side before the union. Their
union, `LNL_UNION_ai`, goes to the delivered set, and that is a **declared
risk**: it is described in the file as an unapproved anatomical union that is
neither an OAR nor a CTV — the elective volume is a medical decision.

## Four technical guarantees

These are properties of the files it writes, and anyone can check them by
opening those files.

- **Nothing comes out approved.** `ApprovalStatus = UNAPPROVED` in every
  file, and a provenance suffix on every structure name (`_ai`, `_ts`, `_nv`,
  `_cds`, `_mse`, `_lnl`, and a three‑letter one for each optional task, all
  listed in [NOTICE](NOTICE)). There is no path through the program that
  produces an approved structure.
- **No external contour is declared.** No output set contains `BODY`,
  `External` or an equivalent, and no ROI is written as `EXTERNAL` — organs
  are `ORGAN`, the nodal levels and their union are `CONTROL`. The refusal
  lives inside the function that writes the RTSTRUCT
  (`engine.conferir_sem_body`), not in a screen. `Skin` is a 5 mm shell, and
  a shell does not give a usable dose calculation on its own.
- **Separate series, never the original.** Each set is written as its own
  series, alongside. The CT the planning system holds is never touched.
- **The metrics measure divergence between models, not accuracy.** Without an
  approved reference contour there is no measure of correctness.

## What is ours, and what is not

**The segmentation models are not ours.** We did not train them. The
TotalSegmentator draws the anatomy; the other models draw what the table
says. What this component builds is the accessibility layer around them —
running them on the workstation, post‑processing, grouping, naming,
building the structures a plan uses, and putting the results next to each
other. We integrate:

| component | code | weights |
|---|---|---|
| [TotalSegmentator][ts] | Apache‑2.0 | Apache‑2.0 |
| [nnU‑Net][nnunet] | Apache‑2.0 | — |
| [NV‑Segment‑CT][nv] (NVIDIA) | Apache‑2.0 (MONAI bundle) | NVIDIA Open Model License — commercial use allowed; the model card says research, not clinical use |
| [CADS][cads], `open` variant | Apache‑2.0 | CC BY‑SA 4.0 |
| [MOOSE][moose] | Apache‑2.0 | CC BY 4.0 — attribution required |
| [Head & neck nodal levels][hnlnl] (Weissmann et al., 2023) | CC0‑1.0 | CC0‑1.0 |
| [CT brain structures][buti] (Buti et al., 2025) | — | MIT |

No weight travels in this repository: the Suite's preparer downloads each one
from its original source, and from v8.7 on removes the optimiser state —
used only for training — from the TotalSegmentator checkpoints it downloads
and, in a new package, from the checkpoints of the nodal levels, the CT brain
model, MOOSE and CADS (the network weights identical byte by byte, the change
declared in [NOTICE](NOTICE)); the workstation accepts
either the original or the trimmed file. This repository carries one
third‑party file — the NV‑Segment‑CT label map read by one battery
(`tools/data/nv_segment_ct_labels.json`, Apache‑2.0, like every file of the
model's repository that is not a weight) — and a few lines of rt‑utils (MIT):
`engine._adicionar_roi` reproduces its ROI assembly with rt‑utils' own
functions. [NOTICE](NOTICE) credits both.

Making a model reachable is not a neutral act — it is what turns an available
library into something used in a clinic. That is why the unapproved status,
the provenance suffix and every refusal live inside the functions that write
the files, and not in a screen.

## Privacy

Everything runs locally, on the workstation. **No image is sent to an external
server**, and there is no upload function: the NVIDIA hosted API is not used
for patient images, and a battery (`tools/test_rt.py`) fails if a path for an
image to leave is added. TotalSegmentator's own usage statistics, on by
default in the library, are switched off, both in its configuration file and
in the process that runs it. The per‑task cache of segmentation results stays
on the workstation (14 days, at most 20 GB). The connections the suite makes
on its own are listed in the Suite README and in the Privacy Policy shown in
the app.

## Part of the Local Suite

ContourLab does not run on its own. The shared shell — the entrance page, the
menus, the twelve languages, the Terms and the Privacy Policy, the
configuration, the case archive, DICOM reading, the viewers and the queue —
lives in the [Suite][suite], and on the workstation the suite is one program:
one process, one port, one `app` folder, assembled by the Suite's installer
from the seven repositories.

To use it, install the Suite with its light installer, from the
[releases of radioterapia-ai/local-suite][rel] (the permanent link to the
newest one is [`RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip`][latest]). Its
preparer downloads Python, the pinned libraries and every model weight from
the original sources; requirements and installation are in the Suite README.

This repository has no build of its own. The Suite's packager
(`build/empacotar_instalador.py --dos-repositorios`) downloads each component
at the tag pinned in `build/componentes.lock.json`, checks the SHA‑256 of its
extracted tree against the lock and
assembles the installer — see *Build from source* in the Suite README.

## Running the batteries

The batteries (`tools/test_*.py`, listed in `componente.json`) run over
synthetic phantoms. **No patient data is used anywhere in this repository, and
none may be committed to it.**

1. Put the [Suite][suite] and the six component repositories side by side in
   one folder. Folder names do not matter: the Suite is the folder with
   `tools/_componentes.py`, and each component is found by its
   `componente.json` (or set `RADAI_COMPONENTES_DIR` to the folder that holds
   the components). The batteries import modules of the Suite and of the
   other components, so all seven are needed.
2. Create the Suite's development environment: a Python virtual environment
   in `.venv` at the Suite root, as its README describes. It does not
   segment — segmentation runs with the Python, libraries and weights of a
   prepared package.
3. Run every battery of this component:

   ```
   <suite>\.venv\Scripts\python.exe <suite>\tools\_componentes.py --verificar <this folder>
   ```

   or a single one, with `--rodar test_<name>.py`. Each battery ends with an
   `OK:` or a `FALHOU:` footer, and `--verificar` ends with how many failed.
   `verify.cmd`, in this folder, does the same in two clicks once
   `_python.txt` (ignored by Git) holds the path of that `python.exe`.

4. **Turn on the pre‑commit hook** (once per clone):
   `git config core.hooksPath .githooks`. It runs the Suite's
   patient‑data scan over what is staged and refuses the commit that
   carries DICOM (with or without extension), a medical volume or a run
   log — and refuses it too when the scan cannot run, without the Suite
   beside this folder or without Python.

## Reporting a problem

A problem that is not a vulnerability goes through
**[radioterapia.ai](https://radioterapia.ai)**. Include the Local Suite
version, the Windows version, the screen language and the step that
failed — and **never patient data**: no DICOM series, no screenshot of a
patient image, no log with a patient ID, a UID or a series path. A problem
reproduced with the synthetic phantoms of the batteries is the quickest to
fix.

## Security

Found something that exposes patient data or lets the program act where it
should not? **Do not report it in public.** Use GitHub's private
vulnerability reporting on this repository, described in
[SECURITY.md](SECURITY.md).

## Licence and name

The code is licensed under the [Apache License 2.0](LICENSE); the attribution
notices are in [NOTICE](NOTICE), which section 4(d) of the licence requires to
accompany every redistribution. As section 6 says, the licence grants no
permission to use the trade names of the Licensor — "Radioterapia.AI",
"Local Suite" and "ContourLab" included — except as required to describe the
origin of the work. A build you adapt is yours: name it as yours.

| | Published code | A service's own build |
|---|---|---|
| What it is | Teaching and research material | An in‑house tool the service adapts, validates and registers in its own jurisdiction |
| Medical device? | **No.** Not validated for clinical use | Whatever that service's validation and registration make it |
| Who answers for it | Whoever downloads, modifies and deploys it answers for their own build, made with the Suite's build path | The service that deploys it |

Built by Dr. Henrique Braga, radiation oncologist —
**[radioterapia.ai](https://radioterapia.ai)**.

[ts]: https://github.com/wasserth/TotalSegmentator
[nnunet]: https://github.com/MIC-DKFZ/nnUNet
[nv]: https://huggingface.co/nvidia/NV-Segment-CT
[cads]: https://github.com/murong-xu/CADS
[moose]: https://github.com/ENHANCE-PET/MOOSE
[hnlnl]: https://github.com/putzfn/HNLNL_autosegmentation_trained_models
[buti]: https://huggingface.co/GregoryButi/CT_Brain_Segmentation_Radiotherapy
[suite]: https://github.com/radioterapia-ai/local-suite
[rel]: https://github.com/radioterapia-ai/local-suite/releases
[latest]: https://github.com/radioterapia-ai/local-suite/releases/latest/download/RADIOTERAPIA_AI_LOCAL_SUITE_SETUP_LATEST.zip
