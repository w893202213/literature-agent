| 论文                                                         | Method | Results | 核查结论                                                     |
| ------------------------------------------------------------ | ------ | ------- | ------------------------------------------------------------ |
| [2504.10479 InternVL3](https://arxiv.org/abs/2504.10479)     | ✅      | ⚠️       | MMMU 72.2 正确；预测中的 MathVista 79.6 不准确，应为 79.0，使用 VisualPRM Best-of-8 后为 80.5。 |
| [2501.12948 DeepSeek-R1](https://arxiv.org/abs/2501.12948)   | ✅      | ✅       | R1-Zero 通过纯 RL 学习推理；AIME 2024 从 15.6% 提升到 77.9%，多数投票为 86.7%。但 gold 应区分纯 RL 的 R1-Zero 与包含冷启动、多阶段训练的最终 R1。 |
| [2501.14723 CodeMonkeys](https://arxiv.org/abs/2501.14723)   | ✅      | ✅       | 串行/并行扩展测试时计算的描述准确；SWE-bench Verified 为 57.4%，成本约 2300 美元，集成选择为 66.2%。 |
| [2602.00653 NOVA](https://arxiv.org/abs/2602.00653)          | ✅      | ✅       | 非对比式 embedding 预测和 SIGReg 描述准确；平均 AUC 76.25，比匹配条件下 MedCLIP 高 3.8 点。 |
| [2603.01096 V-SONAR/V-LCM](https://arxiv.org/abs/2603.01096) | ✅      | ✅       | 后处理概念空间对齐准确；PE-Video R@1 为 73.03，视频描述 BLEU 数值也与 gold 一致。 |
| [2503.11794 SEMCLIP](https://arxiv.org/abs/2503.11794)       | ✅      | ✅       | 文本语义引导视觉区域选择且无需重训；七个基准平均提升 3.3%，V* 提升 5.3%。 |
| [2507.07104 VLV Auto-Encoder](https://arxiv.org/abs/2507.07104) | ✅      | ✅       | 冻结扩散解码器形成语言表示瓶颈并蒸馏语义的描述正确；训练成本低于 1000 美元，描述能力可比 GPT-4o/Gemini 2.0 Flash。 |
| [2506.18985 GLIMPSE](https://arxiv.org/abs/2506.18985)       | ✅      | ✅       | 三类归因组件描述正确；相对基线 rank correlation 提升 46.2%，NSS 提升 71.5%。gold 正确但过于笼统，建议补入数字。 |
| [2504.07615 VLM-R1](https://arxiv.org/abs/2504.07615)        | ✅      | ✅       | R1 风格规则奖励和 GRPO 描述正确；LISA-Grounding 为 63.16，对比 SFT 的 54.82；COCO AP 为 21.1，对比 17.8。 |
| [2504.21226 MemeBLIP2](https://arxiv.org/abs/2504.21226)     | ✅      | ✅       | BLIP-2 图文融合方法正确；PrideMM 上 accuracy 77.5%、AUROC 81.8%、macro-F1 79.0%。gold 正确但建议补入这些数字。 |