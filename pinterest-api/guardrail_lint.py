# VERBATIM COPY of obenpaper-guardrail-lint/scripts/guardrail_lint.py (1 Oct 2026).
# The skill is the source: when its word lists change, copy the file here again
# unchanged. validate_queue.py imports WORDLISTS and HEADLINE_WATCH from it.
#!/usr/bin/env python3
"""
Obenpaper guardrail linter.

Scans draft copy (listing text, pin copy, product page copy) for terms
that violate a product line's non-medical / non-fertility / non-treatment
guardrail. This is a FLAGGING tool, not an auto-fixer -- a flagged term
isn't automatically wrong, it just needs a human (Luc) judgment call or
a nearby disclaimer.

Usage:
    python guardrail_lint.py <line> <path-to-text-file>
    python guardrail_lint.py <line> -   (reads stdin)

<line> is one of: in_tune_en, in_tune_fr, in_check, at_ease, in_focus,
            finance, in_hand, fitness, tools, general
"""
import re
import sys

WORDLISTS = {
    "in_tune_en": [
        "contraception", "contraceptive", "fertility",
        "trying to conceive", " ttc ",
        "prevent pregnancy", "achieve pregnancy",
    ],
    "in_tune_fr": [
        "symptothermie", "fertilité", "glaire cervicale",
        "pma", "fiv", "conception", "contraception",
        # ovulation flagged separately below as a headline-context check
    ],
    "in_check": [
        "treatment", "therapy", "cure", "rehab", "rehabilitation",
        "diagnos",  # catches diagnose/diagnosis/diagnosed
    ],
    "at_ease": [
        "physiotherapy", "physical therapy", "medical treatment",
    ],
    "finance": [
        # Well Spent, In Hand's Money module, Budget Planner, In Order.
        # The product plans money; it never tells anyone what to do with it.
        "financial advice", "investment advice", "we recommend you invest",
        "guaranteed return", "guaranteed savings", "risk-free",
        "pay off your debt faster than", "best way to pay off",
        "should invest", "should refinance", "consolidate your debt",
        "get out of debt guaranteed", "will make you money",
        "beat inflation", "tax advice",
    ],
    "in_focus": [
        # ADHD-adjacent. Support for starting, never a clinical intervention.
        "treatment", "therapy", "cure", "symptoms of adhd", "diagnos",
        "manage your adhd", "adhd management", "clinically proven",
        "replaces medication", "instead of medication",
    ],
    "in_hand": [
        # All-in-one Life OS carrying Health, Mind, Sleep, Brain Dump and Money
        # modules at once — the widest guardrail surface of any product.
        "diagnos", "treatment", "therapy", "cure", "clinically proven",
        "medical advice", "financial advice", "investment advice",
        "guaranteed return", "risk-free",
        "will fix your sleep", "cures anxiety", "treats depression",
        "mental health treatment", "replaces professional",
    ],
    "fitness": [
        # 30-Day Fitness Challenges (Tza97) and Summer Shred.
        # THE RULE: the six body-composition PAGE NAMES are labels, not
        # claims — they stay as page titles and sit in HEADLINE_WATCH below.
        # What is off-limits is the PROMISE: an outcome the product cannot
        # deliver, or pressure the product deliberately does not apply.
        "weight loss", "lose weight", "transform your body", "bikini body",
        "calorie deficit", "meal plan", "diet plan", "guaranteed results",
        "no excuses", "push through the pain", "inches off", "burn fat fast",
        "shred fat", "before and after",
    ],
    "tools": [
        # The /tools route — "Try the numbers", ten free calculators, built
        # 15 Aug 2026. One surface carrying fitness, sleep and money at once,
        # so it inherits from three lines rather than owning one guardrail.
        #
        # ⚠ CALORIES ARE NOT OFF-LIMITS HERE. Luc's decision, 15 Aug 2026:
        # the macro tool may show a maintenance figure. What is off-limits is
        # the TARGET — a deficit, a goal weight, a rate of loss — because that
        # turns a description of what a body burns into an instruction.
        "calorie deficit", "goal weight", "target weight", "rate of loss",
        "lose weight", "weight loss", "meal plan", "diet plan",
        "how many calories to lose", "cut calories to",
        # The sleep tool is clock arithmetic on purpose. Cycle language gives
        # soft science a precise face.
        "sleep cycle", "90-minute", "ninety-minute", "wake up refreshed if",
        "best time to fall asleep",
        # The compound-interest tool inherits the finance non-advice line.
        "financial advice", "investment advice", "guaranteed return",
        "risk-free", "you should invest", "beat inflation",
    ],
    "general": [
        "will cure", "guaranteed to fix", "medical advice",
        "financial advice", "will fix your",
    ],
}

# Terms that are fine as a *named phase/section label* but flagged if they
# read like a headline/selling point. Reported separately since context matters.
HEADLINE_WATCH = {
    "in_tune_en": ["ovulation", "ovulatory"],
    "in_tune_fr": ["ovulation"],
    # Fine as a tracked field or section label; flagged if it reads as a claim
    # about what the product does to the condition.
    "in_focus": ["adhd", "focus problems", "executive function"],
    "in_hand": ["anxiety", "depression", "insomnia", "burnout", "debt-free"],
    "finance": ["debt-free", "savings goal", "payoff"],
    # The six body-composition page names. They are the product's real page
    # titles and they keep their words — flagged so a listing does not turn a
    # page name into a selling point.
    "fitness": [
        "slim thighs", "flat abs", "fat burn", "booty build",
        "toned arms", "cardio burn", "summer shred",
    ],
    # Fine as an output label on the tool itself; flagged if it reads as a
    # promise about what the number will do for the reader.
    "tools": [
        "calories", "macros", "metabolism", "maintenance",
        "sleep", "compound interest",
    ],
}


def lint(line_key, text):
    if line_key not in WORDLISTS:
        print(f"Unknown line '{line_key}'. Options: {', '.join(WORDLISTS)}")
        sys.exit(1)

    # ⚠ WHITESPACE IS FLATTENED BEFORE MATCHING. A multi-word term straddling
    # a line break was silently missed — "trying to\nconceive" did not match
    # "trying to conceive", which is exactly the copy a wrapped paragraph
    # produces. Found by testing in v73, and absent again from the installed
    # copy on 15 Aug 2026, so it is restored here. Match and report against
    # the flattened text so the offsets stay meaningful.
    text = re.sub(r"\s+", " ", text)
    lower = text.lower()
    hits = []
    for term in WORDLISTS[line_key]:
        for m in re.finditer(re.escape(term.lower()), lower):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            hits.append((term, text[start:end].strip()))

    watch_hits = []
    for term in HEADLINE_WATCH.get(line_key, []):
        for m in re.finditer(re.escape(term.lower()), lower):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            watch_hits.append((term, text[start:end].strip()))

    print(f"Guardrail lint — line: {line_key}\n" + "-" * 40)
    if not hits and not watch_hits:
        print("No flagged terms found. Still eyeball for tone/framing —")
        print("this catches literal terms, not implied claims.")
        return True

    if hits:
        print(f"\n{len(hits)} flagged term(s) — off-limits or needs a disclaimer nearby:")
        for term, ctx in hits:
            print(f'  [\"{term}\"] ...{ctx}...')

    if watch_hits:
        print(f"\n{len(watch_hits)} headline-context term(s) — OK as a phase/section")
        print("name described by energy, NOT OK as a headline/selling point:")
        for term, ctx in watch_hits:
            print(f'  [\"{term}\"] ...{ctx}...')

    print("\nReview each hit: is it framed as an estimate/awareness note with")
    print("the required disclaimer nearby, or is it a bare claim? Fix before delivering.")
    return False


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    line_key = sys.argv[1]
    src = sys.stdin if sys.argv[2] == "-" else open(sys.argv[2], encoding="utf-8")
    text = src.read()
    ok = lint(line_key, text)
    sys.exit(0 if ok else 1)
