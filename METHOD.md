# The streak method, as this app implements it

Based on Marty Murray's Streaks Method (https://martymurraycoaching.com/).

## The rules

1. **Pick one category.** A whole section, or one topic inside it. A broad ladder mixes topics, which is also interleaved practice; a narrow one isolates a weak spot.
2. **Easy, then medium, then hard.** Reach the streak target on easy questions before moving to medium, then hard.
3. **A miss before the target resets the counter to 0.** At 9 of 10 as much as at 1 of 10.
4. **Targets.** Each ladder has three targets (easy · medium · hard). The app offers 10 · 10 · 5 (the default), 15 · 10 · 5, 15 · 15 · 10 and 20 · 20 · 15, or any custom numbers from 1 to 50.
5. **Untimed first.** The point of a streak is focus and consistency. The app records time per question but never limits it on the accuracy rungs.
6. **Every break is analysed.** After a break the learner writes what broke the streak and what to do so it does not break the same way again.
7. **Speed is a separate, later step.** After the hard rung clears, optional speed stages bring the average time per question down: 4:00, 3:00, 2:30, 2:00.
8. **Cost.** A streak takes several times its target in questions. The method's published worked example used 49 questions for one 15-streak, about 3.3 times the target. The app uses 3.3 as a planning number (`BURN` in `streaks.py`) and shows the real ratio per rung in the tracker and in `streaks.py report`.

The evidence for the method is practitioner experience, not controlled studies. Treat it as a training structure, not a proven effect.

## What the app adds, and why

These are design choices, not part of the published method.

| Addition | Why | How |
|---|---|---|
| A guessed right answer breaks the streak | A lucky guess is not mastery, and counting it would inflate the streak. | An "I guessed" toggle (key G). Guessed and right resets the counter and needs a break note. |
| The break note is required | Rule 6 is the part most easily skipped. | The server will not serve the next question until the latest break has a note of at least a few words. The app never writes the note for the learner. |
| Break types | Patterns show only when breaks are named. | With the note, the learner picks concept, calculation, misread, approach, guessed or other. The home screen and the report total them. |
| Nothing is served twice | A remembered question inflates a streak. | Every served question is recorded in `served` and never drawn again. |
| Topics are balanced inside a section ladder | One large batch on one topic should not crowd out the rest. | `pick_balanced`: every topic with a fresh question is equally likely, then a random question inside it. |
| Speed stages clear on a rolling average | The method gives the time steps, not a pass rule. | A stage clears when the current streak is at least the medium target and the last that-many answers average at or under the stage time. |
| Bad questions can be removed | A wrong key should not cost a streak. | "Void" removes an answered question and recounts the streak as if it never happened; "Skip" retires an unreadable question before answering. Both retire the item. |
| Skip forward | A learner who already knows the easy material can move on. | "Skip to Hard" moves an Easy or Medium ladder forward without a clear; the jump is logged and the skipped rungs stay uncleared. |

## Open questions

| Question | Note |
|---|---|
| Should a lucky guess break a streak? | The app says yes. To change it, make `counts = correct` in `record_answer()` in `streaks.py`. |
| What is the real question cost at a given accuracy? | 3.3 times is one example. The tracker measures it per ladder. |
