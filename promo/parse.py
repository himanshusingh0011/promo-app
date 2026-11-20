"""Screenplay parser: turns one episode .txt into timed events.

Format (Kuku screenplays):
    EPISODE NUMBER: Episode 1
    EPISODE LOGLINE: ...
    SCENE 01 / Scene heading: ... / Scene start: 00:00.00
    **CAMERA:** | **ACTION:** | **SOUND FX:** | **NAME (Tone, Tone):**
    Start: (00:11.30) | End: (00:13.10)
    text...
Pure code, no AI: timestamps must never be invented by a model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

KIND_LABELS = {"CAMERA": "camera", "ACTION": "action", "SOUND FX": "sfx", "SFX": "sfx", "SOUND": "sfx"}
VISIBLE = ("dialogue", "action", "sfx")  # what the AI sees; camera lines are only used for cut points

_TS = r"(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)"
RE_TIMES = re.compile(r"Start:\s*\(?\s*" + _TS + r"\s*\)?\s*\|\s*End:\s*\(?\s*" + _TS + r"\s*\)?", re.I)
RE_LABEL = re.compile(r"^\*\*(.+?):?\*\*\s*$")
RE_SCENE = re.compile(r"^SCENE\s+(\d+)", re.I)
RE_EPNUM = re.compile(r"EPISODE NUMBER:\s*(?:Episode\s*)?(\d+)", re.I)
RE_FILE_EP = re.compile(r"episode[-_ ]?(\d+)", re.I)


def ts_to_sec(h, m, s) -> float:
    return int(h or 0) * 3600 + int(m) * 60 + float(s)


def fmt_ts(sec: float) -> str:
    sec = max(0.0, sec)
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Event:
    idx: int            # position in episode (0-based, includes camera lines)
    kind: str           # dialogue | action | sfx | camera
    text: str
    start: float
    end: float
    scene: int = 1
    speaker: str = ""
    tone: str = ""
    lid: int = 0        # short id shown to the AI (1-based, visible lines only; 0 for camera)

    def label(self) -> str:
        if self.kind == "dialogue":
            return f"{self.speaker} ({self.tone})" if self.tone else self.speaker
        return {"action": "ACTION", "sfx": "SFX", "camera": "CAMERA"}[self.kind]


@dataclass
class Episode:
    number: int
    name: str
    logline: str = ""
    continuity: str = ""
    events: list[Event] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return max((e.end for e in self.events), default=0.0)

    @property
    def visible(self) -> list[Event]:
        return [e for e in self.events if e.kind in VISIBLE]

    @property
    def shots(self) -> list[Event]:
        return [e for e in self.events if e.kind == "camera"]

    def by_lid(self) -> dict[int, Event]:
        return {e.lid: e for e in self.visible}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration"] = self.duration
        return d


def _split_label(raw: str) -> tuple[str, str, str]:
    """'MATRIARCH (O.S.) (Firm)' -> ('dialogue', 'MATRIARCH', 'Firm')."""
    raw = raw.strip().rstrip(":").strip()
    up = raw.upper()
    if up in KIND_LABELS:
        return KIND_LABELS[up], "", ""
    groups = re.findall(r"\(([^)]*)\)", raw)
    speaker = re.sub(r"\(.*", "", raw).strip()
    tones = [g for g in groups if g.strip().upper().replace(".", "") not in ("OS", "VO", "CONTD", "CONT'D", "OC")]
    return "dialogue", speaker, (tones[-1].strip() if tones else "")


def parse_text(text: str, name: str = "episode.txt") -> Episode:
    text = text.replace("\r\n", "\n").replace("﻿", "")
    m = RE_EPNUM.search(text) or RE_FILE_EP.search(name)
    number = int(m.group(1)) if m else 0
    ep = Episode(number=number, name=name)
    for line in text.split("\n")[:12]:
        if line.upper().startswith("EPISODE LOGLINE:"):
            ep.logline = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CONTINUITY NOTES:"):
            ep.continuity = line.split(":", 1)[1].strip()

    scene = 1
    cur: dict | None = None
    last_end = 0.0

    def flush():
        nonlocal cur, last_end
        if cur and (cur["text"] or cur["kind"] == "camera"):
            body = " ".join(cur["text"]).strip()
            if cur["kind"] == "dialogue":
                body = body.strip().strip('"').strip("“”").strip()
            start = cur["start"] if cur["start"] is not None else last_end
            end = cur["end"] if cur["end"] is not None else start + 2.0
            ep.events.append(Event(idx=len(ep.events), kind=cur["kind"], text=body, start=start,
                                   end=max(end, start), scene=scene, speaker=cur["speaker"], tone=cur["tone"]))
            last_end = max(last_end, end)
        cur = None

    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("--- SCRIPT"):
            flush()
            continue
        ms = RE_SCENE.match(s)
        if ms:
            flush()
            scene = int(ms.group(1))
            continue
        ml = RE_LABEL.match(s)
        if ml:
            flush()
            kind, speaker, tone = _split_label(ml.group(1))
            cur = {"kind": kind, "speaker": speaker, "tone": tone, "start": None, "end": None, "text": []}
            continue
        if cur is None:
            continue
        mt = RE_TIMES.search(s)
        if mt and cur["start"] is None:
            g = mt.groups()
            cur["start"], cur["end"] = ts_to_sec(*g[:3]), ts_to_sec(*g[3:])
            continue
        if s:
            cur["text"].append(s)
        elif cur["text"]:
            flush()
    flush()

    ep.events.sort(key=lambda e: (e.start, e.idx))
    lid = 0
    for i, e in enumerate(ep.events):
        e.idx = i
        if e.kind in VISIBLE:
            lid += 1
            e.lid = lid
    return ep


def parse_file(path) -> Episode:
    from pathlib import Path
    p = Path(path)
    return parse_text(p.read_text(encoding="utf-8", errors="replace"), p.name)


def compact_line(ep: Episode, e: Event, max_chars: int = 220) -> str:
    """One short line per event for the AI prompt (about half the tokens of the raw script)."""
    body = e.text if len(e.text) <= max_chars else e.text[: max_chars - 3] + "..."
    if e.kind == "dialogue":
        body = f'"{body}"'
    return f"[{ep.number}.{e.lid} @{fmt_ts(e.start)[:5]}] {e.label()}: {body}"


def compact_episode(ep: Episode) -> str:
    head = f"### EPISODE {ep.number} ({fmt_ts(ep.duration)[:5]} long)\nLogline: {ep.logline}\n"
    return head + "\n".join(compact_line(ep, e) for e in ep.visible)
