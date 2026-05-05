# Research Report

**Query:** Comprehensive survey of open-source code-generation evaluation benchmarks suitable for measuring local-vs-cloud-vs-hybrid LLM routing as of May 2026. For each benchmark report: dataset size, task types covered (function completion, multi-file edit, repo-level edit, debugging, test writing, refactor, architecture design), automation difficulty (does it ship a runnable harness and a sandbox?), license, recency of test data (data-contamination concerns), and what flagship + open-weights models score on it as of late 2025 / early 2026. Cover at minimum: HumanEval, MBPP, MBPP+, EvalPlus, BigCodeBench-Hard, LiveCodeBench, SWE-bench Verified, SWE-bench Lite, SWE-bench Pro, RepoBench, ClassEval, CodeContests, CRUXEval, Aider Polyglot, Aider Refactor, Spider, StackEval, MultiPL-E, CodeXGLUE, DS-1000, R2E, Stack Overflow QA, AppWorld, ML-Bench, RepoCoder, CoderEval, ComplexCodeEval. Identify which benchmarks are designed/usable for routing evaluation specifically (RouterBench coding subset, RouterArena, RouterEval — coding splits if any). For each: how easy is it to wire into a custom harness that runs the same task through 4 different routes (cloud-only, local-only, hybrid-architect, hybrid-minion) and produces a comparable score? Be detailed; cite leaderboards, per-task automation requirements, and known contamination findings. Also note any benchmarks specifically for measuring quality vs cost trade-offs.
**Run ID:** `ee2df0e2`
**Generated:** 2026-05-04T21:29:50Z

---

## Perplexity Deep Research
*Model: `sonar-deep-research` · 170s · 359 prompt + 10,503 completion tokens*

<think>
This is a comprehensive and detailed query about code-generation evaluation benchmarks as of May 2026. Let me break down what I need to cover:

1. **Core benchmarks to analyze:**
   - HumanEval, MBPP, MBPP+, EvalPlus, BigCodeBench-Hard, LiveCodeBench
   - SWE-bench variants (Verified, Lite, Pro)
   - RepoBench, ClassEval, CodeContests, CRUXEval
   - Aider Polyglot, Aider Refactor, Spider, StackEval, MultiPL-E
   - CodeXGLUE, DS-1000, R2E, Stack Overflow QA, AppWorld
   - ML-Bench, RepoCoder, CoderEval, ComplexCodeEval
   - FrontendBench (mentioned in results)

2. **For each benchmark, I need to report:**
   - Dataset size
   - Task types covered (function completion, multi-file edit, repo-level edit, debugging, test writing, refactor, architecture design)
   - Automation difficulty (runnable harness + sandbox)
   - License
   - Recency of test data / data-contamination concerns
   - Flagship + open-weights model scores (late 2025/early 2026)

3. **Routing evaluation specific benchmarks:**
   - RouterBench, RouterEval, RouterArena (coding subsets if any)

4. **Metrics:**
   - Ease of integrating into custom routing harness (4 routes: cloud-only, local-only, hybrid-architect, hybrid-minion)

5. **Special considerations:**
   - Quality vs cost trade-offs
   - Contamination findings

Let me review the search results provided:

[1] - HumanEval GitHub page
[2] - HumanEval Pro & MBPP Pro with performance data


[3] - SWE-bench leaderboards showing various model performance across repository-level tasks
[4] - FrontendBench for web development code generation
[5] - Open-source LLM comparisons from 2026 with benchmark results
[3] - Additional SWE-bench leaderboard data
[6] - ClassEval for object-oriented programming evaluation
[7] - LiveCodeBench with continuously updated test cases
[8] - BigCodeBench-Hard focusing on complex coding challenges
[9] - EvalPlus variants including HumanEval+, MBPP+, and RepoQA
[10] - Aider Polyglot benchmark for multi-language code editing
[11] - Spider for database query generation
[12] - StackEval for stack-based problem solving
[13] - DS-1000 benchmark for data science tasks
[14] - RepoExec for repository-level code execution evaluation
[15] - LLM leaderboard aggregating 2026 model rankings
[16] - Open source LLM leaderboard specifically tracking open models
[17] - Data contamination detection methods to ensure benchmark validity
[18] - RouterBench for evaluating model routing strategies
[19] - Hybrid LLM routing approaches combining multiple models
[20] - RouterBench implementation details and metrics
[21] - RouterEval for assessing routing performance
[22] - ClawEnvKit providing agent environments for testing
[1] - HumanEval benchmark (previously mentioned)
[23] - MBPP leaderboard tracking model performance on Python problems
[24] - Survey of benchmarks and evaluation metrics for code generation
[25] - ComplexCodeEval for harder programming tasks
[26] - CRUXEval examining code understanding and execution
[27] - COMPASS benchmark for comprehensive code assessment
[28] - Trade-offs between latency and output quality in model selection
[3] - SWE-bench repository tasks (previously noted)
[29] - BigCodeBench general version alongside the hard variant
[30] - Aider benchmarks for code editing evaluation
[31] - ML-Bench for machine learning code generation
[32] - AppWorld for application-level code tasks
[23] - MBPP leaderboard (previously listed)
[33] - Open source licensing considerations for models
[34] - LiveCodeBench leaderboard with current rankings
[35] - CoreCodeBench for fundamental coding skills
[18] - RouterBench routing evaluation (previously mentioned)
[36] - Determining the best LLM for coding tasks based on benchmarks
[37] - RepoBench evaluating multi-file repository understanding
[38] - CodeContests for competitive programming evaluation
[39] - List of available open source language models
[40] - IPR benchmark specifically for routing model selection
[41] - Inconsistencies and variations in HumanEval implementations
[42] - MBPP dataset composition and problem distribution
[35] - CoreCodeBench (previously listed)
[43] - Sandbox environments for testing coding agents safely
[44] - LM Evaluation Harness as infrastructure for running benchmarks

I'm organizing these findings into a structured framework covering foundational benchmarks like HumanEval and MBPP, then moving through repository-level evaluation, domain-specific tasks, and routing-specific frameworks. The key distinction emerging is between function-level completion tasks versus full application development, with contamination concerns requiring newer benchmarks like LiveCodeBench. Routing evaluation introduces additional complexity since models must be selected based on task characteristics rather than just ranked globally.

Key metrics I'm tracking: LiveCodeBench provides 500+ contamination-free problems across code generation, self-repair, and execution tasks. SWE-bench offers 500 verified repository-level instances. BigCodeBench scales to 1140 complex problems while ComplexCodeEval provides 3897 Java and 7184 Python samples. RouterBench and RouterEval represent the routing-specific layer with 405k+ samples and 200M+ performance records respectively. Domain-specific benchmarks like Spider (10,181 text-to-SQL), DS-1000 (1000 data science), and ML-Bench (repository-level ML tasks) show how evaluation fragments across specializations. Application-level benchmarks including AppWorld (750 agent tasks), FrontendBench (148 front-end tasks), and Aider Polyglot (225 multi-language problems) demonstrate the gap between isolated function completion and real-world deployment scenarios.

Top performers cluster around GPT-5.5, Claude 3.7 Sonnet, and Gemini 3 Pro. Among open-weight models, Qwen2.5-Coder 32B achieves 92.7% on HumanEval Pro, outpacing GPT-4o's 90.2%. LiveCodeBench favors GPT-4-turbo and Claude-3-Opus while SWE-bench shows Kimi K2.5 leading at 76.8%. License terms matter for deployment: Apache 2.0 and MIT offer commercial flexibility, Llama License caps at 700M monthly active users, and Gemma applies usage policies.
</think>

# Comprehensive Survey of Open-Source Code-Generation Evaluation Benchmarks for LLM Routing Evaluation as of May 2026

This report presents a detailed analysis of open-source code-generation evaluation benchmarks currently available for assessing local versus cloud versus hybrid large language model routing strategies. The evaluation landscape in 2026 has matured significantly beyond simple function-level correctness metrics, encompassing repository-scale challenges, real-world software engineering tasks, and specialized routing evaluation frameworks. This survey examines over two dozen benchmarks across multiple dimensions including dataset composition, task diversity, automation infrastructure, licensing terms, data recency and contamination concerns, and measured performance of flagship and open-weight models as of late 2025 and early 2026. Additionally, this report evaluates the feasibility of integrating these benchmarks into custom routing harnesses that can execute identical tasks through multiple routing strategies—cloud-only services, local inference, hybrid architectures with central coordinators, and hierarchical minion-based systems—while maintaining comparable evaluation metrics. The analysis identifies which benchmarks were purpose-built or adapted for routing evaluation specifically and discusses the infrastructure requirements for creating representative cost-quality trade-off measurements.

## Function-Level Code Generation Benchmarks: The Foundation

The earliest and most widely recognized code evaluation benchmarks operate at the function level, presenting models with task descriptions and expecting complete, executable function implementations. These benchmarks have provided the baseline against which most code LLM development has been measured, though they represent only a narrow slice of real-world software engineering activities.

### HumanEval: The Original Standard

HumanEval remains the canonical baseline for function-level code generation evaluation[1][1]. The benchmark consists of 164 hand-written Python programming problems with associated unit tests, designed to evaluate whether large language models can generate correct, executable code from natural language problem descriptions. Each problem includes a function signature, docstring specification, and a set of test cases that verify correctness[1]. The dataset was released in December 2021 alongside the "Evaluating Large Language Models Trained on Code" paper from OpenAI, establishing what would become the de facto standard for initial code LLM evaluation.

The simplicity of HumanEval's task structure—generate a single complete function given a specification—means that the benchmark exhibits relatively low cognitive complexity compared to real-world programming scenarios. However, this simplicity has also made it extremely useful for establishing baseline comparisons across models and for rapid iteration on model architectures. The 164 instances provide sufficient scale for statistical significance while remaining small enough that models with training-time contamination can potentially memorize portions of the dataset, a concern that has grown more acute as the field has matured[17].

The benchmark operates with straightforward automation: models generate Python code as strings, the harness executes the code within a sandboxed environment using Python's built-in unittest framework, and binary pass/fail metrics are recorded based on whether generated code passes all test cases[1]. The license for HumanEval is permissive for academic and commercial research purposes through OpenAI's repository terms. In terms of recency, the test data is now more than four years old, creating potential data contamination concerns for models trained on public internet data up to mid-2024 and beyond.

Performance on HumanEval has reached saturation for frontier models. According to leaderboard data from late 2025 and early 2026[15][16], proprietary models including GPT-5.5, Claude 3.7 Sonnet, and Gemini 3 Pro achieve pass@1 rates exceeding 90 percent on HumanEval. Among open-weight models, Qwen2.5-Coder 32B instruction variant achieves approximately 92.7 percent pass@1 on the extended HumanEval Pro variant (discussed below), though pure HumanEval scores for open models typically range from 70 to 85 percent depending on model size and training approach[2][23]. The saturation of this benchmark for frontier models has driven the field toward more challenging alternatives.

### MBPP: Crowd-Sourced Python Fundamentals

The Mostly Basic Python Problems (MBPP) benchmark represents an alternative function-level evaluation set, comprising 974 crowd-sourced Python programming problems designed specifically to be solvable by entry-level programmers[23][42]. Unlike HumanEval's hand-curated problems, MBPP problems originate from crowdworker submissions and encompass programming fundamentals, standard library functionality, and straightforward algorithmic challenges. Each problem consists of a task description, a reference solution, and three automated test cases that verify basic correctness criteria[23].

The MBPP benchmark's much larger size relative to HumanEval—974 problems versus 164—provides greater statistical power for detecting performance differences between models. However, the broader distribution of problem difficulty and the potentially variable quality of crowd-sourced tasks introduce different evaluation characteristics. The benchmark operates with similar automation to HumanEval: code generation followed by sandboxed execution and test case verification[42]. Current leaderboard data indicates that Sarvam-30B leads MBPP evaluation with a score of 0.927, followed closely by Llama-3.3 Nemotron Super 49B and Qwen2.5-Coder 32B Instruct, all near 0.9 pass rates[23]. The MBPP benchmark is released under Apache 2.0 licensing, permitting both academic and commercial use without restriction[39].

## Enhanced and Specialized Function-Level Benchmarks

The maturation of code evaluation has driven the development of enhanced versions of foundational benchmarks that address specific limitations of the originals. These variants typically add rigor through extended test suites, incorporate additional task types, or introduce specialized evaluation scenarios.

### EvalPlus: Extended Test Coverage for Rigor

The EvalPlus initiative, maintained by the EvalPlus team focused on building high-quality code evaluation systems, introduces HumanEval+ and MBPP+ by substantially extending the test case sets associated with original benchmarks[9]. HumanEval+ extends the test coverage by approximately eighty times the original density, incorporating edge cases, boundary conditions, and more comprehensive assertion sets. MBPP+ similarly increases test rigor by thirty-five times relative to the base benchmark. These extensions address a critical limitation in the original benchmarks: their relatively sparse test coverage allowed models to generate code that appeared correct on limited test cases while failing to generalize correctly[9].

Beyond test extension, EvalPlus maintains EvalPerf, a specialized evaluation framework for measuring code efficiency through differential performance evaluation methodology established in their COLM'24 research. This framework assesses not only functional correctness but also the efficiency characteristics of generated code—an important practical consideration in production environments where computational resources directly translate to cost[9]. EvalPlus also maintains RepoQA, designed to evaluate long-context code understanding across entire repositories, addressing a gap between simple function-level evaluation and real-world multi-file development scenarios[9].

The automation infrastructure for EvalPlus is built on top of the existing HumanEval and MBPP harnesses, making integration into custom evaluation systems straightforward. The extended test cases are available through the EvalPlus project repositories and integrate directly with standard Python testing infrastructure. License terms are permissive for academic research.

### HumanEval Pro and MBPP Pro: Self-Invoking Code Generation

Recent research has introduced HumanEval Pro and MBPP Pro benchmarks specifically designed to evaluate LLMs on self-invoking code generation tasks, which represent scenarios where generated code must correctly call helper functions and manage complex control flow[2]. These benchmarks maintain compatibility with the original HumanEval and MBPP problem sets while adding requirements for self-referential code generation and testing the model's ability to generate code that invokes itself or previously defined functions correctly.

Performance data from early 2026 reveals significant performance differentiation on HumanEval Pro compared to standard HumanEval. The flagship proprietary models achieve pass@1 rates in the 75-92 percent range on HumanEval Pro, while open-weight models show more variable performance patterns[2]. Notably, instruction-tuned variants of open models show substantial gains over base models: Qwen2.5-Coder-32B-instruct achieves 92.7 percent on HumanEval Pro (87.2 percent on stricter metrics), while the base variant only reaches 65.9 percent. This pattern holds across other model families, suggesting that instruction tuning provides more pronounced benefits for complex self-invoking scenarios than for straightforward function generation[2]. The research introducing these benchmarks also reveals that base models may retain elevated training potential for self-invoking tasks compared to their instruction-tuned counterparts, suggesting a possible optimization direction for future model development[2].

## Repository-Scale Code Evaluation Benchmarks

The limitations of function-level evaluation have driven the development of benchmarks that operate at repository scale, encompassing multiple files, cross-file dependencies, and the full context of real software projects. These benchmarks present substantially greater challenges to current LLMs and provide more realistic assessment of practical applicability.

### SWE-bench: Software Engineering from Real GitHub Issues

SWE-bench represents one of the most significant advances in code evaluation, providing a benchmark derived from real GitHub software engineering issues that require actual repository-level modifications[3][3][3]. The benchmark's foundation consists of verified instances selected from public GitHub repositories and includes a human-filtered subset of 500 instances representing confirmed resolvable issues. SWE-bench also maintains SWE-bench Lite, a more cost-effective evaluation variant, and SWE-bench Multilingual, extending the evaluation framework across nine programming languages, as well as SWE-bench Multimodal for issues that incorporate visual elements[3][3][3].

The dataset scale is substantial—with the verified subset containing 500 carefully curated instances drawn from diverse real-world projects—making it far more computationally intensive to evaluate than function-level benchmarks. SWE-bench tasks require models to understand complex codebases, identify where modifications are necessary, generate appropriate patches, and ensure that all existing tests continue to pass while fixing the target issue. The benchmark incorporates an automatic evaluation framework that uses the mini-SWE-agent harness to maintain consistent evaluation methodology across models[3].

Current leaderboard performance shows substantial variation across models. As of early 2026, proprietary models achieve scores in the 70-76 percent range, with Kimi K2.5 leading at 76.8 percent. Open-weight models show more modest performance, with DeepSeek-R1 at 49.2 percent and DeepSeek V3 at 38.8 percent[16]. The gap between frontier proprietary and best open-weight models on SWE-bench remains significantly larger than on HumanEval, suggesting repository-scale reasoning remains a capability frontier.

SWE-bench's automation infrastructure is relatively mature, with the mini-SWE-agent providing a standardized harness that can execute across multiple models. The benchmark includes integrated sandboxing through Docker containers that preserve isolated repository state, allow code execution, and verify test outcomes. The licensing terms permit academic and commercial research use. A critical consideration is data recency: the benchmark's composition from real GitHub issues published in the training periods of many contemporary LLMs creates significant data contamination concerns[17].

### RepoBench: Cross-File Code Generation

RepoBench provides a repository-level code generation benchmark available through Hugging Face, with versions 1.1 incorporating recent code data[37]. The benchmark focuses on cross-file code generation scenarios where models must generate code with awareness of symbols and patterns defined in other files within the same repository. RepoBench distinguishes between cross-file scenarios with first-look ordering (where dependent files appear before depended-upon files in the context) and random ordering, allowing assessment of how models handle context ordering variations[37].

The benchmark includes separate Python and Java variants, supporting evaluation across multiple programming languages. Unlike SWE-bench's focus on issue resolution, RepoBench emphasizes completion of partial code implementations where the model must generate appropriate continuation code. The evaluation harness provides outputs for each level of cross-file context complexity, with weighted averages computed across all context levels[37]. RepoBench's automation infrastructure is straightforward, with Python-based evaluation scripts that can be executed with a single command specifying the model and language.

### ClassEval: Class-Level Code Generation

ClassEval introduces the first class-level code generation benchmark, addressing an evaluation gap between function-level and full-repository evaluation[6]. The benchmark consists of 100 manually-crafted class-level Python coding tasks encompassing 100 complete classes and 410 methods, with an average of 33.1 test cases per class[6]. This benchmark recognizes that modern object-oriented programming requires understanding of class hierarchies, method dependencies, state management across methods, and proper encapsulation—all challenges absent from function-level evaluation.

The dataset construction process emphasized manual curation to ensure task quality, with problems sourced from competitive programming platforms and programming education resources. Each class is accompanied by comprehensive test cases that verify both individual method correctness and interactions between methods. The automation infrastructure builds on standard Python testing frameworks, making integration relatively straightforward.

### ComplexCodeEval: GitHub Repository Scale

ComplexCodeEval extends repository-level evaluation through a large-scale benchmark derived from high-star GitHub repositories[25]. The benchmark comprises 3,897 Java samples from 1,055 repositories and 7,184 Python samples from 2,107 repositories, providing substantially more scale than most preceding repository-level benchmarks. The benchmark supports multiple downstream tasks including code generation, API recommendation, and test case generation, allowing assessment of diverse coding capabilities within a unified framework[25].

The inclusion of timestamps within the dataset design specifically addresses data leakage concerns, incorporating mechanisms to prevent training data contamination by filtering problems based on temporal boundaries. Performance evaluation across multiple models shows that Codellama-34B achieves highest scores on Java test case generation, while DeepSeek-Coder-6.7B leads on Python with a CodeBLEU score of 22.87[25]. The benchmark's multi-task design enables more comprehensive capability assessment than single-task frameworks.

## Holistic Code Capability Benchmarks

Beyond task-specific evaluation, the field has developed benchmarks that assess broader code-related capabilities including generation, self-repair, execution prediction, and dynamic reasoning about code behavior. These frameworks provide more complete pictures of code LLM capabilities.

### LiveCodeBench: Contamination-Free Continuous Evaluation

LiveCodeBench represents a significant methodological advance by addressing data contamination through continuous collection of fresh problems from competitive programming platforms[7][34]. The benchmark collects problems from LeetCode, AtCoder, and Codeforces, updating regularly to maintain contamination-free evaluation sets. Beyond simple code generation, LiveCodeBench evaluates broader code-related capabilities including self-repair (ability to fix incorrect code given test output), test output prediction (predicting execution results without running code), and code execution verification[7].

The benchmark currently hosts over 500 high-quality coding problems published between May 2023 and May 2024, providing substantially more recent test data than static benchmarks. The multi-capability focus reflects actual software development workflows where developers encounter diverse coding tasks beyond initial implementation. Performance data indicates GPT-4-turbo and Claude-3-Opus perform best across different scenarios among closed models, while DeepSeek-Ins-33B and Phind-34B lead among open-source variants[7]. LiveCodeBench's emphasis on contamination-free evaluation through continuous problem collection addresses one of the field's most significant methodological concerns[34].

The automation infrastructure executes code within sandboxed environments and verifies outcomes against expected results. The continuous update mechanism means that evaluations performed on LiveCodeBench at different time points necessarily test different problem instances, limiting longitudinal comparison but ensuring ongoing measurement validity. Licensing terms support academic and commercial research use.

### BigCodeBench: Task Automation at Scale

BigCodeBench provides a large-scale benchmark specifically designed for evaluating code generation capabilities in task automation scenarios with practical emphasis on realistic programming challenges[29]. The benchmark comprises 1,140 software-engineering-oriented programming tasks with two evaluation splits: a "Complete" split focused on code completion based on comprehensive docstrings, and an "Instruct" split designed for instruction-tuned models receiving natural language specifications[29].

The benchmark's design emphasizes complex instructions and diverse function calls, moving substantially beyond the relatively straightforward function completion tasks present in HumanEval. Tasks are sourced from practical software development scenarios, bringing realistic problem distributions to evaluation. BigCodeBench enables precise evaluation and comparative ranking of models' practical programming capabilities. The infrastructure includes automated harness testing and result comparison facilities designed to support large-scale model evaluation.

### COMPASS: Multi-Dimensional Programming Assessment

COMPASS (COdility's Multi-dimensional Programming ASSessment) introduces comprehensive evaluation across three critical dimensions of code quality: correctness, efficiency, and code quality characteristics[27]. The benchmark comprises 50 competitive programming problems from real Codility competitions, providing authentic human baselines from 393,150 submissions across the platform. This multi-dimensional assessment addresses a critical limitation in prior benchmarks that focused exclusively on functional correctness while ignoring the algorithmic efficiency and code maintainability dimensions critical in professional programming environments[27].

The inclusion of authentic competitive programming problems ensures alignment with real-world difficulty distributions and performance expectations. Human baselines enable assessment of how generated code compares not only to reference solutions but to typical human programmer performance. The efficiency dimension specifically addresses cost considerations in cloud deployment scenarios where computational resources directly impact operational expenses.

## Specialized Domain and Task Benchmarks

Beyond general code generation, specialized benchmarks target specific programming domains and task types that require distinct capabilities. These benchmarks enable fine-grained assessment of model capabilities in particular contexts.

### CRUXEval: Code Reasoning, Understanding, and Execution

CRUXEval focuses specifically on code reasoning, understanding, and execution prediction capabilities through a benchmark of 800 Python functions with associated input-output pairs[26]. The benchmark features two distinct tasks: CRUXEval-I (input prediction) where models must predict what input would produce a given output, and CRUXEval-O (output prediction) where models predict execution results for given inputs[26].

These tasks assess reasoning about code semantics and execution dynamics rather than code generation capability. GPT-4 achieves 67 percent pass@1 on CRUXEval-I and 63 percent on CRUXEval-O, while CodeLlama 34B achieves 47 percent and 44 percent respectively, indicating substantial capability variation[26]. This benchmark's focus on reasoning about code rather than generation provides complementary assessment to generation-focused benchmarks.

### Spider: Text-to-SQL Semantic Parsing

Spider provides a large-scale benchmark for complex semantic parsing and text-to-SQL tasks, consisting of 10,181 questions and 5,693 unique complex SQL queries across diverse database schemas[11]. While focused on database query generation rather than general code generation, Spider represents an important specialized domain where code generation interacts with semantic understanding of data schemas and natural language specifications[11].

### StackEval: Stack Overflow Derived Benchmarking

StackEval presents comprehensive benchmarks for code assistance tasks derived from Stack Overflow content, covering code writing, debugging, code review, and conceptual understanding[12]. The benchmark includes StackEval as a large-scale benchmark derived from historical Stack Overflow questions, plus StackUnseen featuring the most recent Stack Overflow content, enabling evaluation of model behavior on contemporary programming challenges. The evaluation framework scores completions on a zero-to-three scale where scores of two or higher are deemed acceptable, providing finer-grained assessment than binary pass/fail metrics[12].

### DS-1000: Data Science Code Generation

DS-1000 introduces a specialized benchmark for data science code generation with 1,000 problems spanning seven Python libraries including NumPy, Pandas, and related data science tools[13]. The benchmark's focus on data science represents an important specialized domain where models must generate code that correctly manipulates data structures and applies library-specific functions. Performance data indicates the current best public system achieves 43.3 percent accuracy, suggesting substantial room for improvement in specialized domain code generation[13].

## Application-Level and Interactive Code Benchmarks

Recent benchmarks have extended evaluation to application-level scenarios requiring autonomous agents to generate and execute code within interactive environments, reflecting increasingly sophisticated applications of code LLMs.

### Aider Benchmarks: Code Editing in Interactive Environments

Aider provides specialized benchmarks evaluating code generation in interactive editing contexts, recognizing that real-world code development involves iterative editing, test feedback incorporation, and file manipulation alongside pure code generation[30][10]. The benchmarks measure not only code generation capability but also the model's ability to format edits correctly for consumption by the editor tool and to incorporate test output feedback.

The Aider Polyglot benchmark evaluates models' coding abilities across six programming languages (C++, Go, Java, JavaScript, Python, and Rust) through 225 of Exercism's most challenging problems[10]. Models are given two attempts per problem, with the second attempt informed by unit test results from the first attempt, testing both initial solution capability and debugging/self-correction ability. This two-attempt structure provides more realistic assessment of practical development workflows than single-generation evaluation.

Performance on Aider benchmarks shows differentiation between models in their ability to incorporate feedback and adjust code based on test outputs. The benchmark's integration of iterative improvement cycles distinguishes it from static generation-only benchmarks. License terms support academic and research use through the Aider project's permissive licensing.

### AppWorld: Autonomous Agent Development

AppWorld provides a high-fidelity execution environment for autonomous agent evaluation, comprising nine day-to-day applications operable via 457 different APIs and populated with simulated digital activities of 106 people[32]. The AppWorld Benchmark includes 750 natural, diverse, and challenging autonomous agent tasks requiring rich and interactive code generation, represented through 40,000 lines of benchmark infrastructure code[32].

This benchmark represents a substantial evolution beyond static problem sets, creating interactive environments where agents must generate code that manipulates complex state spaces and interacts with multiple systems. The high fidelity of the execution environment enables assessment of code generation in near-realistic scenarios.

### FrontendBench: Front-End Code Generation

FrontendBench introduces a benchmark for evaluating LLMs specifically on front-end code generation tasks, comprising 148 meticulously crafted prompt-test case pairs spanning five levels of web components[4]. The benchmark categorizes tasks based on code functionality and incorporates interactive test scenarios enabling comprehensive evaluation of front-end capabilities. An automatic evaluation framework executes generated code within a sandbox environment using Puppeteer APIs to control browsers and verify generated HTML against functional specifications, achieving 90.54 percent agreement with expert human evaluations[4].

The benchmark's five application categories—concept explanation, utilities, games, web interfaces, and data visualizations—provide diverse front-end scenarios. The automated evaluation framework's high agreement with human assessment validates its reliability for scalable performance measurement.

## Benchmarks Specifically Designed for Routing Evaluation

A critical category for this survey involves benchmarks explicitly constructed for evaluating LLM routing systems and cost-quality tradeoffs. These specialized frameworks enable systematic assessment of routing strategies.

### RouterBench: Multi-LLM Routing Evaluation Framework

RouterBench provides the first comprehensive benchmark specifically designed for systematically evaluating the efficacy of LLM routing systems[18][20][18]. The framework comprises a comprehensive dataset of over 405,000 inference outcomes from representative LLMs performing diverse tasks, designed to support development and assessment of routing strategies[18][20].

RouterBench's construction draws from established datasets that are widely recognized in LLM evaluation: it comprises a broad spectrum of tasks including commonsense reasoning, knowledge-based language understanding, conversation, math, coding, and retrieval-augmented generation (RAG)[20]. For coding specifically, the benchmark includes tasks from standard code evaluation datasets, providing coverage of typical code-related challenges. The comprehensive dataset was generated through inference with 14 different LLMs including both open-source and proprietary models[20].

The benchmark's scale—405,467 samples across 11 models, 8 datasets, and 64 distinct tasks—provides sufficient statistical power for identifying router performance differences. The inclusion of multiple model families (from small efficient models to large frontier models) enables assessment of routing strategies that must balance cost, latency, and quality across diverse model options[20]. The theoretical framework for LLM routing provided alongside RouterBench formalizes routing objectives and constraints, enabling rigorous router design and comparison.

RouterBench's architecture comprises multiple task categories with associated performance data allowing assessment of router decision quality. The framework documents inference costs and latencies for each model-task combination, enabling precise cost-quality tradeoff measurements. This enables routers to be evaluated not merely on accuracy but on their ability to route to appropriate models given cost budgets, latency constraints, or quality requirements.

### RouterEval: Large-Scale Router Benchmarking

RouterEval extends routing evaluation to comprehensive scale with a benchmark containing over 200 million performance records for 12 popular LLM evaluations across multiple domains[21]. The benchmark spans over 8,500 LLM variants, providing vastly more comprehensive coverage than RouterBench for routing optimization research. The extensive performance data enables training sophisticated routing models and evaluating their effectiveness across diverse scenarios[21].

The breadth of RouterEval—incorporating results from thousands of LLM instances—suggests it may not focus specifically on code evaluation but rather provides general routing infrastructure. However, the sheer scale of performance records provides foundation for cost-quality routing analysis in code domains if appropriate task filtering is applied.

### IPR: Intelligent Prompt Routing with Quality-Cost Tradeoffs

IPR (Intelligent Prompt Routing) specifically introduces a framework for managing quality-cost tradeoffs in LLM systems through user-controlled routing[40]. The IPRBench benchmark comprises 1.5 million prompts with quality rankings across multiple LLM families, establishing standardized evaluation for routing systems. The benchmark introduces an area-under-the-curve style metric named Bounded-ARQGC to measure quality-cost tradeoffs across different routing configurations[40].

This explicit focus on measurable quality-cost tradeoffs makes IPR particularly valuable for systems where cost considerations are primary. The Bounded-ARQGC metric provides quantitative assessment of router performance along the crucial dimension of balancing model quality against deployment cost.

## Infrastructure and Integration Considerations

Beyond the benchmarks themselves, successful routing evaluation requires infrastructure to execute identical tasks through multiple routing strategies while maintaining comparable metrics. This section addresses the practical challenges of integrating benchmarks into custom routing harnesses.

### Sandbox and Execution Environment Requirements

Robust code evaluation requires isolated execution environments that prevent generated code from affecting host systems or accessing sensitive data[43]. A well-designed coding agent sandbox provides filesystem isolation allowing agents read and write access without touching the host system, network policies blocking unauthorized egress, resource limits preventing runaway workloads, and ephemeral lifecycle auto-destroying environments after task completion[43].

Current major coding agents vary in sandboxing support: Claude Code uses Bubblewrap/Seatbelt with opt-in sandboxing, Gemini CLI uses Docker/Podman with opt-in protection, while OpenAI Codex ships with Landlock and seccomp enabled by default[43]. For benchmarking, implementing consistent sandbox infrastructure across all evaluation routes becomes critical—cloud-based routes typically provide sandboxing through cloud provider infrastructure, while local-only routes require Docker or similar containerization. Hybrid routing scenarios must ensure equivalent sandboxing across local and cloud execution paths to maintain measurement validity.

### Integration with LM Evaluation Harness

The LM Evaluation Harness provides a Python-based framework for evaluating language models on diverse NLP benchmarks including multiple-choice tasks, question answering, and classification[44]. While originally designed for broad NLP tasks, the Evaluation Harness can be extended to support custom code generation benchmarks through task-specific modules. Integration requires creating a task YAML configuration file specifying dataset parameters, output types, metrics definitions, and few-shot configurations[44].

The modular architecture of the Evaluation Harness enables flexible integration of custom benchmarks, though code generation tasks require specialized test execution infrastructure beyond the framework's core capabilities. Creating a custom benchmark within the Evaluation Harness framework involves: defining a task directory structure including dataset files and YAML configuration, implementing evaluation metrics through predefined or custom metric functions, specifying doc-to-text and doc-to-target conversion functions for proper prompt formatting, and configuring aggregation methods for multi-shot evaluation[44].

For routing evaluation, the Evaluation Harness could be extended to include router-specific task modules that execute identical prompts through different routes and aggregate results enabling cost-quality analysis. However, the Evaluation Harness's primary focus on NLP rather than code-specific challenges means custom infrastructure would likely still be necessary for comprehensive routing evaluation.

### Adapting Benchmarks for Multi-Route Evaluation

Executing benchmarks through multiple routing strategies (cloud-only, local-only, hybrid-architect with central coordinator, hybrid-minion with hierarchical structure) requires careful infrastructure design. The primary challenge involves ensuring that routing strategy differences do not introduce confounding variables affecting evaluation validity.

For cloud-only routing, models execute on cloud infrastructure—Perplexity AI, OpenAI, Anthropic APIs, or similar cloud services. Evaluation measures both solution quality and cloud API costs, capturing the full economic picture of cloud routing. For local-only routing, identical models execute on local infrastructure (laptops, edge servers, local cluster infrastructure), with evaluation capturing solution quality and local computational costs.

Hybrid-architect routing involves a central coordinating node that makes routing decisions, routing simpler tasks to local models and complex tasks to cloud services. The architecture requires implementing a router that predicts task complexity or difficulty and assigns tasks appropriately. Measurement must capture both the quality and the accuracy of routing decisions, as suboptimal routing (sending high-difficulty tasks to weak local models, for instance) introduces systematic quality degradation.

Hybrid-minion routing implements hierarchical structures where local "minion" models handle initial attempts at problems, escalating to cloud "architect" models only when local attempts fail or appear low-confidence. This architecture captures real-world development patterns where developers start with local tools and escalate to more powerful cloud services when necessary. Evaluation must measure both final solution quality and cost, tracking how frequently escalation occurs and whether escalation improves outcomes.

The critical infrastructure requirement across all routing strategies is result normalization. Benchmarks must produce comparable metrics across routing strategies despite potentially different code execution environments, latencies, and resource limitations. This typically requires standardizing on binary pass/fail metrics (does generated code pass all test cases?) rather than more nuanced quality gradations that might vary across infrastructure types.

### Contamination Detection and Mitigation

Data contamination represents a growing concern for code benchmarks, as models trained on increasingly large portions of internet data overlap substantially with public benchmark repositories[17]. Methods exist for detecting data contamination through analyzing loss distributions and comparing against contaminated reference models, but true contamination detection requires access to model training data or extensive probing[17].

For routing evaluation purposes, data contamination presents particular challenges because a router should ideally assign tasks based on task characteristics rather than whether the task appears in a model's training data. Contaminated knowledge of a specific benchmark problem should not drive routing decisions, as it provides false signals about genuine model capability on novel problems. This argues for using continually-updated benchmarks like LiveCodeBench that maintain fresh problem sets, or for careful temporal filtering of static benchmarks based on problem publication dates relative to model training cutoffs.

## Model Performance Across Benchmarks

Understanding how frontier and open-weight models perform across the diverse benchmark landscape is essential for contextualizing router design choices.

### Proprietary Frontier Models

Flagship proprietary models demonstrate strong performance across most code benchmarks. GPT-5.5 leads overall coding rankings with quality scores around 60.2, followed closely by Claude Opus 4.7 at 57.3 and Gemini 3.1 Pro Preview at 57.2[36]. On LiveCodeBench, GPT-4-turbo and Claude-3-Opus achieve top performance. On HumanEval, frontier models reach saturation with pass@1 rates exceeding 90 percent. SWE-bench represents a more challenging frontier where proprietary models achieve 70-76 percent accuracy, indicating substantial remaining difficulty in real-world software engineering tasks.

Claude Opus 4.5 shows particular strength on multi-file understanding and architectural reasoning, making it well-suited for complex repository-level tasks[36]. GPT-5.2 leads on raw code generation benchmarks including LiveCodeBench. Gemini 3 Ultra demonstrates strong code completion and debugging capabilities. The performance variation across benchmarks—high on HumanEval but lower on SWE-bench—indicates that benchmark diversity appropriately captures different capability dimensions.

### Open-Weight Models

Open-weight models have made substantial progress closing gaps with proprietary models, particularly for code generation. Qwen2.5-Coder 32B instruction variant achieves 92.7 percent on HumanEval Pro, competing directly with frontier proprietary model performance on this benchmark[2]. DeepSeek-R1 and DeepSeek V3 demonstrate strong coding capabilities through chain-of-thought reasoning approaches. GLM-4.7 Thinking achieves top performance among open-weight models on LiveCodeBench[36].

Open-weight models show more variable performance across different benchmark categories than proprietary models. On repository-level tasks (SWE-bench), open-weight models substantially trail frontier proprietary models—DeepSeek-R1 achieves 49.2 percent while Kimi K2.5 leads at 76.8 percent compared to proprietary models exceeding 70 percent[16]. This suggests that repository-level reasoning remains a capability frontier where proprietary models retain advantages despite open-weight models' strong performance on simpler benchmarks.

For routing decisions, this performance landscape suggests that local-only strategies using open-weight models should focus on simpler tasks (HumanEval-complexity code generation) where performance matches proprietary models, while hybrid strategies escalating complex repository-level tasks to cloud services would capture performance gains. Hybrid-minion architectures routing high-difficulty tasks to cloud services could substantially improve outcomes on benchmarks like SWE-bench.

### Model Size and Efficiency Considerations

Model size significantly impacts local feasibility and infrastructure costs. Smaller efficient models like Gemma 4 (26B effective through mixture-of-experts) achieve 85 tokens/second throughput on consumer hardware, making local deployment viable even on modest machines[5]. DeepSeek Coder V2 (21B effective) provides strong coding capability while remaining locally deployable. Larger open-weight models like Llama 3.3 70B or Mistral provide better quality but require substantial GPU memory (24+ GB) for viable local execution.

For routing decisions, this efficiency landscape suggests that hybrid architectures should employ efficient small models for initial local attempts (where quality requirements are modest) and reserve expensive large models for cases requiring highest quality output. The performance-efficiency frontier varies by benchmark: simple function generation might succeed with 3-8B models, while repository-level tasks typically require much larger models to achieve acceptable quality.

## Quality-Cost Tradeoff Evaluation

Effective routing depends on understanding quality-cost tradeoffs across different routing strategies. This section examines measurement approaches and benchmark suitability.

### Cost Dimensions in Code Evaluation

Cost considerations include multiple dimensions: cloud API costs (typically per million tokens), local computational costs (GPU hours, electricity), latency requirements (developer workflow expectations), and model training/fine-tuning costs for specialized models. Routing strategies must balance these dimensions against quality outcomes.

Cloud models incur explicit per-token costs but provide unlimited scalability and eliminate hardware investment requirements. For example, GPT-5.2 costs $1.50 per million input tokens and $14 per million output tokens, while Claude Sonnet 4.6 costs $3 per million input tokens and $15 per million output tokens[15]. Local models require substantial upfront GPU hardware investment but eliminate per-token costs for inference.

The quality-cost frontier differs across benchmarks. On HumanEval where many models achieve high accuracy, the relevant question becomes cost per correct solution rather than accuracy per se. On SWE-bench where frontier models achieve ~75 percent accuracy, quality differences dominate cost considerations. COMPASS's explicit multi-dimensional evaluation including efficiency provides direct quality-cost measurement through efficiency scoring[27].

### Frameworks for Tradeoff Measurement

Statsig's analysis of latency-quality tradeoffs in LLM systems provides generalizable frameworks applicable to routing: architect systems should expose rather than hide tradeoffs, push speed to the edge through local evaluation and caching, push quality to the core through richer features and heavier models, and bind tail risk through clear interpretation frameworks[28]. For code routing specifically, this suggests: maintaining local caches of common coding problems to avoid latency on repeated tasks, using lightweight local models for first-pass attempts at routine tasks, reserving high-quality cloud models for genuinely novel problems, and maintaining clear performance metrics that capture both speed and quality dimensions.

The IPR framework with its Bounded-ARQGC metric provides specific methodology for measuring quality-cost tradeoffs across routing configurations[40]. This metric could be adapted for code routing by computing area under the accuracy-cost curve as routing policies vary, enabling quantitative comparison of different routing strategies' efficiency.

### Benchmark Suitability for Cost-Quality Measurement

Most traditional code benchmarks (HumanEval, MBPP, SWE-bench) focus on accuracy metrics while ignoring cost dimensions. COMPASS's explicit inclusion of efficiency alongside correctness and code quality makes it particularly valuable for cost-quality tradeoff research[27]. BigCodeBench's focus on practical task automation provides realistic cost distributions if extended to track execution costs alongside correctness.

RouterBench and RouterEval, with their explicit inclusion of cost and latency data alongside accuracy, provide the most direct infrastructure for quality-cost measurement. These benchmarks document inference costs and latencies for each model-task combination, enabling evaluation of how routers allocate tasks across models to optimize quality-cost tradeoffs[20][21].

For custom routing harnesses, adapting existing benchmarks to measure quality-cost tradeoffs requires instrumenting execution to capture: problem difficulty/complexity (to test whether routers correctly identify task complexity), model-specific costs (API costs for cloud models, GPU hours for local models), actual execution times (to verify latency expectations), and quality outcomes (pass/fail on test cases). The primary infrastructure need is cost and latency tracking infrastructure that can be layered onto existing benchmarks.

## Benchmark Coverage Matrix and Routing Suitability

Synthesizing the benchmark landscape reveals substantial coverage across diverse coding capabilities but notable gaps in routing-specific evaluation. The following analysis identifies which benchmarks best support different routing evaluation scenarios.

Function-level code generation benchmarks (HumanEval, MBPP, EvalPlus variants) provide excellent baseline capability measurement with straightforward automation and clear pass/fail metrics. However, their relatively small problem sets and age (over 4 years for HumanEval) create data contamination concerns. For routing evaluation, these benchmarks effectively test local versus cloud performance on simple code generation where most models achieve high accuracy and cost differences dominate quality differences. Their primary limitation is lack of realistic task difficulty variation—most problems are essentially equivalent difficulty despite surface differences.

Repository-level benchmarks (SWE-bench, RepoBench, ClassEval, ComplexCodeEval) provide realistic complexity and strong performance differentiation between model qualities. However, larger benchmark size creates longer evaluation times, making frequent re-evaluation expensive. These benchmarks excel for identifying tasks where local models will reliably fail and cloud escalation becomes necessary. SWE-bench's 500-instance verified set provides computational feasibility while maintaining sufficient scale for statistical significance.

Holistic capability benchmarks (LiveCodeBench, BigCodeBench, COMPASS) provide diverse task types and contamination-free evaluation through continuous collection or competitive problem sourcing. LiveCodeBench's multi-capability focus (generation, self-repair, execution) and continuous updates make it exceptionally valuable for ongoing router validation. However, continuous problem updates complicate longitudinal comparison of router strategies over time.

Routing-specific benchmarks (RouterBench, RouterEval, IPR) provide the most direct infrastructure for routing evaluation but require adaptation to focus on code-specific subsets. RouterBench's 405k+ inference records provide sufficient scale for router training, while RouterEval's 200M+ records enable training sophisticated routing policies. The primary limitation is these benchmarks' focus on routing systems themselves rather than on code quality measurement—integrating them with code-specific evaluation requires careful alignment.

Domain-specialized benchmarks (Spider for SQL, DS-1000 for data science, StackEval for Stack Overflow, CRUXEval for reasoning) enable targeted evaluation of specialized capabilities. A comprehensive routing system targeting diverse programming domains would need to incorporate multiple domain-specific benchmarks.

## Practical Integration Considerations

Successfully integrating benchmarks into custom routing harnesses requires addressing several practical challenges beyond benchmark selection.

### Dataset Management and Versioning

Benchmarks evolve over time—test cases expand, problems get corrected, new variants emerge. Maintaining reproducible routing evaluation requires rigorous dataset versioning. HumanEval inconsistencies with 164 versus 161 instances across different implementations illustrate how version mismatches create incomparable evaluation results[41]. For routing evaluation tracking performance over time, using specific benchmark versions is essential to ensure results remain comparable.

### Licensing and Commercial Deployment

Benchmark licensing significantly impacts commercial viability of routing solutions. Most academic benchmarks (HumanEval, MBPP, LiveCodeBench) permit academic and commercial research use. However, deploying routing systems in production that fundamentally depend on specific benchmarks for optimization requires confirming licensing permits such use. Open-source licenses dominating code benchmarks (Apache 2.0, MIT, custom research licenses) generally permit commercial research use but should be verified per specific benchmark[33][39].

### Performance Measurement Infrastructure

Implementing consistent performance measurement across routing strategies requires instrumentation capturing multiple metrics: accuracy/correctness (does generated code pass tests), execution time (latency of solution generation), resource consumption (GPU hours for local execution, API token usage for cloud), and cost (actual dollars spent or GPU hour equivalents). This instrumentation must be consistent across routing strategies to enable fair comparison.

### Sandbox and Security Considerations

Code evaluation requires executing potentially untrusted generated code safely. This becomes more complex in hybrid routing scenarios where code execution might occur either locally or in cloud environments. Ensuring consistent security properties across both execution locations is critical—executing unsafe code on local machines poses host compromise risks while cloud execution requires trusting cloud provider security.

## Synthesis and Routing Evaluation Framework Recommendations

Designing an optimal routing evaluation framework requires combining insights across the diverse benchmark landscape. A comprehensive approach would include a multi-tier benchmark suite: foundational function-level benchmarks (HumanEval, MBPP+, EvalPlus variants) for rapid iteration and baseline capability assessment, repository-level benchmarks (SWE-bench Verified, ClassEval, ComplexCodeEval) for realistic task complexity and challenging scenarios, holistic capability benchmarks (LiveCodeBench, BigCodeBench) for continuous validation and comprehensive capability measurement, and routing-specific frameworks (RouterBench subset with code focus, IPR methodology) for explicit quality-cost tradeoff measurement.

For integrating into custom routing harnesses, the minimum viable implementation would require: problem definition and specification (from benchmark datasets), solution generation (by routing different models based on strategy), execution in isolated sandboxes (capturing both local and cloud executions), test verification (binary pass/fail metrics), and cost-quality aggregation (comparing total cost against quality outcomes across routing strategies).

The most practical starting point for routing evaluation would focus on LiveCodeBench (contamination-free, comprehensive capabilities, multiple problem types) and SWE-bench Verified (realistic complexity, sufficient scale, good tool support), using these two benchmarks to establish baseline routing performance. This combination provides coverage from straightforward code generation to complex real-world engineering tasks. Adding RouterBench's framework for cost-quality measurement would enable explicit optimization toward quality-cost frontiers rather than pure quality maximization.

## Conclusion

The 2026 code evaluation benchmark landscape offers unprecedented breadth and sophistication compared to earlier years. Function-level benchmarks provide essential baselines but have reached saturation for frontier models. Repository-level benchmarks provide realistic complexity and strong performance differentiation. Holistic frameworks capture diverse coding capabilities beyond simple generation. Routing-specific evaluation frameworks enable systematic optimization of cost-quality tradeoffs.

Successfully leveraging this benchmark ecosystem for routing evaluation requires careful selection of complementary benchmarks, rigorous infrastructure for multi-route execution, clear cost-quality measurement frameworks, and ongoing attention to data contamination concerns. The availability of robust routing-specific benchmarks like RouterBench and frameworks like IPR provides unprecedented capability for optimizing local-cloud hybrid systems. The combination of established benchmarks (HumanEval, SWE-bench) with continually-updated alternatives (LiveCodeBench) creates opportunity for both rigorous standardized evaluation and ongoing validation against emerging coding practices.

For practitioners implementing routing systems, the recommended approach combines HumanEval or MBPP for foundational capability verification (rapid iteration, numerous tools support), SWE-bench Verified for realistic complexity assessment (identifies real-world failure modes), LiveCodeBench for continuous validation (contamination-free, multi-capability focus), and RouteEval framework for explicit cost-quality optimization (enables principled routing decisions). This multi-tier approach balances evaluation rigor, practical feasibility, and alignment with the core routing optimization objective: maximizing delivered quality for constrained cost budgets through intelligent routing decisions.

### Citations

1. https://github.com/openai/human-eval
2. https://arxiv.org/html/2412.21199v2
3. https://www.swebench.com
4. https://arxiv.org/html/2506.13832v2
5. https://till-freitag.com/en/blog/open-source-llm-comparison
6. https://github.com/FudanSELab/ClassEval
7. https://livecodebench.github.io
8. https://huggingface.co/datasets/bigcode/bigcodebench-hard
9. https://evalplus.github.io
10. https://epoch.ai/benchmarks/aider-polyglot
11. https://yale-lily.github.io/spider
12. https://github.com/ProsusAI/stack-eval
13. https://ds1000-code-gen.github.io
14. https://arxiv.org/html/2406.11927v4
15. https://www.vellum.ai/llm-leaderboard
16. https://www.vellum.ai/open-llm-leaderboard
17. https://www.computer.org/csdl/proceedings-article/apsec/2025/665300b045/2emQQj1FdPa
18. https://arxiv.org/abs/2403.12031
19. https://arxiv.org/html/2404.14618v1
20. https://arxiv.org/html/2403.12031v1
21. https://arxiv.org/abs/2503.10657
22. https://arxiv.org/html/2604.18543v2
23. https://llm-stats.com/benchmarks/mbpp
24. https://arxiv.org/html/2406.12655v1
25. https://arxiv.org/html/2409.10280v1
26. https://crux-eval.github.io
27. https://arxiv.org/html/2508.13757v1
28. https://www.statsig.com/perspectives/latency-quality-tradeoffs
29. https://github.com/bigcode-project/bigcodebench
30. https://aider.chat/docs/benchmarks.html
31. https://github.com/gersteinlab/ML-Bench
32. https://appworld.dev
33. https://opensource.org/blog/top-open-source-licenses-in-2025
34. https://artificialanalysis.ai/evaluations/livecodebench
35. https://arxiv.org/html/2507.05281v1
36. https://whatllm.org/best-llm-for-coding
37. https://github.com/Leolty/repobench
38. https://www.giskard.ai/glossary/codecontests-coding-benchmark
39. https://github.com/eugeneyan/open-llms
40. https://arxiv.org/html/2509.06274v3
41. https://github.com/noahshinn/reflexion/issues/42
42. https://github.com/google-research/google-research/tree/master/mbpp
43. https://www.bunnyshell.com/guides/coding-agent-sandbox/
44. https://huggingface.co/blog/Neo111x/integrating-benchmarks-into-lm-evaluation-harness

---

## Exa Deep Search  (15 sources)

### 1. AI Coding Benchmarks 2026: Every Major Eval Explained and Ranked
**URL:** https://www.morphllm.com/ai-coding-benchmarks-2026
**Published:** 2026-03-06T16:47:00.000Z

AI Coding Benchmarks 2026: Every Major Eval Explained and Ranked

# AI Coding Benchmarks in 2026: Every Major Eval Explained and Ranked

SWE-Bench Verified, SWE-Bench Pro, Terminal-Bench, Aider Polyglot, LiveCodeBench, HumanEval. Complete guide to AI coding benchmarks in 2026 with scores for Claude Opus 4.6, GPT-5.3 Codex, Gemini 3.1 Pro, and more.

March 6, 2026 · 1 min read

Six benchmarks, six different leaderboards. This guide covers what each AI coding benchmark actually tests, the current scores for every frontier model, and which evaluation matters for your use case.

Scores updated March 6, 2026

## Leaderboard Summary: Models Across Benchmarks

No model wins every benchmark. The rankings shift depending on what you measure. This table gives a cross-benchmark view of the five most-cited frontier models.

~80.9%

Top SWE-Bench Verified

~45.9%

Top SWE-Bench Pro (SEAL)

~77.3%

Top Terminal-Bench

~85%

Top Aider Polyglot

| Model/Agent | SWE-Bench Verified | SWE-Bench Pro (SEAL) | Terminal-Bench | Aider Polyglot |
| --- | --- | --- | --- | --- |
| Claude Opus 4.6 | ~80.9% | ~45.9%* | ~65.4% | ~85% |
| GPT-5.3 Codex | ~77.3%** | ~41.8%*** | ~77.3% | ~80% |
| Gemini 3.1 Pro | ~80.6% | ~43.3% | ~77.3% | ~78% |
| Qwen 3.5 | ~72% | ~38.7% | N/A | ~75% |
| DeepSeek V3.2 | ~73% | ~33% | N/A | ~72% |

*Opus 4.5 score on SEAL. **GPT-5.2 score (5.3 not separately reported on Verified). ***GPT-5 High on SEAL. Aider Polyglot scores are approximate from aider.chat leaderboard.

Claude Opus 4.6 leads SWE-Bench Verified, but trails GPT-5.3 Codex and Gemini 3.1 Pro on Terminal-Bench by 12 points. Gemini 3.1 Pro is competitive across all four benchmarks. DeepSeek V3.2 and Qwen 3.5 score lower across the board but cost a fraction per token.

## SWE-Bench Verified

### What it tests

Real GitHub issues from popular Python repos (Django, Matplotlib, Scikit-learn, etc.). ~500 human-validated tasks from the original 2,294. Each task is a real bug report paired with a test that must pass.

### Who runs it

Princeton NLP Group, originally by Carlos E. Jimenez et al. The most-cited benchmark for AI coding agents since its introduction in 2023.

### Strengths and limits

Real-world tasks from real repos. But Python-only, single-repo, and contaminated. OpenAI confirmed every frontier model shows training data leakage.

| Rank | Model | Score | Provider |
| --- | --- | --- | --- |
| 1 | Claude Opus 4.5 | 80.9% | Anthropic |
| 2 | Claude Opus 4.6 | 80.8% | Anthropic |
| 3 | Gemini 3.1 Pro | 80.6% | Google |
| 4 | MiniMax M2.5 | 80.2% | MiniMax |
| 5 | GPT-5.2 | 80.0% | OpenAI |
| 6 | Claude Sonnet 4.6 | 79.6% | Anthropic |
| 7 | Gemini 3 Flash | 78.0% | Google |
| 8 | Claude Sonnet 4.5 | 77.2% | Anthropic |
| 9 | Kimi K2.5 | 76.8% | Moonshot |
| 10 | Claude Haiku 4.5 | 73.3% | Anthropic |
| 11 | DeepSeek V3.2 | 73.0% | DeepSeek |

#### Contamination caveat

OpenAI confirmed that every frontier model shows training data contamination on SWE-Bench Verified, and 59.4% o

*… (13,571 more characters — see results.json for full text)*

---

### 2. EvalPlus Leaderboard
**URL:** https://evalplus.github.io/leaderboard.html

EvalPlus Leaderboard

# 🏆 EvalPlus Leaderboard 🏆

### EvalPlus evaluates AI Coders with rigorous tests.

📢 News: Beyond correctness, how's their code efficiency? Checkout🚀EvalPerf!

HumanEval MBPP Average

⚡EvalPlus Tests⚡

Base Tests

### 📝 Notes

1. Evaluated using HumanEval+ version 0.1.10; MBPP+ version 0.2.0.
2. Models are ranked according to pass@1 using greedy decoding. Setup details can be found here.
3. ✨ marks models evaluated using a chat setting, while others perform direct code completion.
4. Both MBPP and MBPP+ referred in our leaderboard use a subset (399 tasks) of hand-verified problems from MBPP-sanitized (427 tasks), to make sure the programming task is well-formed (e.g., test_list is not wrong).
5. Model providers have the responsibility to avoid data contamination. Models trained on close data can be affected by contamination.
6. 💚 means open weights and open data. 💙 means open weights and open SFT data, but the base model is not data-open. What does this imply? 💚💙 models open-source the data such that one can concretely reason about contamination.
7. "Size" here is the amount of activated model weight during inference.

### 🤗 More Leaderboards

In addition to EvalPlus leaderboards, it is recommended to comprehensively understand LLM coding ability through a diverse set of benchmarks and leaderboards, such as:

---

### 3. Code Completion and Generation LLM Leaderboard 2026 | Awesome Agents
**URL:** https://awesomeagents.ai/leaderboards/code-completion-llm-leaderboard/
**Published:** 2026-04-19T00:00:00.000Z

Code Completion and Generation LLM Leaderboard 2026 | Awesome Agents

I need to say something upfront that most coverage of code completion benchmarks glosses over: HumanEval is compromised. Not broken in the sense that the problems are wrong - Chen et al.'s 164 Python function stubs remain a reasonable test of basic algorithmic reasoning. Compromised in the sense that the entire dataset has been public since July 2021, and every model trained in the last three-plus years has almost certainly seen it. When you read a headline claiming some new model scores 98% on HumanEval, you are not reading a coding ability score. You are reading a memorization upper bound.

That does not mean HumanEval is useless. It is still a reasonable sanity check, a baseline that lets you compare a new model to a long historical record. What it is not is a reliable indicator of how well that model will complete functions it has never seen before. For that, you need LiveCodeBench.

This leaderboard covers pure code authoring: complete a function given a signature or docstring, generate a full solution from a spec, place in a competitive programming contest. It does not cover code review (see the LLM Code Review Leaderboard) or full-repository agent tasks (see the SWE-Bench Coding Agent Leaderboard).

TL;DR

- Claude Opus 4 and GPT-5 lead on contamination-resistant LiveCodeBench; HumanEval numbers are largely untrustworthy at the frontier
- DeepSeek-V3 and Qwen3-Coder are the strongest open-weight options and genuinely competitive with frontier closed models on LiveCodeBench
- BigCodeBench is a better signal than HumanEval for realistic library-usage tasks - harder and less contaminated
- Competitive programming benchmarks (APPS Hard, CodeContests, LCB Hard) show a large gap between reasoning-capable models and standard code models
- Qwen 2.5-Coder 32B remains the strongest sub-40B open-weight model for code-specific deployments

## The Benchmark Landscape - What to Trust and What to Ignore

### HumanEval and MBPP - Useful History, Unreliable Frontier Scores

HumanEval(OpenAI, 2021) is 164 hand-written Python programming problems, each consisting of a function signature and docstring. The canonical metric is pass@1: generate one solution and check if it passes the test suite. The benchmark has been cited in essentially every code LLM paper published since 2021. That ubiquity is the problem. The tasks are public. The canonical correct solutions are public. Every training dataset scraped from GitHub, code forums, and ML papers after mid-2021 has almost certainly included HumanEval task descriptions and solutions.

MBPP(Google, 2021) - Mostly Basic Python Problems - is similarly compromised by age. 374 crowdsourced programming tasks drawn from beginner Python exercises. Again, public since 2021 and in every major training corpus.

EvalPlus(2023) partially addresses this by augmenting HumanEval and MBPP with automatically generated additional test cases, creating HumanEval+ an

*… (21,004 more characters — see results.json for full text)*

---

### 4. evalplus/evalplus
**URL:** https://github.com/evalplus/evalplus
**Published:** 2023-04-15T04:20:10.000Z

# Repository: evalplus/evalplus

Rigourous evaluation of LLM-synthesized code - NeurIPS 2023 & COLM 2024

- Stars: 1704
- Forks: 192
- Watchers: 1704
- Open issues: 58
- Primary language: Python
- Languages: Python (99.7%), Shell (0.2%), Dockerfile (0.1%)
- License: Apache License 2.0 (Apache-2.0)
- Topics: benchmark, chatgpt, efficiency, gpt-4, large-language-models, program-synthesis, testing
- Default branch: master
- Homepage: https://evalplus.github.io
- Created: 2023-04-15T04:20:10Z
- Last push: 2025-10-02T22:56:38Z
- Contributors: 30 (top: ganler, Kristoff-starling, brutalsavage, soryxie, FatPigeorz, Co1lin, CL-ModelCloud, UniverseFly, nalinabrol, terryyz)
- Releases: 11
- Latest release: v0.3.1 (2024-10-20T21:59:03Z)

---

# `EvalPlus(📖) => 📚`

 
 
 
 
 
 
 
 

 
 📙About •
 🔥Quick Start •
 🚀LLM Backends •
 📚Documents •
 📜Citation •
 🙏Acknowledgement 
 

## 📢 News

Who's using EvalPlus datasets? EvalPlus has been used by various LLM teams, including:

- [Meta Llama 3.1 and 3.3](https://ai.meta.com/blog/meta-llama-3-1/)
- [Allen AI TÜLU 1/2/3](https://github.com/allenai/open-instruct/blob/main/docs/tulu1_tulu2.md#benchmark-based-eval)
- [Qwen2.5-Coder](https://qwenlm.github.io/blog/qwen2.5-coder-family/)
- [CodeQwen 1.5](https://qwenlm.github.io/blog/codeqwen1.5/)
- [DeepSeek-Coder V2](https://arxiv.org/pdf/2406.11931)
- [Qwen2](https://arxiv.org/pdf/2407.10671)
- [Snowflake Arctic](https://www.snowflake.com/en/data-cloud/arctic/)
- [StarCoder2](https://arxiv.org/pdf/2402.19173)
- [Magicoder](https://arxiv.org/pdf/2312.02120)
- [WizardCoder](https://arxiv.org/pdf/2306.08568)

Below tracks the notable updates of EvalPlus:

- **[2024-10-20 `v0.3.1`]**: EvalPlus `v0.3.1` is officially released! Highlights: *(i)* Code efficiency evaluation via EvalPerf, *(ii)* one command to run all: generation + post-processing + evaluation, *(iii)* support for more inference backends such as Google Gemini & Anthropic, etc.
- **[2024-06-09 pre `v0.3.0`]**: Improved ground-truth solutions for MBPP+ tasks (IDs: 459, 102, 559). Thanks to [EvalArena](https://github.com/crux-eval/eval-arena).
- **[2024-04-17 pre `v0.3.0`]**: MBPP+ is upgraded to `v0.2.0` by removing some broken tasks (399 -> 378 tasks). ~4pp pass@1 improvement could be expected.

 Earlier news:: click to expand :: 
 

- ([`v0.2.1`](https://github.com/evalplus/evalplus/releases/tag/v0.2.1)) You can use EvalPlus datasets via [bigcode-evaluation-harness](https://github.com/bigcode-project/bigcode-evaluation-harness)! HumanEval+ oracle fixes (32).
- ([`v0.2.0`](https://github.com/evalplus/evalplus/releases/tag/v0.2.0)) MBPP+ is released! HumanEval contract & input fixes (0/3/9/148/114/1/2/99/28/32/35/160).
- ([`v0.1.7`](https://github.com/evalplus/evalplus/releases/tag/v0.1.7)) [Leaderboard](https://evalplus.github.io/leaderboard.html) release; HumanEval+ contract and input fixes (32/166/126/6)
- ([`v0.1.6`](https://github.com/evalplus/evalplus/releases/tag/v0.1.6)) Configurable and by-default-conserva

*… (11,679 more characters — see results.json for full text)*

---

### 5. AI Code Generation Benchmarks 2026: Which Model Actually Writes Better Code? | Groundy
**URL:** https://groundy.com/articles/ai-code-generation-benchmarks-2026-which-model-actually/
**Published:** 2026-02-15T00:00:00.000Z

AI Code Generation Benchmarks 2026: Which Model Actually Writes Better Code? | Groundy

Table of Contents

The AI coding assistant landscape has transformed dramatically. As of February 2026, GPT-4o demonstrates strong performance on HumanEval with approximately 90% accuracy, and open-source models like Qwen2.5-Coder-32B have achieved parity with closed-source alternatives on standard benchmarks. However, the gap between benchmark performance and real-world software engineering remains substantial—with even the best models achieving only around 80% on SWE-bench Verified (according to claimed scores), a benchmark based on actual GitHub issue resolution.

## What Are AI Code Generation Benchmarks?

AI code generation benchmarks are standardized test suites designed to evaluate how well large language models (LLMs) can write, understand, and debug computer code. These benchmarks emerged from a fundamental need: as models began generating increasingly complex code, developers needed objective ways to measure progress and compare capabilities.

The first widely adopted benchmark, HumanEval, was introduced by OpenAI in 2021 alongside their Codex model. It consists of 164 handwritten Python programming problems with unit tests. Each problem provides a function signature and docstring, requiring the model to generate the implementation. The metric pass@k measures the probability that at least one of k generated samples passes all unit tests.

Beyond HumanEval, the ecosystem has expanded to include:

- MBPP (Mostly Basic Python Problems): 974 crowd-sourced Python programming problems
- EvalPlus: Rigorous extensions of HumanEval and MBPP with significantly more comprehensive test suites
- SWE-bench: Tests models on resolving real GitHub issues from 12 popular Python repositories
- LiveCodeBench: Continuously collects new problems from competitive programming platforms to avoid data contamination
- Aider: Real-world code editing benchmark measuring performance on actual repository modifications

## How Do Current Benchmarks Work?

Modern code generation evaluation operates on multiple dimensions of capability. The most rigorous frameworks now assess not just whether code runs, but whether it runs correctly, efficiently, and maintainably.

### Correctness Evaluation

EvalPlus, developed by researchers at the University of Illinois Urbana-Champaign and presented at NeurIPS 2023, represents the gold standard for correctness evaluation. Their HumanEval+ benchmark augments the original 164 problems with 80x more tests, while MBPP+ adds 35x more tests to MBPP. This expansion is critical: the original HumanEval’s sparse test coverage allowed models to achieve high scores with fragile solutions that fail on edge cases.

The evaluation process works as follows:

1. The model receives a function signature, docstring, and potentially example usage
2. It generates one or more code completions
3. Each completion is executed against the hidden test suite
4. A “pass” requ

*… (10,435 more characters — see results.json for full text)*

---

### 6. BigCodeBench Leaderboard
**URL:** https://bigcode-bench.github.io/

BigCodeBench Leaderboard

# 🌸 BigCodeBench Leaderboard

### BigCodeBench evaluates LLMs with practical and challenging programming tasks.

Hard Full

Complete Instruct Average

Recommendation Size View Time View

Show Models with Unknown Sizes

### 📝 Notes

1. Evaluated using BigCodeBench;
2. Hard Set vs Full Set: Hard Set: A subset of ~150 BigCodeBench tasks which is more user-facing and challenging. Full Set: The full set of 1140 BigCodeBench tasks.
3. Models are ranked according to (calibrated) Pass@1 using greedy decoding. Setup details can be found here.
4. Complete vs Instruct: Complete: Code Completion based on the structured long-context docstring. This variant tests if the models are good at coding. Instruct (🔥Vibe Check🔥): Code Generation based on the brief NL-oriented instructions. This variant tests if the models are really capable enough to understand human intents to code.
5. Wonder the relative performance among models, or the current progress of task solve rate? Check out the🤗 Hugging Face Leaderboard!
6. 🧠 indicates an evaluation setup without response prefilling during generation, potentially leading to the reasoning process.
7. ✨ marks models evaluated using a chat setting, while others perform direct code completion. We note that some instruction-tuned models miss the chat template in their tokenizer configuration.
8. Model providers have the responsibility to avoid data contamination. Models trained on close data can be affected by contamination.
9. 💚 means open weights and open data. 💙 means open weights and open SFT data, but the base model is not data-open. What does this imply? 💚💙 models open-source the data such that one can concretely reason about contamination.
10. "Size" here is the number of model parameters during inference.

### 🤗 More Leaderboards

In addition to BigCodeBench leaderboards, it is recommended to comprehensively understand LLM coding ability through a diverse set of benchmarks and leaderboards, such as:

### 🙏 Acknowledgements

- We thank the EvalPlus team for providing the leaderboard template.
- We are grateful for the significant contributions from the BigCode community.

---

### 7. BigCodeBench Benchmark - AI Code Generation Leaderboard (2026) | LM Market Cap
**URL:** https://lmmarketcap.com/benchmarks/bigcodebench



 

 

 

 

BigCodeBench Benchmark - AI Code Generation Leaderboard (2026) | LM Market Cap

[Skip to content](#main-content)
[LMMarketCap.comLMMC](https://lmmarketcap.com/)
⌘K
EN
Menu
⌘K
EN
Loading rankings...
Last updated: 39m agoApril 2, 2026 at 08:02 AM
Coding benchmark
# BigCodeBench (Hard) Leaderboard
Practical code generation requiring use of libraries, APIs, and complex program structures. The 'Hard' subset tests non-trivial engineering tasks.
Why it matters: More realistic than HumanEval — tests practical programming skills including library usage, API calls, and multi-file reasoning.
Top Model
72.1%
Claude Opus 4.6
Average Score
66.9%
Across 3 models
Models Tested
3
Metric: pass@1
Human Baseline
-
Score Range: 0%–100%
## Model Rankings
All models with a reported BigCodeBench score, ranked by highest pass@1.
RankModelScorePerformance
#1
[Claude Opus 4.6](https://lmmarketcap.com/model/claude-opus-4-6)[Anthropic](https://lmmarketcap.com/providers/anthropic)
72.1%
72%
72.1%
#2
[Claude Sonnet 4.6](https://lmmarketcap.com/model/claude-sonnet-4-6)[Anthropic](https://lmmarketcap.com/providers/anthropic)
68.4%
68%
68.4%
#3
[Qwen 2.5 Coder 32B](https://lmmarketcap.com/model/qwen-2.5-coder-32b-instruct)[Alibaba](https://lmmarketcap.com/providers/alibaba)
60.2%
60%
60.2%
## About BigCodeBench
Full NameBigCodeBench (Hard)
CategoryCoding
Metricpass@1 (%)
Score Range0%–100%
Human BaselineNot established
StatusActive
Frequently Asked Questions
What is the BigCodeBench benchmark?
BigCodeBench is a standardized evaluation that measures AI model performance on specific tasks. It provides comparable scores across different models, helping developers choose the right model for their needs.
Which AI model scores highest on BigCodeBench?
Claude Opus 4.6 currently holds the top score on the BigCodeBench benchmark. See our full rankings table above for the complete leaderboard with 3 models.
How often are BigCodeBench scores updated?
We update benchmark data from multiple sources including HuggingFace Open LLM Leaderboard and LMArena. Scores are refreshed regularly as new evaluations are published and new models are released.
Are BigCodeBench scores the only thing that matters?
No. While BigCodeBench is an important indicator, real-world performance depends on many factors including pricing, latency, context window, and specific task requirements. We recommend using our composite score which weighs multiple benchmarks and practical factors.
## Related Benchmarks
[MMLUKnowledge](https://lmmarketcap.com/benchmarks/mmlu)[MMLU-ProKnowledge](https://lmmarketcap.com/benchmarks/mmlu_pro)[GPQA DiamondReasoning](https://lmmarketcap.com/benchmarks/gpqa_diamond)[MATH-500Math](https://lmmarketcap.com/benchmarks/math_500)[HumanEvalCoding](https://lmmarketcap.com/benchmarks/humaneval)[SWE-bench VerifiedCoding](https://lmmarketcap.com/benchmarks/swe_bench_verified)[AIME 2024Math](https://lmmarketcap.com/benchmarks/aime_2024)[GSM8KMath](https://lmmarketcap.com/benchmarks/gsm8

*… (381 more characters — see results.json for full text)*

---

### 8. bigcode-project/bigcodebench
**URL:** https://github.com/bigcode-project/BigCodeBench
**Published:** 2024-04-29T11:46:10.000Z

# Repository: bigcode-project/bigcodebench

[ICLR'25] BigCodeBench: Benchmarking Code Generation Towards AGI

- Stars: 495
- Forks: 69
- Watchers: 495
- Open issues: 29
- Primary language: Python
- Languages: Python (95.0%), Dockerfile (4.3%), Shell (0.6%)
- License: Apache License 2.0 (Apache-2.0)
- Topics: agent, agents, benchmark, chatgpt, claude-3, code-generation, deepseek, function-calling, gemini, gpt-4, instruction-following, large-language-models, llm, program-synthesis, tool-use
- Default branch: main
- Homepage: https://bigcode-bench.github.io/
- Created: 2024-04-29T11:46:10Z
- Last push: 2026-01-03T07:22:42Z
- Contributors: 20 (top: terryyz, ganler, Kristoff-starling, brutalsavage, hvaara, FatPigeorz, soryxie, marianna13, UniverseFly, Devy99)
- Releases: 13
- Latest release: v0.2.5 (2025-04-11T09:01:49Z) [prerelease]

---

# BigCodeBench

 
 
 

 
 
 
 
 
 
 
 
 
 

 
 💥 Impact •
 📰 News •
 🔥 Quick Start •
 🚀 Remote Evaluation •
 💻 LLM-generated Code •
 🧑 Advanced Usage •
 📰 Result Submission •
 📜 Citation 
 

 
 🎉 Check out our latest work! 
 🌟 BigCodeArena 🌟 
 🚀 Open Evaluation Platform on AI for Vibe Coding 🚀 
 ✨ 100% free to use the latest frontier models! ✨ 
 

## 💥 Impact

BigCodeBench has been trusted by many LLM teams including:

- Zhipu AI
- Alibaba Qwen
- DeepSeek
- Amazon AWS AI
- Snowflake AI Research
- ServiceNow Research
- Meta AI
- Cohere AI
- Sakana AI
- Allen Institute for Artificial Intelligence (AI2)

## 📰 News

- **[2025-01-22]** We are releasing `bigcodebench==v0.2.2.dev2`, with 163 models evaluated!
- **[2024-10-06]** We are releasing `bigcodebench==v0.2.0`!
- **[2024-10-05]** We create a public code execution API on the [Hugging Face space](https://huggingface.co/spaces/bigcode/bigcodebench-evaluator).
- **[2024-10-01]** We have evaluated 139 models on BigCodeBench-Hard so far. Take a look at the [leaderboard](https://huggingface.co/spaces/bigcode/bigcodebench-leaderboard)!
- **[2024-08-19]** To make the evaluation fully reproducible, we add a real-time code execution session to the leaderboard. It can be viewed [here](https://huggingface.co/spaces/bigcode/bigcodebench-leaderboard).
- **[2024-08-02]** We release `bigcodebench==v0.1.9`.

 More News:: click to expand :: 
 

- **[2024-07-18]** We announce a subset of BigCodeBench, BigCodeBench-Hard, which includes 148 tasks that are more aligned with the real-world programming tasks. The details are available [in this blog post](https://huggingface.co/blog/terryyz/bigcodebench-hard). The dataset is available [here](https://huggingface.co/datasets/bigcode/bigcodebench-hard). The new release is `bigcodebench==v0.1.8`.
- **[2024-06-28]** We release `bigcodebench==v0.1.7`.
- **[2024-06-27]** We release `bigcodebench==v0.1.6`.
- **[2024-06-19]** We start the Hugging Face BigCodeBench Leaderboard! The leaderboard is available [here](https://huggingface.co/spaces/bigcode/bigcodebench-leaderboard).
- **[2024-06-18]** We release BigCodeBench, a new benchmark for code genera

*… (7,340 more characters — see results.json for full text)*

---

### 9. LiveCodeBench: Holistic and Contamination Free Evaluation of Large
    Language Models for Code
**URL:** https://livecodebench.github.io/

LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code

# LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code

1UC Berkeley 2MIT 3Cornell University

## LiveCodeBench collects problems from periodic contests on LeetCode, AtCoder, and Codeforces platforms and uses them for constructing a holistic benchmark for evaluating Code LLMs across variety of code-related scenarios continuously over time.

## Introduction

LiveCodeBench is a holistic and contamination-free evaluation benchmark of LLMs for code that continuously collects new problems over time. Particularly, LiveCodeBench also focuses on broader code-related capabilities, such as self-repair, code execution, and test output prediction, beyond mere code generation. Currently, LiveCodeBench hosts over three hundred high-quality coding problems published between May 2023 and February 2024. We evaluate 29 LLMs on LiveCodeBench scenarios and present novel empirical findings not revealed in prior benchmarks.

## Contamination

LiveCodeBench annotates problems with release dates, and thus allows evaluating models on problems released during a specific time period. Thus, for a newer model with a training-cutoff date D, we can evaluate it on problems released after D to measure its generalization on unseen problems.

The above plots depict the performance of models on code generation and test output prediction scenarios on problems released over different months. We find that DeepSeek models exhibit a stark drop in performance on LeetCode problems released since September 2023, its release date, indicating that the earlier problems might be contaminated. In contrast, for GPT models, the performance is relatively stable across different months.

## Holistic Evaluation and Open vs Closed Models

LiveCodeBench evaluates models on a variety of code-related scenarios, such as code generation, self-repair, test output prediction, and code execution. We find that while model performances are correlated across different scenarios, there relative performances and ordering can vary (left figure). For instance, Claude-3-Opus overtakes GPT-4-turbo in the test output prediction scenario, but not in the code generation scenario. Similarly, Mistral-Large performs considerably better on natural language reasoning tasks like test output prediction and code execution.

We compare the performance of open access models with closed api-access models on LiveCodeBench and find that generally the closed api-access models outperform the open models. Particularly, the only open models that surpass the barrier are fine-tuned variants of large (30+B parameter) models.

## Potential Overfitting in HumanEval

We also find that models that perform well on HumanEval might be overfitting on the benchmark. Particularly, the models are separated into two clusters depicted by the green and red shaded region in the right scatterplot. The models in the green regi

*… (1,613 more characters — see results.json for full text)*

---

### 10. jmagly/LiveCodeBench
**URL:** https://github.com/jmagly/LiveCodeBench
**Published:** 2026-01-25T18:27:04.000Z

# Repository: jmagly/LiveCodeBench (fork of [LiveCodeBench/LiveCodeBench](https://github.com/LiveCodeBench/LiveCodeBench))

Official repository for the paper "LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code"

- Stars: 0
- Forks: 0
- Watchers: 0
- Open issues: 0
- Primary language: Python
- Languages: Python
- License: MIT License (MIT)
- Default branch: main
- Homepage: https://livecodebench.github.io/
- Created: 2026-01-25T18:27:04Z
- Last push: 2025-07-16T00:58:38Z
- Contributors: 20 (top: Naman-ntc, jyoo980, tomscohere, sreemanti-abacusai, plaguss, arkapal3, catherinewu, kcxain, Fanjia-Yan, eltociear)

---

# LiveCodeBench

Official repository for the paper "LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code"

 
 🏠 Home Page •
 💻 Data •
 🏆 Leaderboard •
 🔍 Explorer 
 

## Introduction

LiveCodeBench provides holistic and contamination-free evaluation of coding capabilities of LLMs. Particularly, LiveCodeBench continuously collects new problems over time from contests across three competition platforms -- LeetCode, AtCoder, and CodeForces. Next, LiveCodeBench also focuses on a broader range of code-related capabilities, such as self-repair, code execution, and test output prediction, beyond just code generation. Currently, LiveCodeBench hosts four hundred high-quality coding problems that were published between May 2023 and March 2024.

## Installation

You can clone the repository using the following command:

```bash
git clone https://github.com/LiveCodeBench/LiveCodeBench.git
cd LiveCodeBench
```

We recommend using [uv](https://github.com/astral-sh/uv)
for managing dependencies, which can be installed a [number of ways](https://github.com/astral-sh/uv?tab=readme-ov-file#installation).

Verify that `uv` is installed on your system by running:

```bash
uv --version
```

Once `uv` has been installed, use it to create a virtual environment for
LiveCodeBench and install its dependencies with the following commands:

```bash
uv venv --python 3.11
source .venv/bin/activate

uv pip install -e .
```

## Data

We provide a benchmark for different code capability scenarios

- [Code Generation](https://huggingface.co/datasets/livecodebench/code_generation_lite)
- [Code Execution](https://huggingface.co/datasets/livecodebench/execution)
- [Test Output Prediction](https://huggingface.co/datasets/livecodebench/test_generation)

## Inference and Evaluation

### Dataset Versions

Since LiveCodeBench is a continuously updated benchmark, we provide different versions of the dataset. Particularly, we provide the following versions of the dataset:

- `release_v1`: The initial release of the dataset with problems released between May 2023 and Mar 2024 containing 400 problems.
- `release_v2`: The updated release of the dataset with problems released between May 2023 and May 2024 containing 511 problems.
- `release_v3`: The updated release of the dataset with problems released bet

*… (9,622 more characters — see results.json for full text)*

---

### 11. SWE-bench Leaderboards
**URL:** https://www.swebench.com/
**Published:** 2024-10-06T17:48:08.000Z

SWE-bench Leaderboards

Verified Multilingual Lite Full Multimodal

Compare results

Agent:

mini-SWE-agent v2 mini-SWE-agent v0-v2 All OSS agents All agents

Models:

All models Open source only Proprietary only

Filters:

Open Scaffold ▼

All Tags ▼

Show results from older agent versions

SWE-bench Verified is a human-filtered subset of 500 instances; use the Agent dropdown to compare LMs with mini-SWE-agent or view all agents [Post]. SWE-bench Multilingual features 300 tasks across 9 programming languages [Post]. SWE-bench Lite is a subset curated for less costly evaluation [Post]. SWE-bench Multimodal features issues with visual elements [Post].

Each entry reports the % Resolved metric, the percentage of instances solved (out of 2294 Full, 500 Verified, 300 Lite & Multilingual, 517 Multimodal).

Analyze Results in Detail

## News

- [11/2025] Introducing CodeClash, our new eval of LMs as goal (not task) oriented developers! [Link]
- [07/2025] mini-SWE-agent scores 65% on SWE-bench Verified in 100 lines of python code. [Link]
- [05/2025] SWE-smith is out! Train your own models for software engineering agents. [Link]
- [03/2025] SWE-agent 1.0 is the open source SOTA on SWE-bench Lite! [Link]
- [10/2024] Introducing SWE-bench Multimodal! [Link]
- [08/2024] SWE-bench x OpenAI = SWE-bench Verified [Report]
- [06/2024] Docker-ized SWE-bench for easier evaluation [Report]
- [03/2024] Check out SWE-agent (12.47% on SWE-bench) [Link]
- [03/2024] Released SWE-bench Lite [Report]

## Acknowledgements

We thank the following institutions for their generous support: Open Philanthropy, AWS, Modal, Andreessen Horowitz, OpenAI, and Anthropic.

---

### 12. SWE-Bench Pro Leaderboard (2026): Why 46% Beats 81%
**URL:** https://www.morphllm.com/swe-bench-pro
**Published:** 2026-03-01T13:44:10.000Z

SWE-Bench Pro Leaderboard (2026): Why 46% Beats 81%

# SWE-Bench Pro Leaderboard (2026): Why 46% Beats 81%

Live SWE-Bench Pro rankings with SEAL scores, agent systems, and Verified. The best model scores 46% on Pro but 81% on Verified, because Verified is contaminated. Full leaderboard and analysis.

March 1, 2026 · 2 min read

Claude Opus 4.5 scores 80.9% on SWE-Bench Verified and 45.9% on SWE-Bench Pro. Same model, half the score. The difference: Verified's 500 Python-only tasks are contaminated. Pro's 1,865 multi-language tasks are not.

Below are the latest rankings from Scale AI's SEAL leaderboard (standardized scaffolding), agent systems with custom scaffolding, and SWE-Bench Verified. The SEAL leaderboard is the controlled comparison. Agent system scores show what happens when scaffolding is optimized.

Leaderboard data verified March 1, 2026

#### SWE-Bench Pro: SEAL Leaderboard (Top 10)

Standardized scaffolding, 250-turn limit, 731 public tasks

1Opus 4.5

45.9%

2Sonnet 4.5

43.6%

3Gemini 3 Pro

43.3%

4Sonnet 4

42.7%

5GPT-5 (High)

41.8%

6GPT-5.2 Codex

41%

7Haiku 4.5

39.5%

8Qwen3 480B

38.7%

9MiniMax 2.1

36.8%

10Gemini 3 Flash

34.6%

Source: Scale AI SEAL Leaderboard. All models uncapped cost, 250-turn limit.

1,865

Tasks across 41 repositories

20+

Models ranked

4

Languages (Py, Go, TS, JS)

~59%

Top agent score (public set)

SEAL Leaderboard (Scale AI) → SWE-bench Official → OpenAI on Retiring Verified →

## SEAL Leaderboard: SWE-Bench Pro (Standardized Scaffolding)

Scale AI runs every model through identical tooling with a 250-turn limit. This isolates raw model capability from scaffolding quality. SEAL stands for Scale's Evaluation and Assessment Lab. Scores below are from the public set (731 tasks).

The top 6 models are separated by 4.9 percentage points. Confidence intervals overlap for most adjacent pairs, meaning ranks 2 through 6 are statistically close. The gap widens below rank 10, where models drop below 30%.

| Rank | Model | Score | CI |
| --- | --- | --- | --- |
| 1 | Claude Opus 4.5 | 45.9% | ±3.60 |
| 2 | Claude Sonnet 4.5 | 43.6% | ±3.60 |
| 3 | Gemini 3 Pro | 43.3% | ±3.60 |
| 4 | Claude Sonnet 4 | 42.7% | ±3.59 |
| 5 | GPT-5 (High) | 41.8% | ±3.49 |
| 6 | GPT-5.2 Codex | 41.0% | ±3.57 |
| 7 | Claude Haiku 4.5 | 39.5% | ±3.55 |
| 8 | Qwen3 Coder 480B | 38.7% | ±3.55 |
| 9 | MiniMax 2.1 | 36.8% | ±3.55 |
| 10 | Gemini 3 Flash | 34.6% | ±3.55 |
| 11 | GPT-5.2 | 29.9% | ±2.15 |
| 12 | Kimi K2 Instruct | 27.7% | ±3.25 |
| 13 | Qwen3 235B | 21.4% | ±2.25 |
| 14 | GPT-OSS 120B | 16.2% | ±2.67 |
| 15 | DeepSeek V3p2 | 15.6% | ±2.63 |
| 16 | Gemma 3 27B | 11.4% | ±2.15 |
| 17 | Llama 3.1 405B | 11.2% | ±2.15 |
| 18 | GLM-4.6 | 9.7% | ±2.15 |
| 19 | Llama 4 Maverick 17B | 5.2% | ±1.24 |
| 20 | Codestral (2405) | 1.5% | ±1.51 |

Source: Scale AI SEAL Leaderboard. All models use uncapped cost with 250-turn limit unless noted. CI = 95% confidence interval.

## Agent Systems Leaderboard (Custom Scaffolding)

*… (11,428 more characters — see results.json for full text)*

---

### 13. SWE-bench Lite Leaderboard 2026 - Compare AI Model Scores
**URL:** https://pricepertoken.com/leaderboards/benchmark/swe-bench-lite

SWE-bench Lite Leaderboard 2026 - Compare AI Model Scores

Join the conversation on AI models, pricing, and tools. Price Per Token Community

# SWE-bench Lite Leaderboard

Software Engineering benchmark testing ability to resolve real GitHub issues.

As of May 3, 2026, the top-scoring model on SWE-bench Lite is Claude Opus 4.6 at 62.7%, followed by Claude Opus 4.6 at 62.7% and MiniMax M2.5 at 56.3%. 62 models have been evaluated on this benchmark.

Last updated: May 3, 2026

Models

62

Best Score

62.7

Average

26.8

Std Dev

19.9

Categories

Multi-turn

Columns

Provider

Model

Input $/M

Output $/M

SWE-bench Lite

Actions

Claude Opus 4.6 Thinking

$5.000

$25.000

62.7

$5.000

$25.000

62.7

$0.150

$1.150

56.3

$0.625

$5.000

54.3

$0.625

$5.000

54.3

$0.625

$5.000

54.3

$0.625

$5.000

54.3

Claude Haiku 4.5 Thinking

$1.000

$5.000

54.3

$1.000

$5.000

54.3

$0.600

$2.080

53.3

$0.600

$2.080

53.3

Claude Opus 4.5 Thinking

$5.000

$25.000

49.3

$5.000

$25.000

49.3

Qwen3 Coder 480B A35B (exacto)

$0.220

$0.900

44.7

$0.550

$2.200

42.0

$0.550

$2.200

42.0

$0.390

$1.740

42.0

$0.390

$1.740

42.0

$1.000

$10.000

40.0

$0.255

$1.000

39.0

$0.250

$2.000

38.3

$0.250

$2.000

38.3

$0.400

$2.000

36.5

Qwen3 235B A22B Instruct 2507

$0.071

$0.100

36.3

$0.625

$5.000

36.3

$0.625

$5.000

36.3

Mistral Large 3 2512

$0.500

$1.500

33.3

$0.014

$0.028

29.1

$0.800

$4.000

27.7

Gemini 2.5 Flash Thinking

$0.300

$2.500

26.1

Gemini 2.5 Flash Thinking

$0.300

$2.500

26.1

$0.300

$2.500

26.1

$0.300

$2.500

26.1

$0.300

$0.900

26.0

$0.300

$0.900

26.0

$0.390

$0.900

20.0

$0.390

$0.900

20.0

$0.080

$0.240

16.3

$0.080

$0.240

16.3

$0.150

$0.750

14.3

$0.150

$0.750

14.3

Gemini 3 Flash Preview Thinking

$0.500

$3.000

12.7

Gemini 3 Flash Preview

$0.500

$3.000

12.7

$0.039

$0.100

9.0

$0.039

$0.100

9.0

$0.150

$0.600

8.0

$3.000

$15.000

7.7

$0.600

$2.200

7.7

Grok 4 Fast Thinking

$0.200

$0.500

7.0

Mistral Small 3.2 24B

$0.075

$0.200

5.7

$0.080

$0.300

4.0

$0.800

$3.200

2.7

Grok 4.1 Fast Thinking

$0.200

$0.500

0.7

$0.200

$0.500

0.7

$0.065

$0.140

-

$0.400

$1.760

-

$0.400

$1.760

-

DeepSeek V3.2 Exp Thinking

$0.270

$0.410

-

$0.270

$0.410

-

$0.440

$2.000

-

$0.440

$2.000

-

$0.260

$1.560

-

Pricing from OpenRouter. Benchmarks from Artificial Analysis.

Get our weekly newsletter on pricing changes, new releases, and tools.

Subscribe

Join the Price Per Token Community

8 Ways to Use Fewer Tokens

Download Now

## About SWE-bench Lite

Software Engineering benchmark testing ability to resolve real GitHub issues.

This leaderboard shows all models with SWE-bench Lite benchmark scores, ranked from highest to lowest. Pricing data is included to help you compare performance against cost.

## Frequently Asked Questions

What is the SWE-bench Lite benchmark?

Software Engineering benchmark testing ability to resolve real GitHub issues.

Whi

*… (1,016 more characters — see results.json for full text)*

---

### 14. Aider LLM Leaderboards | aider
**URL:** https://aider.chat/docs/leaderboards/

Aider LLM Leaderboards | aider

# Aider LLM Leaderboards

Aider excels with LLMs skilled at writing and editing code, and uses benchmarks to evaluate an LLM’s ability to follow instructions and edit code successfully without human intervention. Aider’s polyglot benchmark tests LLMs on 225 challenging Exercism coding exercises across C++, Go, Java, JavaScript, Python, and Rust.

## Aider polyglot coding leaderboard

View Select Detail

×

- Dirname : 2025-08-23-15-47-21--gpt-5-high
- Test cases : 225
- Model : gpt-5 (high)
- Edit format : diff
- Commit hash : 32faf82
- Reasoning effort : high
- Pass rate 1 : 52.0
- Pass rate 2 : 88.0
- Pass num 1 : 117
- Pass num 2 : 198
- Percent cases well formed : 91.6
- Error outputs : 23
- Num malformed responses : 22
- Num with malformed responses : 19
- User asks : 96
- Lazy comments : 3
- Syntax errors : 0
- Indentation errors : 0
- Exhausted context windows : 0
- Prompt tokens : 2675561
- Completion tokens : 2623429
- Test timeouts : 3
- Total tests : 225
- Command :`aider --model openai/gpt-5`
- Date : 2025-08-23
- Versions : 0.86.2.dev
- Seconds per case : 194.0
- Total cost : 29.0829

- Dirname : 2025-08-25-13-23-27--gpt-5-medium
- Test cases : 225
- Model : gpt-5 (medium)
- Edit format : diff
- Commit hash : 32faf82
- Reasoning effort : medium
- Pass rate 1 : 49.8
- Pass rate 2 : 86.7
- Pass num 1 : 112
- Pass num 2 : 195
- Percent cases well formed : 88.4
- Error outputs : 40
- Num malformed responses : 40
- Num with malformed responses : 26
- User asks : 102
- Lazy comments : 0
- Syntax errors : 0
- Indentation errors : 0
- Exhausted context windows : 0
- Prompt tokens : 2827261
- Completion tokens : 1468799
- Test timeouts : 0
- Total tests : 225
- Command :`aider --model openai/gpt-5`
- Date : 2025-08-25
- Versions : 0.86.2.dev
- Seconds per case : 118.7
- Total cost : 17.693

- Dirname : 2025-06-28-00-38-18--o3-pro-high
- Test cases : 225
- Model : o3-pro (high)
- Edit format : diff
- Commit hash : 5318380
- Reasoning effort : high
- Pass rate 1 : 43.6
- Pass rate 2 : 84.9
- Pass num 1 : 98
- Pass num 2 : 191
- Percent cases well formed : 97.8
- Error outputs : 20
- Num malformed responses : 8
- Num with malformed responses : 5
- User asks : 100
- Lazy comments : 0
- Syntax errors : 0
- Indentation errors : 0
- Exhausted context windows : 0
- Prompt tokens : 2372636
- Completion tokens : 1235902
- Test timeouts : 1
- Total tests : 225
- Command :`aider --model o3-pro`
- Date : 2025-06-28
- Versions : 0.85.1.dev
- Seconds per case : 449.0
- Total cost : 146.3249

- Dirname : 2025-06-06-16-36-21--gemini0605-32k-think-diff-fenced
- Test cases : 225
- Model : gemini-2.5-pro-preview-06-05 (32k think)
- Edit format : diff-fenced
- Commit hash : f827f22
- Thinking tokens : 32768
- Pass rate 1 : 46.2
- Pass rate 2 : 83.1
- Pass num 1 : 104
- Pass num 2 : 187
- Percent cases well formed : 99.6
- Error outputs : 1
- Num malformed responses : 1
- Num with malformed responses : 1
- User asks : 112
- Lazy com

*… (22,000 more characters — see results.json for full text)*

---

### 15. Aider-AI/refactor-benchmark
**URL:** https://github.com/Aider-AI/refactor-benchmark
**Published:** 2023-12-17T21:18:22.000Z

# Repository: Aider-AI/refactor-benchmark

Aider's refactoring benchmark exercises based on popular python repos

- Stars: 81
- Forks: 8
- Watchers: 81
- Open issues: 4
- Primary language: Python
- Languages: Python
- License: Apache License 2.0 (Apache-2.0)
- Default branch: main
- Created: 2023-12-17T21:18:22Z
- Last push: 2024-10-10T22:01:53Z
- Contributors: 1 (top: paul-gauthier)

---

## Aider's refactoring benchmark

This repository holds exercises for a coding benchmark used by the
[aider](https://github.com/paul-gauthier/aider)
AI coding tool.
This benchmark was designed to provoke "lazy coding" in the GPT-4 Turbo models,
which have this widely reported problem.

This benchmarked assisted in the design and evaluation of a solution to the
lazy coding problem.
[Asking GPT-4 Turbo to format code changes as unified diffs](https://aider.chat/docs/unified-diffs.html)
reduced lazy coding
by 3X.

## Benchmark details

Aider has long used a
[benchmark suite based on 133 Exercism python exercises]().
But these are mostly small coding problems,
usually requiring only a few dozen lines of code.
GPT-4 Turbo is typically only lazy on 2-3 of these exercises:
the ones with the most code and which involve refactoring.

Based on this observation, I set out to build a benchmark based on refactoring
a non-trivial amount of code found in fairly large files.
To do this, I used python's `ast` module to analyze
[9 popular open source python repositories](https://github.com/paul-gauthier/refactor-benchmark)
to identify challenging refactoring tasks.
The goal was to find:

- Source files that contain classes with non-trivial methods, having 100-250+ AST nodes in their implementation.
- Focus on methods that are part of a larger class, which has at least twice as much code as the method itself.
- Select methods that don't use their `self` parameter, so they can be trivially refactored out of the class.

We can then turn each of these source files into a task for the benchmark,
where we ask GPT to do something like:

> Refactor the `_set_csrf_cookie` method in the `CsrfViewMiddleware` class to be a stand alone, top level function.
> Name the new function `_set_csrf_cookie`, exactly the same name as the existing method.
> Update any existing `self._set_csrf_cookie` calls to work with the new `_set_csrf_cookie` function.

A [simple python AST scanning script](https://github.com/paul-gauthier/aider/blob/main/benchmark/refactor_tools.py)
found 89 suitable files
and packaged them up as benchmark tasks.
Each task has a test
that checks if the refactor
was performed roughly correctly:

- The updated source file must parse as valid python, to detect misapplied edits which produce invalid code.
- The target method must now exist as a top-level function in the file.
- This new top-level function must contain approximately the same number of AST nodes as the original class method. This ensures that GPT didn't elide code and replace it with comments.
- The original class must s

*… (1,189 more characters — see results.json for full text)*

---
