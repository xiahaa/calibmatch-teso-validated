# 弱标定双目、在线校正与标定感知匹配：系列探索技术报告

**报告日期：** 2026-08-18  
**实验周期：** 2026-08-03 至 2026-08-18  
**主要计算平台：** NVIDIA L20 46 GB；早期实验另使用 RTX 4090 服务器  
**报告性质：** 内部技术报告；记录已验证结果、失败路线、审计修正和后续研究边界  
**当前项目状态：** 暂停。仅保留经验证的 CalibMatch 子结果及必要复现资产。

## 摘要

本报告总结一系列围绕弱标定双目深度、在线 stereo rectification、essential matrix tracking、视频自标定和标定感知对应关系优化的研究尝试。最初目标是在只知道内参、机械 baseline 和存在旋转漂移的 tooling pose 时，从未校正双目图像直接恢复 metric depth。随着实验推进，研究依次考察了 raw-image metric plane sweep、粗到细深度与姿态联合估计、特征域校正、姿态后验边缘化、基于 TESO 的 5-DoF 时序跟踪、VGGT 虚拟标定场、稠密 direct calibration、通用 point tracking、LightGlue 亚像素 refinement，以及面向 stereo 加速的预算化 refinement。

这些路线没有收敛为一篇达到 ICRA/RA-L 强贡献要求的完整论文，但形成了若干可靠结论。首先，tooling rotation drift 对深度的影响是真实且显著的；在准确姿态下，feature/image rectification 与冻结 stereo matcher 可以获得良好深度，因此主要瓶颈不是 stereo head，而是从单帧或短视频视觉证据中稳定估计 calibration state。其次，下采样只缩小像素单位的纵向偏差，并不等价于 rectification，也不能消除深度与旋转之间的歧义。第三，通用 correspondence 的数量或通用 EPE 并不直接决定 online calibration 的闭环表现：LightGlue 相比 SIFT 对官方 TESO 有稳定正收益，而 CoTracker 传播、GMFlow 稠密对应和若干 task-aware loss 反而恶化结果。第四，唯一经过 20 条正式 validation sequence 验证的正结果，是在冻结 LightGlue proposals 上进行局部亚像素 refinement，再送入 rotation-only tracker：rotation error 从 0.041270° 降至 0.023424°，vertical p95 从 0.223356 px 降至 0.163189 px。然而，该模块与 Patch2Pix 类 detect-to-refine 工作过近，task-specific influence/D-optimal 增益又不足，尚不能形成足够强的新颖性。

本报告不把失败 gate、overfit smoke test、重复使用的 debug 数据或早期存在实现错误的结果包装成正式结论。所有数值按证据强度标记，并明确哪些结果已被后续审计推翻。

## 1. 问题定义与概念边界

### 1.1 三个容易混淆、但并不等价的目标

本系列工作先后涉及三个目标：

1. **Online rectification：** 寻找左右图像变换，使对应点的纵向坐标尽可能一致，从而把二维搜索简化为近似一维搜索。它只要求产生适合 stereo matching 的校正几何，不一定恢复物理上准确的相对外参。
2. **Essential matrix / extrinsic tracking：** 在已知内参时估计 $E=[\hat t]_{\times}R$，从而恢复相对旋转 $R$ 和 translation direction $\hat t$。essential matrix 本身不包含 translation magnitude。
3. **Metric stereo depth：** 对校正后的 disparity $d$，使用
   \[
   Z=\frac{f_x b}{d}
   \]
   恢复有尺度深度。这里必须知道 baseline magnitude $b$。

因此，FLoSR 或 RSCE 即使只优化 rectification，也仍有实际意义：它们可以恢复一维匹配条件、有效视场和 stereo matcher 的可用性；当 rig 的 baseline 来自机械设计或离线标定时，仍可输出 metric depth。但如果 baseline magnitude 未知，仅靠 online rectification 或 essential matrix decomposition 不能恢复 metric scale。

### 1.2 本项目逐步收敛后的合理问题

早期问题“无需准确标定，直接从 raw stereo 恢复 metric depth”过宽。实验后更合理的研究边界是：

- 已知准确内参、畸变和 baseline magnitude；
- 有配置级 nominal/tooling extrinsics；
- 主要不确定性是小范围、慢变化的相对 rotation，translation direction 仅在可观测时更新；
- online rectification 与 physical extrinsic tracking 应分别评价，不能用 vertical residual 代替全部 5-DoF 精度；
- stereo/depth 网络不是必须重新训练的对象，前端 correspondence 与标定估计器之间的接口更关键。

## 2. Related Work

### 2.1 Online stereo rectification 与在线外参估计

[FLoSR](https://openaccess.thecvf.com/content/CVPR2024/html/Kumar_Flow-Guided_Online_Stereo_Rectification_for_Wide_Baseline_Stereo_CVPR_2024_paper.html) 使用 flow-guided correlation 和跨图注意力预测相对旋转，并以纵向 optical flow 作为 rectification 质量代理。它主要解决单帧宽基线 stereo 的在线校正，不以恢复完整物理外参为唯一目标。

[RSCE](https://openaccess.thecvf.com/content/CVPR2025/html/Gong_Rectification-specific_Supervision_and_Constrained_Estimator_for_Online_Stereo_Rectification_CVPR_2025_paper.html) 将半稠密匹配与受约束的 rectification estimator 结合，并引入 rectification-specific supervision。它进一步说明，面向“行对齐”的监督可以不同于通用 correspondence 或通用 pose 监督。

[StereoCalibrator / Dive Deeper into Rectifying Homography](https://arxiv.org/abs/2309.10314) 从 rectifying homography 的参数化出发，通过纵向残差估计左右校正旋转，并提供多帧全局估计。该路线强调：达到好的 rectification 与直接最小化传统 essential residual 并不完全等价。

[TESO](https://openaccess.thecvf.com/content/CVPR2026/html/Moravec_TESO_Online_Tracking_of_Essential_Matrix_by_Stochastic_Optimization_CVPR_2026_paper.html) 则是另一类问题。它对 tentative correspondences 建立 kernelized epipolar objective，在 essential manifold 上做自适应随机优化，直接追踪 5-DoF essential state。TESO 不需要训练，计算量低，并可从 $E$ 分解得到 $R$ 与 $\hat t$，但仍不能恢复 baseline magnitude。

本项目的重要区分是：FLoSR/RSCE 更偏向“得到可用的 rectification”，TESO 更偏向“追踪物理 essential state”。二者可以共享 correspondence frontend，但不能仅凭 vertical residual 改善就声称完整 5-DoF 恢复更准确。

### 2.2 Raw/posed stereo、光流与 stereo backbone

[UniMatch](https://arxiv.org/abs/2211.05783) 已经展示了统一的 optical flow、rectified stereo 和在准确 pose 下的 unrectified stereo depth。这意味着“准确相机 pose 下从未校正图像估计深度”本身不构成新问题；本项目真正困难的部分是 pose drift。

[GMFlow](https://openaccess.thecvf.com/content/CVPR2022/html/Xu_GMFlow_Learning_Optical_Flow_via_Global_Matching_CVPR_2022_paper.html) 以全局特征匹配预测 dense 2D flow，适合作为 raw correspondence frontend，但其像素误差具有空间相关性，未必适合直接累积成 calibration objective。

[RAFT-Stereo](https://arxiv.org/abs/2109.07547) 使用多级 correlation pyramid 和 recurrent update operator 估计 disparity。本项目把它作为固定 stereo backend，以区分“姿态/校正是否正确”和“深度网络是否足够强”。

### 2.3 低分辨率 stereo、深度 refinement 与上采样

[StereoNet](https://openaccess.thecvf.com/content_ECCV_2018/html/Sameh_Khamis_StereoNet_Guided_Hierarchical_ECCV_2018_paper.html) 在低分辨率构建 cost volume，再通过图像引导的层级 refinement 恢复高分辨率 disparity。[HITNet](https://openaccess.thecvf.com/content/CVPR2021/html/Tankovich_HITNet_Hierarchical_Iterative_Tile_Refinement_Network_for_Real-time_Stereo_Matching_CVPR_2021_paper.html) 使用多分辨率 tile hypothesis、warping 和迭代 refinement，证明 stereo 加速可以不依赖完整 3D cost volume。

Poggi/Tosi 系列的 [Neural Disparity Refinement（NDR）](https://arxiv.org/abs/2110.15367) 把已有 disparity 与参考图像作为输入，通过连续查询在任意分辨率输出 refined disparity，尤其适合不平衡分辨率 stereo 和跨域 refinement。但 NDR 的输入 disparity 已经处于 rectified stereo 几何中；它不能单独修复错误外参造成的二维对应偏移。

[JAFAR](https://papers.nips.cc/paper_files/paper/2025/hash/8eed150084dc3534f01ba63f9b7d32d2-Abstract-Conference.html) 是面向 foundation vision encoder 的通用 feature upsampler，通过高分辨率 query、低分辨率语义 key 和 SFT 调制恢复细节。它不是 stereo matcher、disparity refiner 或 rectification 模块。将它用于 stereo 需要额外证明跨视图 matching 信息在上采样过程中被保留；本项目没有完成这一独立验证，因此不能下结论说 JAFAR 对 depth 无效。

### 2.4 稀疏、半稠密匹配与亚像素 refinement

[LightGlue](https://openaccess.thecvf.com/content/ICCV2023/html/Lindenberger_LightGlue_Local_Feature_Matching_at_Light_Speed_ICCV_2023_paper.html) 是自适应深度的 sparse feature matcher，在本项目中成为最可靠的 learned frontend。[EfficientLoFTR](https://openaccess.thecvf.com/content/CVPR2024/html/Wang_Efficient_LoFTR_Semi-Dense_Local_Feature_Matching_with_Sparse-Like_Speed_CVPR_2024_paper.html) 以聚合注意力和两阶段 correlation 提供高效半稠密、亚像素对应，是 CalibMatch 的强基线。

[Patch2Pix](https://openaccess.thecvf.com/content/CVPR2021/papers/Zhou_Patch2Pix_Epipolar-Guided_Pixel-Level_Correspondences_CVPR_2021_paper.pdf) 已经提出 detect-to-refine 范式：从 patch-level proposals 回归 pixel-level matches 并预测置信度。这构成 CalibMatch 新颖性的主要压力：如果贡献只剩“冻结 matcher 后加局部亚像素 refiner”，即使闭环性能显著，也难以作为强方法论文成立。

### 2.5 视频 point tracking 与多视图 foundation model

[CoTracker3](https://arxiv.org/abs/2410.11831) 可对视频中的任意点进行联合跟踪，但其目标是单流视频中的时间一致性，并未针对每帧左右相机间的 stereo correspondence 重建进行训练。本项目验证了，简单把左右流独立传播再拼成 stereo matches 会积累相关偏差。

[VGGT](https://openaccess.thecvf.com/content/CVPR2025/papers/Wang_VGGT_Visual_Geometry_Grounded_Transformer_CVPR_2025_paper.pdf) 可从一帧或多帧图像一次性预测 cameras、depth、point maps 和 tracks。它为“用左目视频构建虚拟标定场，再用右图重投影优化 stereo rig”提供了合理先验，但通用 3D reconstruction 精度与亚十分之一度的 stereo calibration 精度不是同一要求。

## 3. 实验方法与证据等级

### 3.1 证据等级

本报告使用以下标签：

- **已验证（VALIDATED）：** 代码/数据协议固定，跨 sequence 统计，机器可读 artifact 可回算；没有已知会改变结论的实现错误。
- **探索性（EXPLORATORY）：** 使用 debug/reused 数据或样本量较小，可用于因果定位，不作为论文正式结果。
- **Gate 失败（FAILED GATE）：** 按预注册门槛停止，后续模块未运行。
- **未运行（NOT RUN）：** 只有设计、代码骨架或 manifest，不能作为实验结论。
- **已推翻/被审计替代（SUPERSEDED）：** 早期实现或报告存在公平性、数据、代码或统计问题，后续结果取代它。

### 3.2 共同评价指标

深度使用 AbsRel、RMSE、$\delta_1$；correspondence 使用 2D EPE、vertical EPE/p95 和 bad-pixel；标定使用 rotation geodesic error 与 translation-direction angular error。统计单位尽量为 sequence，并使用 paired sequence bootstrap，而不是把相邻帧当作独立样本扩大显著性。

### 3.3 关键完整性原则

- tooling prior 不能在每帧被当作独立观测重复相乘。
- true pose 只能作为 oracle，不进入公平排名。
- 预测越界或 warp invalid 像素不得通过选择性删除美化结果。
- 运行过旧 gate 的 Scene Flow TEST 不再称为 untouched test。
- 未通过 gate 时不继续堆叠 refinement、JAFAR 或更大网络。
- 每条失败路线都要区分“具体实现/打分失败”和“整个方法家族不可能”。

## 4. 数据集与实际使用范围

| 数据集/协议 | 来源与内容 | 在本项目中的用途 | 实际状态与限制 |
|---|---|---|---|
| Scene Flow / FlyingThings3D | 大规模合成 stereo、disparity、flow；[CVPR 2016](https://openaccess.thecvf.com/content_cvpr_2016/html/Mayer_A_Large_Dataset_CVPR_2016_paper.html) | 物理旋转 homography 生成 raw stereo；TGRMS、GeoJAFAR、posterior gates | 官方 TEST 的 4370 帧/437 sequences 已被旧 Gate B′/C 使用，不能再称 untouched；后续从 TRAIN 做 sequence-disjoint debug/gate split |
| KITTI Stereo 2012/2015 | 真实车载 stereo；2012 为 194 train/195 test，2015 为 200 train/200 test；[官方 benchmark](https://www.cvlibs.net/datasets/kitti/eval_stereo.php) | legacy 深度结果、数据下载与 manifest、计划中的 Stage 3 | legacy 的部分 calibration/scale 设定不可信；新的完整 formal benchmark 未跑完 |
| ETH3D | 室内外高精度扫描和同步 stereo；[CVPR 2017](https://openaccess.thecvf.com/content_cvpr_2017/papers/Schops_A_Multi-View_Stereo_CVPR_2017_paper.pdf) | 建立 manifest，计划检验 metric scale 与跨域泛化 | 主要停留在准备阶段，不能声称有正式结果 |
| Middlebury | 高精度室内 stereo benchmark | legacy 稿件中的深度/scale 实验 | 早期“metric”设定含人为 calibration/scale alignment，相关 headline result 已被审计推翻 |
| CARLA debug / CARLA-Tooling | [CARLA](https://arxiv.org/abs/1711.03938) 物理重渲染的 stereo sequence、真实相机 pose、depth/correspondence | ToolE-Track、TESO 公平复现、CoTracker、DirectCalib、CalibMatch、VGGT | 多条路线共享早期 10 条 debug sequences；只能做探索。另生成 20 条 CalibMatch formal validation sequences 和 controls，但没有 sealed final test |
| CARLA-Drift | TESO 官方动态 essential tracking 数据 | 计划复现官方 TESO | 完整 155 sequence 复现未完成；不能声称 Gate T0 正式通过 |
| CARLA-Flowguided / Semi-Truck Highway | FLoSR/RSCE 的公开协议 | related-work/外部 comparator 计划 | 未形成同协议可审计的本地正式对比 |
| VGGT pilot windows | CARLA control 与 slow sequence 的 9 帧窗口 | 虚拟标定场 Stage A/B | Stage A 60 trials；Stage B 为 40 frozen windows；均是 reused debug 数据 |
| Budget-refinement split | 20 条已使用 CARLA sequences，共 200 frames；6/9/5 sequence 划分 | 预算化 dense stereo refinement | 仅 debug/calibration/eval，未进入 formal/test |
| 自有真实 rig | 计划的重复装配、自然场景和 ChArUco/棋盘格评估 | tooling covariance、zero-shot 真实验证 | 没有完成足够配置与可审计 GT；不报告真实 rig 结论 |

Scene Flow 的“depth”应按 Blender/dataset unit 报告；只有 KITTI、ETH3D 或已知物理 rig 才能支撑 metre-level metric claim。

## 5. 路线总览

| 路线 | 核心假设 | 最高执行阶段 | 结论 |
|---|---|---|---|
| Legacy CalibRefine | 用 GT depth 辅助 per-scene calibration，再输出 metric depth | 论文/代码审计 | **SUPERSEDED**：存在任务循环、代码—论文不一致和尺度设置问题 |
| TGRMS raw metric stereo | tooling prior + raw 2D matching 可端到端恢复 depth/rotation | Gate B/C | rotation drift 效应真实；adapter 收益远低于门槛 |
| ToolRect / GeoJAFAR | 粗尺度弱化纵向偏差，再逐层 stereo refinement | F0/F1 | F0 通过、F1 失败；stride-32 表示本身限制明显 |
| Latent feature rectification + RAFT | 学 rotation latent，在 feature 域校正后运行 RAFT | L0/overfit smoke | true-pose 闭环可行；learned pose 不泛化 |
| Tooling posterior stereo | 多姿态后验和 top-K depth 边缘化优于单点姿态 | P0/P1 | frozen GMFlow score 无法形成有信息的姿态后验；P1 失败 |
| ToolE-Track | tooling covariance + observability gate 改进 TESO 5-DoF tracking | T1 + 2-seq pilot | 几何实现可靠；translation direction 更新初步有害，正式 T2 未跑 |
| VGGT virtual target | 左视频 3D reconstruction 可作虚拟标定场 | Stage A/B | 优化器 oracle 通过；VGGT 几何精度未达到 calibration gate |
| E2E/direct TESO | 稠密特征 objective 或 point tracker 可替代 sparse matching | D0/D1/DG0 | GMFlow/直接特征目标/CoTracker 均负收益；具体朴素方案失败 |
| CalibMatch | 亚像素 refinement + calibration influence + D-opt selection | formal validation + strengthening | endpoint refinement 强；task-aware 部分不增益，新颖性不足 |
| Budget stereo refinement | 只精修高风险区域以加速 stereo | B0/B1 | oracle opportunity 存在；learned policy 不如简单 photometric heuristic |

## 6. 各路线实验与结果

### 6.1 Legacy：GT-depth 辅助的 per-scene CalibRefine

**路线。** 初始系统输入弱 calibration (K_0,R_0,b_0)，对每个 scene 优化可学习的 calibration 参数，执行 Bouguet rectification，再用冻结 RAFT/GMDepth/IGEV 估计 disparity，最后以 (Z=f b/d) 输出深度。

**审计发现。** 这一版本不是可部署的弱标定 metric stereo：优化阶段直接使用 GT metric depth，因而实质上是“给定 GT depth 的 calibration refinement”。所谓 CalibRefine 也是每个 scene 独立优化的 `nn.Parameter`，不是训练后可迁移的网络。论文声称的 held-out crop early stopping 与代码不一致，实际是 in-sample best-loss checkpointing。Middlebury 的 metric calibration 和 scale 设置存在人为构造/对齐，内参 refinement 在主结果中关闭，baseline 可沿 (f b) ridge 吸收 focal error。旧稿还存在未运行消融、缺失 supplement、逐轴采样却把上限写成总旋转角等问题。

**结论。** 旧稿的 headline numbers 不作为本报告的有效实验结果。这里的“fake-like”问题应准确表述为：结果和实现未必是恶意伪造，但存在不受任务定义支持的指标、错误的实验叙述和代码—论文不一致。该路线已被完全停止。

### 6.2 TGRMS：raw-image metric plane sweep

**路线。** 在准确 $K,b,\hat t$ 和有 rotation error 的 $R_{tool}$ 下，以 UniMatch/GMFlow 特征构建 raw-image plane sweep；geometry adapter 预测 rotation likelihood，与 tooling Gaussian prior 在 $SO(3)$ tangent space 融合；局部二维 refinement 更新 inverse depth 和 correspondence residual。

**数据与验证。** Scene Flow 右图通过 (H=K_RR_{raw}K_R^{-1}) 做物理纯旋转；角度以轴—角总范数分层采样。对应关系通过原 disparity 和 homography 生成，并完成 round-trip、crop/resize intrinsics 和 baseline invariance 单测。

**主要结果。** weak-pose 相对 true-pose oracle 在 2°、3°、5° 下分别约恶化 48%、65%、92%，说明研究问题具有足够效应量。但最佳早期 geometry adapter 在 2° 下只改善约 4.2%，远低于预注册的 25% 门槛。

**结论。** rotation drift 确实会破坏 metric stereo；但当前单点 Gaussian adapter 不能可靠解耦 rotation 与 depth。不能据此说 raw metric stereo 不可能，只能说这一表示和训练目标没有达到可行性门槛。

### 6.3 ToolRect / GeoJAFAR：粗尺度初始化与逐层 refinement

**路线。** 假设下采样后纵向 misalignment 在 feature pixels 中变小，可在 stride-32 的二维窄带内得到粗 inverse depth，再通过局部 GeoJAFAR 式跨尺度 latent upsampling 和右图 rematching 恢复到 stride-4/原分辨率。

**先验几何统计。** 在旧 40-frame validation 上，2°/3°/5° tooling error 的 vertical p95 在 stride-32 约为 1.12/1.67/2.77 feature px，在 stride-64 约为 0.56/0.84/1.39 px。因此 radius-4 的二维 band 在覆盖意义上合理，但这不等于图像已被 rectified。

**Gate F0。** 几何、baseline scaling、warp 和资源测试通过。

**Gate F1。** 失败：AbsRel 0.2786（要求 <0.05），2D EPE 49.92 px（要求 <1 px）；2° rotation residual 0.044° 和 shuffled-right degradation ratio 3.10 通过，但有 1 次 skipped optimizer update。诊断表明，去掉预测 local residual 后 EPE 为 16.13 px、vertical EPE 0.45 px；加入 local residual 后反而变成 49.92/20.30 px。使用 GT inverse depth + predicted rotation 时 EPE 为 0.90 px，GT depth + true rotation 为 0.23 px。

**表示上限。** continuous/64-candidate depth oracle AbsRel 随起始 stride 为：stride-32 0.1720/0.1748、stride-16 0.1070/0.1137、stride-8 0.0618/0.0726、stride-4 0.0328/0.0473。F1 要求的一部分已经超出 stride-32 表示所能达到的范围。

另一个 ToolRect probe 中，即使提供 true pose，stride-16 coarse head 的 AbsRel 仍约为 0.264，进一步把失败定位到 coarse inverse-depth representation/head，而不是 projection convention。

**结论。** 下采样只把 misalignment 变成较小的 feature-pixel offset，同时也压缩 disparity 与深度分辨率；它不能自动完成 rectification。失败主要来自粗 depth representation 和 residual factorization。GeoJAFAR 完整模块并未进入公平、受控的 efficacy test，因此不能写成“JAFAR 对深度上采样无效”。

### 6.4 Latent feature rectification + RAFT-Stereo

**路线。** 冻结 GMFlow 提供 raw 2D flow，pose head 预测内部 rotation latent；在 RAFT stride-4 feature 上按估计姿态 warp 右特征，再运行原生一维 correlation、ConvGRU 与 convex upsampling。

**关键对照。** true-pose feature/image rectification 后 RAFT 的 AbsRel 为 0.04890，而 weak-pose RAFT 为 0.27844。这是整个 raw-depth 系列最重要的归因结果之一：feature-domain warp 与 metric-depth closure 是可行的，正确姿态下 stereo backend 足够准确。

**失败点。** learned pose head 只在 overfit/smoke 数据上收敛，未在 sequence-disjoint 数据上泛化。允许 depth gradient 更新 pose head 还会加剧不稳定。

**结论。** 瓶颈是 calibration inference，而不是 feature warp 或 RAFT-Stereo。后续继续堆叠 JAFAR/NDR 无法修复错误 pose。

### 6.5 Tooling-Posterior Stereo：姿态边缘化

**路线。** 不把视觉证据压成单个 rotation mean/std，而是在 tooling 周围做三级 (SO(3)) 离散搜索，形成 top-3 pose posterior；每个姿态分别 feature-rectify 和 stereo，再对 baseline-normalized inverse depth 做像素级边缘化，并输出 risk/拒识。

**Gate P0。** 基于 GT correspondence 的几何检查接近但未完全通过：2° top-3 recall @0.25° 为 98%（门槛 99%），5° @0.5° 为 100%，identity 中心命中率 100%，baseline invariance 精确通过。

**Gate P1。** frozen GMFlow scoring 决定性失败：identity residual 为 0，但 2° MAP median residual 1.501°、top-3 recall @0.5° 为 0；5° residual 2.707°、top-3 recall @1° 为 0。shuffled-right entropy ratio 仅 1.002，failure trigger 为 0%。

**结论。** 当前 frozen-feature likelihood 几乎没有提供可辨识的 pose posterior；因此 P2 的 top-3 RAFT mixture、cross-view NDR 和 risk head 均未运行。该结果否定的是这一 posterior energy，不是否定“离散姿态边缘化”这一整个研究家族。

### 6.6 ToolE-Track：tooling covariance 与可观测性门控 TESO

**路线。** 在 $SO(3)\times S^2$ 上追踪 3-DoF rotation + 2-DoF translation direction。tooling covariance 只用于初始化、白化和 trust region；每帧计算完整 $5\times5$ Gauss–Newton information matrix，并在白化特征方向上冻结低信息更新。视觉目标结合 TESO-style epipolar loss 与 rectification vertical residual。

**Gate T1。** 几何实现通过 34 个测试：dense projection 最大误差 $3.052\times10^{-5}$ px；oracle sequential recovery 的 rotation error 0.000121°、translation-direction error 0.00521°；人工退化中 600/600 个弱 eigendirections 被冻结。开发中发现并修复了三个会改变结论的 bug：CARLA attached sensor transform 被错当 world pose、camera-Z depth 被错当 ray range、rotation blocks 未投影回 $SO(3)$。

**探索性两序列结果。** rotation-balanced 序列上，nominal/TESO/5-DoF/rotation-only 的 rotation error 分别为 0.2167/0.0413/0.0373/0.0343°，vertical residual 为 2.684/0.284/0.222/0.138 px。translation-heavy 序列上，rotation 为 0.0765/0.0522/0.0255/0.0301°，但 5-DoF translation-direction error 由 nominal 0.1628° 恶化到 0.2767°，TESO 也为 0.2145°；rotation-only 保持 0.1628°。

**结论。** 完整 Jacobian 和 observability gate 的工程实现是可靠的，但 translation direction 在现有视觉证据下容易被错误更新。正式 T2、paired CI 和三 matcher 泛化没有运行，不能声称 3-DoF 或 5-DoF 相对官方 TESO 已成立。SIFT pipeline 约 6.6 Hz，也低于 10 Hz 目标。

### 6.7 VGGT Virtual Calibration Target

**路线。** 用冻结 VGGT 对左目 9 帧窗口重建 depth/point map；使用已知左内参重新 unproject；再以右图 correspondence 和 tooling initialization 优化 rotation、translation direction 和 VGGT scene scale。

**Stage A：GT geometry oracle。** 60 个 control-window trials 全部通过：rotation median $2.49\times10^{-7}$°、p95 $4.22\times10^{-6}$°；translation-direction median $8.68\times10^{-5}$°；reprojection median $4.36\times10^{-5}$ px；5° rotation + 2° translation-direction 初始化成功率 100%。这验证了投影 convention、尺度变量和优化器收敛域。

**Stage B：VGGT geometry + GT correspondence。** 在修正后的 40 个 frozen windows 上，9-frame rotation median 0.209031°、p90 0.464968°，translation-direction median 0.538840°，2°+1° 初始化成功率 17.5%，均未达 Gate B。9 帧相对单帧 rotation 改善 27.394%，shuffled correspondence 使 reprojection 恶化 189.329 倍，说明模型确实使用了视频和 correspondence。`depth + known K` 是三种 3D 表示中最优；`depth + VGGT K` 与 point map 的 rotation error 约 2.3–2.6°。

**实现审计。** 曾发现 SciPy `least_squares` 的 robust loss 会原地修改返回 residual array，而 cache 又返回内部数组引用，导致诊断 cache 污染。修复为返回 copy 后，全部 Stage B 从冻结 VGGT cache 重跑；仅修正后数值有效。CARLA 实际 baseline 0.999942712 m 与 nominal 1 m 的差异导致 dense label precision 最大约 0.00955 px，但量级不足以解释 Stage B 失败。

**结论。** 视频 VGGT 比单帧更好，但通用 reconstruction geometry 未达到 stereo calibration 所需的亚 0.1° 精度。由于 Stage B 使用 GT correspondence 仍失败，真实 matcher Stage C 没有必要运行；本 gate 的瓶颈是 3D geometry，而非 matcher。

### 6.8 回到官方 TESO：公平复现、LightGlue 与 CoTracker

**公平性审计。** 早期“本地方法优于 TESO”的若干结论无效，因为比较的是本地 fixed-translation 3-DoF Gauss–Newton 与官方 5-DoF TESO，并同时存在 top-5 candidates 从约 9263 截断到 512、5-frame window、额外 0.25 step scale、灰度提取差异和 post-update translation projection 等问题。修复后的 wrapper 在 1000 帧上与官方数值列完全一致。

**SIFT 过滤。** 在 10 条 reused debug sequences 上，官方 TESO top-5 的 rotation/translation-direction/vertical 指标为 0.04591°/0.20082°/0.27160 px；SIFT ratio+mutual filtering 为 0.04182°/0.11135°/0.21328 px，对应改善 8.90%/44.55%/21.47%。exact-GT correspondence ceiling 为 0.01181°/0.08791°/0.09811 px，说明 frontend 仍有较大空间。

**LightGlue。** 在相同官方 cached interface 下，SIFT ratio baseline 为 0.038305°/0.108428°/0.199668 px，LightGlue 为 0.030763°/0.093013°/0.166251 px；rotation 改善 19.69%（9/10，CI 排除零），translation-direction 改善 14.22%（7/10，CI 包含零），vertical 改善 16.74%（9/10，CI 排除零）。LightGlue 的 <0.5 px inlier rate 只有 16.4%，score AUROC 为 0.705，却仍改善闭环，说明 calibration utility 不能由单一通用 EPE/score 完全刻画。

**CoTracker。** stride-4 的双流 point propagation 使 rotation 从 0.038305° 恶化到 0.047252°（-23.36%，0/10），translation-direction 恶化 4.00%，vertical 从 0.199668 恶化到 0.235270 px（-17.83%，0/10）；stride-8 更差。这个结果只否定“独立传播左右点并重新拼接 stereo pair”的朴素用法，不否定所有 calibration-aware temporal tracking。

### 6.9 DirectCalibTrack：从 feature-based 改为 dense/direct

**路线。** 借鉴 direct VO，尝试不做 hard matching，而是在候选 rotation 下沿 epipolar/depth 方向累积 dense feature likelihood，或把 GMFlow dense correspondence 直接送入 TESO。

**D0 几何上限。** exact-GT 512 点、tooling translation 下 local 3-DoF rotation error 0.002356°、vertical 0.03350 px；全像素 0.002790°/0.03252 px；oracle translation 下达到 $2.37\times10^{-7}$°/$1.37\times10^{-5}$ px。优化器和几何本身可达高精度。

**GMFlow dense correspondence。** 512/8192 点的 rotation error 为 0.15337°/0.15682°，增加点数没有改善，表明误差是相关的系统性偏差而非独立噪声。在两个 sequence 的官方 TESO 公平比较中，LightGlue 为 0.029917°/0.086187°/0.169379 px，GMFlow 为 0.071165°/0.197417°/0.455191 px，rotation 与 vertical 分别恶化 137.9% 和 168.7%。

**无 hard match 的 direct likelihood。** 目标要求 16 frames 中 80% 的所有轴误差小于 0.02°。forward stride-16 只有 6.25% 通过，worst-axis error 0.16625°；symmetric stride-16 仍为 6.25%/0.09688°；最好 stride-8 也只有 12.5%，median worst-axis 0.09125°、p90 0.195°。

**结论。** direct VO 的成功依赖明确的时空 photometric model 和局部线性化，而 stereo calibration 中对未知 depth 的边缘化产生大量 distractors；稠密 feature error 还高度相关。朴素“稀疏改稠密”并不会自动提高标定精度，D1/E2E 训练因此停止。

### 6.10 CalibMatch：亚像素 refinement、influence 与 D-optimal selection

**路线。** 冻结 SuperPoint+LightGlue proposals，对右端点做局部亚像素 refinement，同时预测 uncertainty/validity；再用 calibration influence scorer 和 tooling-covariance-whitened D-optimal selection 选点。项目早期使用官方 5-DoF TESO/cached interface 做 frontend oracle 与基线；translation-direction claim 未通过后，正式 20-sequence attribution 按预注册 fallback 改用固定 $\hat t=\hat t_{tool}$ 的 full-Hessian rotation-only tracker，其 Gaussian epipolar kernel 来自 TESO。下述 43.24% 正结果属于这个 rotation-only fallback，不能写成官方 5-DoF TESO 的正式增益。

**先导四 profile 结果。** raw LightGlue 的 rotation/vertical/EPE 为 0.027760°/0.177338 px/1.396858 px；通用 Pixel-NLL refiner 为 0.020379°/0.133114 px/0.566446 px；rectification-specific 为 0.021852°/0.134178 px/0.554754 px；one-step calibration loss 为 0.021279°/0.128725 px/0.565270 px；influence-v2 为 0.021724°/0.134461 px/0.554489 px。经典 LK 和 cornerSubPix 分别得到 0.030265°/0.149917 px/0.945111 px 与 0.032341°/0.185761 px/1.947952 px。

这些结果说明 learned local refinement 有真实价值，但当前 task-aware losses 没有系统优于通用 Pixel-NLL。one-step 相对 Pixel-NLL 的 rotation 反而恶化 4.41%，只在 vertical 上改善 3.30%；influence-v2 的 rotation/vertical 分别恶化 6.60%/1.01%。

**正式 validation 的已验证正结果。** 在 20 条 formal validation sequences 上，对三个 seed 的结果聚合：

| 方法 | Rotation error | Vertical p95 | 相对改善 |
|---|---:|---:|---:|
| Raw LightGlue endpoints | 0.041270° | 0.223356 px | - |
| Refined endpoints, all matches | 0.023424° | 0.163189 px | rotation 43.24%；vertical 26.94% |

两项均 20/20 sequence 获胜，paired sequence-bootstrap 95% CI 排除零。这是整个研究周期中证据最强的正结果。

**D-optimal selection。** corrected rotation D-opt 达到 0.021630°/0.155001 px，相对 confidence top-512 改善 11.07%/4.55%，CI 排除零；但相对 refined-all 只改善 rotation 7.66%，CI 包含零，且 coupled profile 恶化；相对 tiled-confidence 的 rotation 只改善 4.22%，CI 仍包含零。更复杂的 (D_s)-optimal 版本为 0.026142°，不优于 D-opt 0.026070°，且 selection cost 从约 0.011 s/frame 增至 0.086 s/frame。

**无 GT 推理审计。** 删除 GT 和 true rotation 输入后，100-frame outputs 可逐项复现，排除了部署时偷看标签的风险。

**下游 depth。** 固定 RAFT-Stereo 在 20 sequences × 10 frames 上，AbsRel 从 0.050489 降至 0.046047，改善 8.80%，18/20 sequence 获胜，bootstrap CI [0.002865, 0.006219]，但未达到预注册的 10% 门槛。

**贡献审计。** calibration-influence 相对相同容量的 EPE/BCE only 只改善 rotation 1.97%、vertical 1.13%，no-drift 反而恶化 11.51%。rotation-only 1k smoke 的 shuffled-right ratio 仅 1.04，AUROC 0.848，EPE 恶化 3.1%。TESO-aware strengthening 在 matched 2k 上也失败：相对 endpoint-only，one-step error 恶化 5.43%、closed-loop 恶化 2.62%、false-update 恶化 5.96%、EPE 恶化 12.23%；full-1024 更差。endpoint gradient 与 task gradient cosine 仅 0.010，25% 为负，45.25% task gradient 落在无 GT candidates 上。

**总 gate 状态。** 正式 aggregate 的 `status` 为 `FAIL`：完整 pipeline 为 9.87 Hz，略低于 10 Hz 门槛；5-DoF translation claim 未通过；下游 depth 改善也低于 10%。rotation-only endpoint-refinement 子结果仍有效，但不能据此宣称整个 Gate C3 通过。

**结论。** “局部 learned subpixel refinement 能显著改善在线 rotation tracking”是可信结果；“calibration influence supervision”和“tooling-whitened D-opt selection”尚未形成足够强、稳定的独立贡献。整体仍接近 Patch2Pix-style refiner + known optimizer，且没有 sealed test、真实 rig 和满足门槛的 downstream depth，因此不足以支撑当前 ICRA/RA-L 投稿。

### 6.11 Budget Stereo Refinement：只精修高风险区域

**路线。** 用廉价 half-resolution stereo 得到初值，只在选定像素/tiles 上运行较昂贵的 local refinement，以测试 JAFAR/upsampling 之外的 stereo 加速方向。

**Gate B0。** 10 个 used debug frames 上，half LightStereo EPE 3.1626，full-resolution 为 1.2479。radius-32 下，10%/25%/50% tile oracle 的 EPE 为 1.7446/1.0454/0.5880，dense refinement 为 0.2277。25% oracle 已闭合 half-to-full gap 的 110.6%，说明预算化 refinement 存在理论机会。

**Gate B1。** 20 sequences/200 frames 按 6 fit、9 calibration、5 eval 划分。三个 seed 的 learned 25% policy capture 为 56.47±0.48%，ceiling 48.45±0.41%，AUROC 0.8589，Spearman 0.5815，conformal coverage 94.74%。但 shuffled drop 只有 14.78%（要求 ≥20%），overhead 12.53%（要求 <10%）。更关键的是，oracle/photometric/learned/gradient/uniform/random capture 分别为 74.92/65.34/56.47/50.92/26.05/25.03%，learned policy 比简单 photometric heuristic 低 13.6%。

**结论。** proxy risk 能被学习，但其 AUROC/校准性不等于闭环 refinement utility。该方向的最强现有结果是简单 photometric selection，而不是学习模块；在概念拥挤的 selective computation 文献中不足以形成新贡献，B2 因此停止。

## 7. 跨路线发现

### 7.1 研究问题有真实效应量，但可观测性比预期更差

2–5° rotation drift 会显著恶化 depth，且 true-pose RAFT 可恢复到 AbsRel 0.04890，说明问题不是人为制造的，也不是 stereo backbone 完全失效。然而，单帧 texture、遮挡、动态物体和未知 depth 共同造成 rotation/depth ambiguity；translation direction 更弱可观测。多数失败发生在 calibration frontend，而不是 depth head。

### 7.2 下采样不是 rectification

纵向误差以 feature pixel 计会随 stride 下降，但 disparity、细结构和 depth resolution 同时下降。粗层能扩大搜索覆盖，却不能把二维 epipolar curve 变成真实水平线，也不能保证正确 metric depth。有效 coarse-to-fine 方法仍必须在每一级重新访问右图，并显式处理 geometry uncertainty。

### 7.3 “更多、更稠密、更稳定的点”不等于更好的 calibration

GMFlow 从 512 增到 8192 点没有改善，因为系统误差相关；CoTracker 的时间一致性也没有转化为左右相机间的 epipolar consistency。相反，LightGlue 虽然亚 0.5 px inlier rate 不高，却稳定改善 TESO。这表明 calibration 需要考虑误差方向、空间覆盖和 Jacobian influence，而不能只看 match count 或通用 EPE。

### 7.4 但 task-aware proxy 也不自动优于通用目标

CalibMatch 中 Pixel-NLL 比当前 influence losses 更稳，Budget Refinement 中简单 photometric heuristic 比 learned policy 更强。一个可微 surrogate 若与最终 optimizer 的截断、candidate selection、manifold update 和时序状态不一致，可能产生几乎正交甚至冲突的梯度。

### 7.5 视频和 foundation model 有帮助，但精度门槛不同

VGGT 9 帧比单帧改善 27.394%，说明视频先验有效；然而 calibration 需要亚 0.1°甚至更高精度，远严格于通常的 3D reconstruction/relative pose 评价。用通用 foundation model 作为 virtual target 是合理方向，但必须有 calibration-specific fine-tuning、BA 或高精度 correspondence/uncertainty model，不能直接零样本套用。

### 7.6 Online rectification 和 essential tracking 应分开做贡献判断

rectification 的主要目标是纵向对齐和下游 stereo 可用性；essential tracking 的目标是物理 $R,\hat t$。前者可以在不精确恢复每个外参自由度时仍取得好结果，后者必须面对不可观测方向和 manifold state。未来论文必须选择其中一个主问题，并用匹配的 GT/指标评价。

## 8. 实现错误、结果修正与科研诚信审计

本系列实验的价值不只在模型结果，也在于建立了几项必须长期保留的审计规则。

1. **Legacy task circularity：** 使用 GT metric depth 优化 calibration 后再声称从 weak calibration 恢复 metric depth，任务定义不成立。
2. **TESO comparator mismatch：** candidate 数量、窗口长度、step scale、灰度实现和 state projection 任一差异都可能制造“优于官方”的假结果。最终以官方 cached interface parity 为准。
3. **SciPy residual mutation：** robust `least_squares` 可原地改写 residual array；缓存若返回内部引用会污染后续诊断。修复后必须从冻结输入重跑。
4. **CARLA convention：** attached sensor pose、camera-Z depth/ray range、baseline 实际值和 (SO(3)) 投影均可能造成亚像素级或姿态级系统误差。
5. **Gate target 与表示上限：** GeoJAFAR F1 的一部分指标低于 stride-32 oracle floor。未来 gate 必须先测 representation ceiling。
6. **数据复用：** Scene Flow TEST 和多条 CARLA debug sequences 已被反复查看，不能再承担确认性结论。CalibMatch 虽有新的 formal validation，但没有 sealed final test。
7. **统计单位：** sequence 内相邻帧高度相关，不能把每帧当独立样本。正式结果应以 sequence bootstrap 和跨 seed 汇总为准。

因此，报告中的失败不是“训练没调好”的笼统判断，而是通过 oracle、shuffling、true-pose、GT-correspondence、representation floor 和公平 comparator 逐层定位后的结果。

## 9. 当前可保留资产与不可保留主张

### 9.1 值得保留

- 经审计的 geometry、$SO(3)\times S^2$、homography、baseline invariance 和 CARLA projection tests。
- 官方 TESO parity wrapper 和 cached one-to-one interface。
- LightGlue、SIFT、GMFlow、CoTracker 的公平前端比较脚本。
- CalibMatch 三个 checkpoint、无 GT 推理路径、20-sequence validation artifacts 和 bootstrap。
- VGGT Stage A/B 的冻结 manifest、cache 和修正后结果，作为高精度 calibration 对 foundation model 的负结果。
- DirectCalib、GeoJAFAR、posterior 和 budget refinement 的 gate reports，作为避免重复踩坑的 negative evidence。

### 9.2 不应继续使用的主张

- “无需 calibration”或“无需 baseline 即可恢复 metric depth”。
- “下采样等价于 rectification”。
- “JAFAR 已被证明不能用于 depth/stereo”。
- “TESO 无法做自标定”或“TESO 不能恢复 (R,t) direction”。
- “稠密 direct 方法一般不可能”，或“所有 point tracker 都对 calibration 无效”。
- “CalibMatch 已形成 calibration-influence-aware 强贡献”。
- “真实 rig 已验证”或“已完成 sealed test”。
- 任何 legacy GT-depth CalibRefine 的 headline metric/novelty claim。

## 10. 最终判断与后续重启条件

截至本报告日期，项目没有形成一条同时满足以下四项的投稿路线：

1. 相对官方强基线有跨 sequence、跨 seed、sealed-test 的显著改善；
2. 改善来自新机制而不是 matcher swap 或通用 patch refiner；
3. 在真实 rig 上有独立 GT 或至少严格下游验证；
4. 方法与已有 FLoSR、RSCE、TESO、Patch2Pix、StereoNet/HITNet/NDR 明确区分。

因此暂停是合理选择，而不是简单的“方向完全不可行”。现阶段最可靠的科学结论是：

- 小范围 rotation drift 确实是 metric stereo 的关键误差源；
- 准确姿态下的 raw/feature rectification 与现成 stereo 网络足够好；
- correspondence frontend 仍有可观改进空间；
- 但当前 calibration-aware surrogate、dense direct score、通用视频 tracker 和通用 foundation reconstruction 都未达到标定所需的闭环精度；
- 已验证的局部亚像素 refinement 收益是真实的，但新颖性不足。

若未来重启，至少应先满足一个新的外部条件：获得真实多配置 rig 数据与独立高精度外参 GT；出现比 LightGlue/EfficientLoFTR 更适合 stereo calibration 的公开 matcher；或者提出能在官方 TESO 闭环中被 oracle 明确验证、且与 Patch2Pix/RSCE 不重合的新型 calibration-specific objective。在此之前，不建议继续通过增加网络、loss 或 refinement 模块进行局部补丁式探索。

## 11. 主要内部产物与可追溯路径

以下路径为本地同步副本；服务器原始目录位于 `/data/home/huxiao/workspace/depth/`。

- Raw metric / GeoJAFAR / posterior gates：`D:\docs\论文方向探索\深度估计\raw_metric_stereo_posterior\docs\`
- TESO 公平性与跨项目结论：`D:\docs\论文方向探索\深度估计\e2e_teso_rot\docs\gates\`
- ToolE-Track：`D:\docs\论文方向探索\深度估计\toole_track\`
- VGGT pilot：`D:\docs\论文方向探索\深度估计\vggt_rig_refine\RESULTS.md`
- DirectCalibTrack：`D:\docs\论文方向探索\深度估计\directcalib_track\FINDINGS.md`
- CalibMatch 贡献审计：`D:\docs\论文方向探索\深度估计\calibmatch_teso\legacy\calibmatch_v1\docs\CONTRIBUTION_AUDIT_20260818.md`
- TESO-aware strengthening：`D:\docs\论文方向探索\深度估计\calibmatch_teso\legacy\calibmatch_v1\docs\TESO_AWARE_STRENGTHENING_AUDIT_20260818.md`
- Budget refinement：`D:\docs\论文方向探索\深度估计\budget_stereo_refinement\docs\RISK_B1_RESULT.md`
- 经验证的最小发布副本：`D:\docs\论文方向探索\深度估计\calibmatch_teso_validated\`
- GitHub 私有仓库：<https://github.com/xiahaa/calibmatch-teso-validated>

## 参考文献

1. Mayer et al. *A Large Dataset to Train Convolutional Networks for Disparity, Optical Flow, and Scene Flow Estimation*. CVPR 2016.
2. Khamis et al. *StereoNet: Guided Hierarchical Refinement for Real-Time Edge-Aware Depth Prediction*. ECCV 2018.
3. Tankovich et al. *HITNet: Hierarchical Iterative Tile Refinement Network for Real-time Stereo Matching*. CVPR 2021.
4. Aleotti et al. *Neural Disparity Refinement for Arbitrary Resolution Stereo*. 3DV 2021 / arXiv:2110.15367.
5. Zhou et al. *Patch2Pix: Epipolar-Guided Pixel-Level Correspondences*. CVPR 2021.
6. Lipson et al. *RAFT-Stereo: Multilevel Recurrent Field Transforms for Stereo Matching*. 3DV 2021.
7. Xu et al. *GMFlow: Learning Optical Flow via Global Matching*. CVPR 2022.
8. Xu et al. *UniMatch: A Unified Model for Flow, Stereo and Depth Estimation*. 2022.
9. Lindenberger et al. *LightGlue: Local Feature Matching at Light Speed*. ICCV 2023.
10. Zhao et al. *Dive Deeper into Rectifying Homography for Stereo Camera Online Self-Calibration*. arXiv:2309.10314.
11. Kumar et al. *Flow-Guided Online Stereo Rectification for Wide Baseline Stereo*. CVPR 2024.
12. Wang et al. *Efficient LoFTR: Semi-Dense Local Feature Matching with Sparse-Like Speed*. CVPR 2024.
13. Karaev et al. *CoTracker3: Simpler and Better Point Tracking by Pseudo-Labelling Real Videos*. 2024.
14. Gong et al. *Rectification-specific Supervision and Constrained Estimator for Online Stereo Rectification*. CVPR 2025.
15. Wang et al. *VGGT: Visual Geometry Grounded Transformer*. CVPR 2025.
16. Couairon et al. *JAFAR: Jack up Any Feature at Any Resolution*. NeurIPS 2025.
17. Moravec et al. *TESO: Online Tracking of Essential Matrix by Stochastic Optimization*. CVPR 2026.

---

**报告结论状态：** 部分已验证。CalibMatch endpoint refinement、官方 TESO parity、LightGlue/CoTracker 对照和多项几何单测具有直接 artifact 支持；其余内容按文中标签区分探索性、失败 gate、未运行或已推翻结果。本报告不是论文投稿稿件，也不把负结果转换为未经支持的普遍不可能性结论。

**Material Passport：** ARS academic-research-suite / technical report / 2026-08-18 / PARTIALLY VERIFIED / `stereo_calibration_exploration_report_v1`。

