#!/usr/bin/env python3
"""
Turn pasted quiz text into a community quiz file.

This is the "publish from your phone" helper: it writes
quizzes/<category>/<id>.json in the exact schema build.py validates and signs.

Text format (same as the app's .txt importer, plus an optional explanation line):

    1. What is 2 + 2?
    a) 3
    b) 4
    c) 5
    d) 6
    Answer: b
    Explain: Because 2 + 2 = 4.

    2. The sun rises in the east.
    a) True
    b) False
    Answer: a

Rules: 2 options = True/False, 4 options = MCQ. "Answer:" is required.
"Explain:" is optional. "//" and "#" lines are ignored.

Usage:
  python3 add_quiz.py --id c-basics-002 --title "C Basics" --category Programming \
      --difficulty Medium --questions-file questions.txt
  python3 add_quiz.py ... --questions-text "1. ...\n"      # same thing inline
  python3 add_quiz.py --dry-run ...                        # validate, write nothing
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUIZZES_DIR = ROOT / "quizzes"

CATEGORIES = [
    "General Knowledge", "Science", "Mathematics", "History", "Geography",
    "Computer Science", "Programming", "English Grammar", "Biology", "Chemistry",
    "Physics", "Sports", "Entertainment", "Current Affairs", "Literature",
    "Economics", "Custom",
]
DIFFICULTIES = ["Easy", "Medium", "Hard", "Expert"]

Q_RE = re.compile(r"^(\d+)[.)]\s*(.+)$")
OPT_RE = re.compile(r"^([a-dA-D])[.)]\s*(.+)$")
ANS_RE = re.compile(r"^(?:Answer|ANS)\s*[:=]\s*([a-dA-D])\.?\s*$")
EXP_RE = re.compile(r"^(?:Explain|Explanation|Why)\s*[:=]\s*(.+)$", re.IGNORECASE)


class QuizTextError(Exception):
    pass


def parse_questions(text: str) -> list:
    """TXT -> [{question, options, correct_index, explanation}] (mirrors the app parser)."""
    questions, current = [], None
    start_line = 0

    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue

        m = Q_RE.match(line)
        if m:
            if current:
                questions.append(_finish(current, start_line))
            current = {"question": m.group(2).strip(), "options": {}, "answer": None, "explanation": ""}
            start_line = idx
            continue

        if current is None:
            raise QuizTextError(f"line {idx}: text before the first numbered question")

        m = ANS_RE.match(line)
        if m:
            current["answer"] = m.group(1).lower()
            continue

        m = EXP_RE.match(line)
        if m:
            current["explanation"] = m.group(1).strip()
            continue

        m = OPT_RE.match(line)
        if m:
            letter = m.group(1).lower()
            if letter in current["options"]:
                raise QuizTextError(f"line {idx}: option '{letter}' given twice")
            current["options"][letter] = m.group(2).strip()
            continue

        # anything else continues the question text (multi-line questions)
        current["question"] = f"{current['question']} {line}".strip()

    if current:
        questions.append(_finish(current, start_line))
    if not questions:
        raise QuizTextError("no questions found")
    return questions


def _finish(cur: dict, line_no: int) -> dict:
    opts = cur["options"]
    if len(opts) not in (2, 4):
        raise QuizTextError(
            f"question starting line {line_no}: needs exactly 2 options (True/False) "
            f"or 4 (MCQ), found {len(opts)}"
        )
    letters = sorted(opts)
    if letters != ["a", "b"] and letters != ["a", "b", "c", "d"]:
        raise QuizTextError(f"question starting line {line_no}: options must be a) b) or a) b) c) d)")
    if cur["answer"] not in opts:
        raise QuizTextError(
            f"question starting line {line_no}: missing/invalid 'Answer:' line "
            f"(got {cur['answer']!r}, options are {letters})"
        )
    ordered = [opts[l] for l in letters]
    out = {
        "question": cur["question"],
        "options": ordered,
        "correct_index": letters.index(cur["answer"]),
    }
    if cur["explanation"]:
        out["explanation"] = cur["explanation"]
    return out


def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return re.sub(r"-{2,}", "-", s) or "misc"


def main() -> int:
    ap = argparse.ArgumentParser(description="Add a community quiz from text")
    ap.add_argument("--id", required=True, help="unique quiz id, e.g. c-basics-002")
    ap.add_argument("--title", required=True)
    ap.add_argument("--category", default="General Knowledge", choices=CATEGORIES)
    ap.add_argument("--difficulty", default="Easy", choices=DIFFICULTIES)
    ap.add_argument("--author", default="SirYadav1")
    ap.add_argument("--questions-file", help="file with the quiz text")
    ap.add_argument("--questions-text", help="quiz text inline")
    ap.add_argument("--dry-run", action="store_true", help="validate only, write nothing")
    args = ap.parse_args()

    if not args.questions_file and not args.questions_text:
        print("ERROR: pass --questions-file or --questions-text")
        return 1

    text = Path(args.questions_file).read_text(encoding="utf-8") if args.questions_file else args.questions_text

    try:
        questions = parse_questions(text)
    except QuizTextError as e:
        print(f"PARSE ERROR: {e}")
        return 1

    quiz = {
        "id": args.id.strip(),
        "title": args.title.strip(),
        "category": args.category,
        "difficulty": args.difficulty,
        "author": args.author.strip() or "kvizo-community",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "questions": questions,
    }

    # same validator the signer uses - never write something that cannot be signed
    sys.path.insert(0, str(ROOT))
    try:
        from build import validate_quiz
    except ImportError:
        validate_quiz = None
    if validate_quiz:
        errs = validate_quiz(quiz, Path(f"quizzes/{slug(args.category)}/{args.id}.json"))
        if errs:
            print("VALIDATION FAILED\n" + "\n".join("  - " + e for e in errs))
            return 1

    target = QUIZZES_DIR / slug(args.category) / f"{args.id.strip()}.json"
    if target.exists():
        print(f"ERROR: {target.relative_to(ROOT)} already exists - pick another --id "
              f"(or delete the old file first)")
        return 1

    print(f"parsed {len(questions)} questions OK")
    if args.dry_run:
        print(f"dry run - would write {target.relative_to(ROOT)}")
        print(json.dumps(quiz, indent=2, ensure_ascii=False)[:400] + "\n...")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(quiz, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    print("next: build.py signs the bundle (CI does this automatically on push)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
