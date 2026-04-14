from typing import List, Dict


def build_story_scenes(name: str, gender: str) -> List[Dict[str, str]]:
    pronoun = "they"
    possessive = "their"
    if gender.lower() == "boy":
        pronoun = "he"
        possessive = "his"
    elif gender.lower() == "girl":
        pronoun = "she"
        possessive = "her"

    return [
        {
            "title": "The Whispering Woods",
            "story_text": f"One golden morning, {name} entered the Whispering Woods where leaves hummed gentle songs. A glowing path appeared beneath {possessive} feet and invited {pronoun} to follow.",
            "prompt": f"A children's storybook illustration of a young {gender} named {name}, magical forest trail with glowing leaves, full body, cartoon style, vibrant colors, consistent face, cinematic composition",
        },
        {
            "title": "The River of Stars",
            "story_text": f"At the forest edge, {name} found a sparkling river that reflected the night sky in daylight. Tiny fish made of starlight leapt from wave to wave and guided {pronoun} onward.",
            "prompt": f"A children's storybook illustration of a young {gender} named {name}, standing by a river filled with starlight fish, whimsical fantasy, cartoon style, vibrant colors, consistent face",
        },
        {
            "title": "The Friendly Dragon",
            "story_text": f"Near a hill of wildflowers, a small dragon appeared and bowed politely to {name}. With a cheerful grin, it offered to fly {name} above the clouds to find the hidden lantern tower.",
            "prompt": f"A children's storybook illustration of a young {gender} named {name}, friendly small dragon in a flower meadow, joyful expression, cartoon style, vibrant colors, consistent face",
        },
        {
            "title": "The Lantern Tower",
            "story_text": f"From the sky, {name} saw an ancient tower whose lantern had gone dark. {pronoun.capitalize()} climbed the winding steps and relit the lantern with courage, making the valley glow again.",
            "prompt": f"A children's storybook illustration of a young {gender} named {name}, relighting an ancient tower lantern at sunset, heroic mood, cartoon style, vibrant colors, consistent face",
        },
        {
            "title": "A Promise Under the Moon",
            "story_text": f"That evening, the whole valley shimmered with gratitude as {name} returned home. Under a silver moon, {name} promised to keep exploring, helping, and believing in magic wherever {pronoun} goes.",
            "prompt": f"A children's storybook illustration of a young {gender} named {name}, moonlit village celebration with floating lanterns, warm ending, cartoon style, vibrant colors, consistent face",
        },
    ]
