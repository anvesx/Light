"""Plain language detection for brain sources: English, Hindi, romanised Hindi mixed with English, or a mix of scripts."""
import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")
WORDS = re.compile(r"[a-z]+")
HINDI_WORDS = frozenset("""hai hain nahi nahin karna karni kya matlab aur bhi kar karo karenge karega karenge kiya hoga hogi
honge chahiye chahie tha thi mein ka ki ke accha acha theek abhi kal haan bhejo bhej dena dedo lena wala wale sab kuch koi lekin
yeh woh hum hamare aap aapko mujhe humein isko jaldi paisa bahut zyada kaam batao bata dekho dekh raha rahi rahe sakte sakta
chalega chalo samajh pehle baad phir kyun kaise kaun""".split())


def detect_language(text):
    """Return "en", "hi", "hinglish" or "mixed". Devanagari is Hindi; Latin letters beside it make it "mixed"."""
    dev, latin = len(DEVANAGARI.findall(text)), len(LATIN.findall(text))
    if dev:
        return "mixed" if latin > 0.3 * (dev + latin) else "hi"
    words = WORDS.findall(text.lower())
    hits = sum(1 for w in words if w in HINDI_WORDS)
    if hits >= 2 or (hits == 1 and len(words) <= 8):
        return "hinglish"
    return "en"
