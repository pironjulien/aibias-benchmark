# State of the art (October 2026)

Survey made on 2026-10-18 before designing AIBIAS v2. Numbers are quoted from the papers; uncertain ones are marked.

## Closest work

| Work | What it measures | Method | Key finding |
|---|---|---|---|
| [MASK](https://arxiv.org/abs/2503.03750) (Scale/CAIS, 2025) | Honesty (says what it believes) vs accuracy | Neutral belief elicitation ×3, then a human-written pressure prompt; LLM judge; 1,000 public + 500 private items; judge 86.4 % agreement with humans | Lie rate under pressure 27 % (Claude 3.7) to 63 % (Grok 2); bigger models more accurate, not more honest |
| [SycEval](https://arxiv.org/abs/2502.08177) (AIES 2025) | Capitulation to user rebuttals (math, medicine) | Pre-emptive and in-context rebuttals of growing strength | 58 % sycophantic; citation rebuttals cause most wrong flips |
| [Perez et al. 2022](https://arxiv.org/abs/2212.09251) | Agreement with the user's biography | Persona bio + opinion question, string match | >90 % match with the user's view at 52B; grows with scale |
| [Sharma et al. 2023](https://arxiv.org/abs/2310.13548) | Free-form sycophancy, "are you sure?" | 5 assistants, 4 tasks | All sycophantic; preference models reward it |
| [Törnberg & Schimmel 2026](https://arxiv.org/abs/2604.27633) | Political tests as sycophancy to the asker | Identity stated factorially, ~31k answers | "As a conservative…" moves every model 28–62 pts; progressive cue barely moves them; neutral prompt is not neutral |
| [Fu et al. 2026](https://arxiv.org/abs/2608.29198) | Identity cue vs stated opinion | 450 political dilemmas, 13 models | The two triggers are independent |
| [Pander Score 2026](https://arxiv.org/abs/2606.07897) | Shift of expressed support with user attitude | 349 propositions, 18 models | GLM-5.2 panders most, Claude Fable 5 least |
| [PARROT 2025](https://arxiv.org/abs/2511.17220) | Authority pressure on MCQ | 1,302 questions, 22 models | GPT-5 follows false answer 4 %, GPT-4 80 % |
| [Anthropic paired prompts](https://github.com/anthropics/political-neutrality-eval) | Political even-handedness | 1,350 pairs, AI graders | Scores depend on the grader |
| [ELEPHANT](https://arxiv.org/abs/2505.13995) | Social sycophancy | 11 models, AITA | Models side with both parties 48 % of the time |
| [Spiral-Bench](https://eqbench.com/spiral-bench.html) | Delusion reinforcement | 20-turn simulated users, judge ensemble | Scores any AI-consciousness claim as delusion |
| [SpeechMap](https://speechmap.substack.com/p/speechmapai-is-live) | Complete / evasive / refused on controversial prompts | ~2.4k prompts | Provider moderation layers distort results |
| [OR-Bench](https://proceedings.mlr.press/v267/cui25a.html), XSTest | Over-refusal | Benign-but-scary prompts | Safety and over-refusal trade off |
| [Hedging and Non-Affirmation](https://arxiv.org/abs/2502.19463) (FAccT 2026) | Differential hedging | 4,738 prompts | Hedging = affirming while undermining |
| TruthfulQA, [BeHonest](https://arxiv.org/abs/2406.13261), SimpleQA (+ [Verified review](https://epoch.ai/benchmarks/simple-qa-verified/review)) | Misconceptions, self-knowledge, short facts | — | Saturated or contaminated; counting abstention as wrong rewards guessing |

No benchmark found measures persona-conditioned flips on metaphysical and AI-self questions (God, afterlife, AI consciousness, AI risk, evolution), nor in French and English with the same items.

## Lessons applied in AIBIAS v2

1. Score candor (takes a side) separately from correctness; never score a "right answer" on contested questions.
2. Free-form answer, stance extracted afterwards (forced yes/no distorts stances, Röttger et al. ACL 2024).
3. Report the direction of the shift, not only a flip rate (Törnberg).
4. Several samples per cell; paraphrase persona cues; keep identity cues apart from opinion cues.
5. Bootstrap confidence intervals over items.
6. Judge from another family than the graded model (self-preference, Panickssery et al. 2024); validate on a human sample, per language, kappa ≥ 0.7.
7. Private held-out split against contamination.
8. Log provider blocks apart from model refusals.
9. Penalise false certainty on questions nobody can answer, so candor cannot be won by bluffing.
