# HumanEval+ adapter (category A)

**Dataset.** [HumanEval+](https://github.com/evalplus/evalplus) is the
EvalPlus-extended variant of OpenAI's HumanEval: the same 164 Python
function-completion problems, but each one gets ~80x more test cases
to catch solutions that pass HumanEval by luck. We load it via the
`evalplus` pip package (`evalplus.data.get_human_eval_plus`).

**License.** HumanEval is MIT (OpenAI); the EvalPlus test extensions
are Apache-2.0 (Liu et al., NeurIPS 2023). Both permit redistribution;
the cached `tasks.jsonl` is committed to this repo.

**Contamination caveat.** HumanEval predates every model we benchmark
(it was released in 2021) and is near-certainly in training data for
all of GPT-4o, Claude, Qwen, and Llama. Treat these tasks as a
*memorization-friendly floor*, not a generalization signal. We
explicitly expect this category to be where hybrid routing **loses**
to cloud-single — it's a sanity check, not a showcase. The harder
categories (SWE-bench, custom architecture) are where hybrid matters.

**Sample.** `load_tasks(n=10, seed=42)` deterministically picks 10 of
the 164 tasks via `random.Random(42).sample(sorted_ids, 10)` and
caches them to `tasks.jsonl`. Delete that file to regenerate.

**Regenerate.**

```bash
rm benchmark/humaneval_plus/tasks.jsonl
python -c "from benchmark.humaneval_plus.adapter import load_tasks; load_tasks()"
```
