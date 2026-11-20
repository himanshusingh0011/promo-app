"""Builds two short, made-up sample episodes (original text, not Kuku content) in the
screenplay format. Used by the unit tests and by the 'Try a sample' button on the web app.

    python tests/make_sample.py
"""
from pathlib import Path

EP1 = ("Episode 1", "Mara, a waitress at her ex-fiance's engagement party, is humiliated in front of the guests, until a stranger calls her by a name nobody has used in ten years.", [
    ("SCENE", "INT. GRAND HOTEL BALLROOM - NIGHT"),
    ("CAMERA", "", "Wide shot of a glittering ballroom, guests in evening wear raising glasses.", 0.0, 3.0),
    ("ACTION", "", "Mara, in a plain black waitress uniform, carries a tray of champagne through the crowd.", 1.0, 4.0),
    ("CAMERA", "", "Close-up on Mara's hands trembling on the tray.", 3.0, 5.0),
    ("DIALOGUE", "VIVIAN (Mocking, Loud)", "Look, everyone. The girl Ethan dumped is serving our drinks.", 4.5, 8.0),
    ("CAMERA", "", "Medium shot of guests turning, laughing behind their hands.", 8.0, 10.5),
    ("DIALOGUE", "MARA (Quiet, Steady)", "I'm just doing my job, Vivian.", 9.0, 11.0),
    ("ACTION", "", "Vivian grabs a glass from the tray and throws the champagne in Mara's face.", 11.5, 13.5),
    ("SOUND FX", "", "A sharp splash and a collective gasp from the guests.", 11.8, 13.0),
    ("CAMERA", "", "Close-up on Mara, champagne dripping from her chin.", 13.5, 16.0),
    ("DIALOGUE", "VIVIAN (Cruel, Smug)", "Then do it on your knees. Clean it up.", 14.0, 16.5),
    ("CAMERA", "", "Medium shot of Ethan standing behind Vivian, saying nothing.", 16.5, 19.0),
    ("DIALOGUE", "MARA (Hurt, Accusing)", "Ethan. You're just going to stand there?", 17.0, 19.5),
    ("DIALOGUE", "ETHAN (Cold, Dismissive)", "You were never part of my world, Mara.", 20.0, 23.0),
    ("CAMERA", "", "Close-up on Mara swallowing her tears.", 23.0, 26.0),
    ("ACTION", "", "Mara slowly kneels and begins picking up broken glass.", 24.0, 28.0),
    ("DIALOGUE", "VIVIAN (Gloating)", "Good girl. Know your place.", 28.5, 30.5),
    ("SCENE", "INT. GRAND HOTEL BALLROOM - CONTINUOUS"),
    ("CAMERA", "", "Wide shot as the ballroom doors swing open.", 31.0, 34.0),
    ("SOUND FX", "", "Heavy doors bang open; the music stops dead.", 31.0, 32.5),
    ("ACTION", "", "A tall man in a dark suit walks in, flanked by four bodyguards.", 32.0, 36.0),
    ("DIALOGUE", "HOTEL MANAGER (Shocked, Whispering)", "That's Mr. Hale. He owns this hotel.", 36.5, 39.0),
    ("CAMERA", "", "Tracking shot following Hale as he walks straight past Ethan to Mara.", 39.0, 43.0),
    ("ACTION", "", "Hale kneels beside Mara and lifts her hand away from the broken glass.", 41.0, 45.0),
    ("DIALOGUE", "HALE (Gentle, Firm)", "You've cut your hand.", 45.5, 47.0),
    ("DIALOGUE", "VIVIAN (Confused, Indignant)", "Mr. Hale, she's just a waitress.", 47.5, 50.0),
    ("CAMERA", "", "Close-up on Hale turning his head toward Vivian, eyes cold.", 50.0, 52.5),
    ("DIALOGUE", "HALE (Icy, Menacing)", "Speak to her like that again and you'll never set foot in this city again.", 51.0, 56.0),
    ("CAMERA", "", "Close-up on Ethan, pale and stunned.", 56.0, 58.0),
    ("DIALOGUE", "ETHAN (Stunned)", "Why would you protect her?", 57.0, 59.0),
    ("CAMERA", "", "Close-up on Hale helping Mara to her feet.", 59.0, 62.0),
    ("DIALOGUE", "HALE (Quiet, Reverent)", "Because she's not a waitress.", 60.0, 62.0),
    ("DIALOGUE", "HALE (Clear, Announcing)", "Welcome home, Miss Sterling.", 62.5, 65.0),
    ("SOUND FX", "", "A gasp ripples across the ballroom; an ominous low string sting.", 65.0, 67.0),
    ("CAMERA", "", "Extreme close-up on Mara's eyes widening. Cut to black.", 65.0, 68.0),
])

EP2 = ("Episode 2", "The guests learn Mara is the missing Sterling heiress, and Vivian swears to expose her as a fraud before the night is over.", [
    ("SCENE", "INT. GRAND HOTEL BALLROOM - NIGHT"),
    ("CAMERA", "", "Wide shot of the frozen ballroom, every face turned toward Mara.", 0.0, 3.0),
    ("DIALOGUE", "VIVIAN (Hysterical, Laughing)", "Sterling? She's a liar! The Sterling girl died in that fire!", 0.5, 4.5),
    ("CAMERA", "", "Close-up on Mara, her hand going to a burn scar on her wrist.", 4.5, 7.0),
    ("ACTION", "", "Mara pulls her sleeve down over the scar.", 5.0, 7.0),
    ("DIALOGUE", "MARA (Shaken, Whispering)", "How do you know my name?", 7.5, 9.5),
    ("DIALOGUE", "HALE (Calm)", "Your grandfather never stopped looking for you.", 10.0, 13.0),
    ("CAMERA", "", "Medium shot of Ethan stepping forward, forcing a smile.", 13.0, 16.0),
    ("DIALOGUE", "ETHAN (Nervous, Charming)", "Mara, sweetheart. I always knew you were special.", 14.0, 17.5),
    ("ACTION", "", "Mara slaps Ethan hard across the face.", 18.0, 19.5),
    ("SOUND FX", "", "A loud crack of the slap echoes through the silent room.", 18.2, 19.0),
    ("CAMERA", "", "Close-up on Ethan holding his cheek in disbelief.", 19.5, 22.0),
    ("DIALOGUE", "MARA (Furious, Cold)", "Ten minutes ago I was beneath you.", 20.0, 22.5),
    ("DIALOGUE", "MARA (Furious, Cold)", "Now I'm your sweetheart?", 23.0, 25.0),
    ("CAMERA", "", "Medium shot of the guests murmuring, phones raised and recording.", 25.0, 28.0),
    ("DIALOGUE", "VIVIAN (Venomous, Threatening)", "Enjoy it while it lasts. I'll prove you're a fraud.", 28.5, 32.0),
    ("SCENE", "INT. HOTEL CORRIDOR - NIGHT"),
    ("CAMERA", "", "Low-angle shot of Vivian storming down a dim corridor, phone at her ear.", 33.0, 37.0),
    ("DIALOGUE", "VIVIAN (Low, Urgent)", "The DNA records from the fire. I need them destroyed by morning.", 36.0, 40.0),
    ("DIALOGUE", "UNKNOWN VOICE (V.O.) (Calm, Menacing)", "That will cost you more than money, Vivian.", 40.5, 44.0),
    ("CAMERA", "", "Close-up on Vivian hesitating, then nodding.", 44.0, 47.0),
    ("DIALOGUE", "VIVIAN (Determined)", "Whatever it takes.", 45.0, 46.5),
    ("SCENE", "INT. HOTEL SUITE - NIGHT"),
    ("CAMERA", "", "Wide shot of a luxurious suite; Mara stands at the window.", 48.0, 51.0),
    ("DIALOGUE", "HALE (Gentle)", "You should rest. Tomorrow you meet your grandfather.", 49.0, 52.5),
    ("DIALOGUE", "MARA (Uncertain)", "What if he doesn't believe me?", 53.0, 55.0),
    ("CAMERA", "", "Close-up on Hale, something unreadable in his eyes.", 55.0, 58.0),
    ("DIALOGUE", "HALE (Quiet)", "He will. I made sure of it.", 56.0, 58.0),
    ("ACTION", "", "Hale leaves. Mara notices an envelope on the table with her real name on it.", 58.5, 62.0),
    ("ACTION", "", "Mara opens it and finds a photo of herself as a child, standing in front of the burning house, with Hale beside her.", 62.0, 67.0),
    ("DIALOGUE", "MARA (Horrified, Whispering)", "He was there... the night of the fire?", 67.0, 70.0),
    ("SOUND FX", "", "A sharp ominous string sting; the lights flicker.", 70.0, 71.5),
    ("CAMERA", "", "Push-in on the photo. Cut to black.", 70.0, 72.0),
])


def ts(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def render(num_title, logline, rows):
    out = [f"EPISODE NUMBER: {num_title}", f"EPISODE LOGLINE: {logline}",
           "CONTINUITY NOTES: Made-up sample for testing.", "", "--- SCRIPT START ---", ""]
    scene_no = 0
    for r in rows:
        if r[0] == "SCENE":
            scene_no += 1
            out += [f"SCENE {scene_no:02d}", f"Scene heading: {r[1]}", "", "Actions and dialogue:", ""]
            continue
        kind, who, text, a, b = r
        label = {"CAMERA": "CAMERA", "ACTION": "ACTION", "SOUND FX": "SOUND FX"}.get(kind, who)
        body = f'"{text}"' if kind == "DIALOGUE" else text
        out += [f"**{label}:**", f"Start: ({ts(a)}) | End: ({ts(b)})", body, ""]
    out.append("--- SCRIPT END ---")
    return "\n".join(out)


if __name__ == "__main__":
    d = Path(__file__).resolve().parent.parent / "public" / "sample"
    d.mkdir(parents=True, exist_ok=True)
    for i, ep in enumerate((EP1, EP2), 1):
        (d / f"sample-episode-{i:03d}.txt").write_text(render(*ep), encoding="utf-8")
    print("wrote", d)
