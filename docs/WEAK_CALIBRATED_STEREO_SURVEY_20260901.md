# 弱标定双目深度、在线自标定与通用三维基础模型：综合调研

> 版本：2026-09-01  
> 整理范围：服务器 `/data1/czy/ws/survey` 中 7 份 Markdown 材料，并对若干关键近邻工作做主来源复核  
> 主题：弱标定/失标定双目、在线外参校正、自监督深度与位姿、NeRF/3DGS 联合优化、前馈三维基础模型、非校正立体匹配  
> 结论先行：**“带噪工厂标定先验 + 单次前馈 + metric depth + 显式外参精修”在本次检索范围内仍未发现完全同构方法，但它不是一个宽阔、低风险的空白。SESC、MapAnything/Pow3R/OmniVGGT、TESO、StereoBench、StereoGeo、HomoDepth 与 Unrectified-Stereo 已从不同方向覆盖其大部分组成能力。若方法只是把这些组件拼接，创新性不足；必须证明一种现有方法不能替代的新机制和稳定收益。**

---

## 1. 文档目的与证据边界

本文不是简单拼接原始笔记，而是围绕一个统一问题重新组织证据：

> 当双目相机的内外参只近似可信，甚至因震动、温漂、机械冲击或安装误差发生漂移时，系统能否在不重新离线标定的条件下，同时恢复可靠的度量深度和可解释的相机几何？

原始材料覆盖五条研究线：

1. 经典与学习式在线双目自标定；
2. 自监督深度、运动和外参联合学习；
3. NeRF/3D Gaussian Splatting 中相机与场景联合优化；
4. DUSt3R、VGGT、MapAnything 等前馈三维基础模型；
5. 现代立体基础模型、未校正双目与异步成像。

为避免把“没有检索到”写成“客观不存在”，本文采用以下证据等级：

| 等级 | 含义 | 本文用法 |
|---|---|---|
| A | 已用论文主页、arXiv、CVF 或出版社页面复核 | 可作为事实陈述 |
| B | 来自 `/survey` 原始材料及其论文链接，但本文未逐篇重新核对全文 | 作为高可信综述信息，涉及精确数字时保留谨慎措辞 |
| C | 机制由摘要、二手材料或相邻工作推断 | 明确标注“推断/待核实” |
| N | 负面检索结论，例如“未发现同类方法” | 只能解释为检索时点和关键词范围内未发现，不能证明不存在 |

时间边界为 **2026-09-01**。2026 年部分论文仍处于预印本、会议刚发表或数据库尚未完整收录阶段，因此创新性判断必须随投稿前检索更新。

---

## 2. 问题定义：先区分五个经常混用的任务

### 2.1 标准校正双目深度

输入为经过极线校正的左右图像，通常假设焦距 `f`、基线 `b` 和相对位姿准确。网络输出水平视差 `d`，度量深度由

\[
Z = \frac{fb}{d}
\]

得到。FoundationStereo、MonSter、DEFOM-Stereo、Stereo Anywhere、S²M² 等主要属于此类。它们可以具有很强的跨域泛化能力，但几何输入错误会直接污染深度尺度和匹配约束。

### 2.2 在线外参自标定或在线校正

目标是从当前帧或连续序列恢复双目相对姿态，常用本质矩阵、基础矩阵、校正单应或低维外参残差表示。输出通常是 `R,t`、本质矩阵 `E`，或可用于重校正的单应矩阵。TESO、FloSR、Ling & Shen、Zhao et al.、Gong et al. 属于此类。

关键点是：**标定精度和下游深度精度相关，但标定方法本身通常不负责生成最终稠密深度。**

### 2.3 非校正或标定鲁棒的双目深度

目标是在左右图没有严格水平极线约束时仍预测深度。常见做法包括二维相关、光流式匹配、学习校正单应、频域抑制垂直错位，以及使用已知位姿的 posed stereo/MVS。

这里必须区分：

- “输入无需预先校正”不等于“估计了真实相机外参”；
- “对标定误差鲁棒”不等于“修正了标定”；
- 输出二维视差或隐式单应不等于输出物理可解释的 `SE(3)` 外参。

### 2.4 自监督深度—位姿—外参联合学习

此路线把图像重投影或光度一致性作为监督，同时学习深度、车辆/相机运动，有时也学习刚性多相机外参。SESC 是与本主题最重要的直接先例：它明确联合学习深度、位姿和外参，而不是单纯做校正预处理。

### 2.5 通用前馈三维重建与相机恢复

DUSt3R/MASt3R/VGGT/MapAnything 等从一张或多张图像直接回归点图、深度、射线、相机和尺度。这一类模型可以绕过传统双目视差管线，但它们处理的是更一般的多视图几何，未必达到长期在线双目标定所需的亚像素或极小角度稳定性。

---

## 3. 统一评价坐标系

一个方法是否真正解决“弱标定双目”问题，应至少从以下维度评价，而不能只看深度榜单：

| 维度 | 核心问题 |
|---|---|
| 输入几何 | 无标定、精确标定、带噪先验，还是只给内参/基线？ |
| 输出几何 | 隐式校正、二维视差、`F/E`、单应，还是显式 `SE(3)`？ |
| 深度尺度 | 相对尺度、数据驱动 metric、由焦距/基线物理锚定，还是由速度/IMU锚定？ |
| 推理模式 | 单帧/单对前馈、滑窗跟踪、每场景优化，还是每数据域重新训练？ |
| 可观性 | 纯旋转、低纹理、重复纹理、动态物体、小视差、弱重叠时是否退化？ |
| 鲁棒性 | 是否专门在旋转、平移、内参误差、时序不同步、rolling shutter 下评估？ |
| 不确定性 | 是否输出置信度或外参协方差，并能拒绝不可靠更新？ |
| 工程代价 | 延迟、显存、训练数据、是否需速度/IMU、是否可在线运行？ |
| 评测闭环 | 是否同时报告外参误差、极线误差、深度误差及时间稳定性？ |

这套坐标系解释了为什么很多表面相似的工作并不能互相替代。

---

## 4. 研究谱系一：在线双目自标定与在线校正

### 4.1 经典几何路线

早期车载立体自标定通常从稀疏特征和对极约束出发，通过递推估计、滤波或局部优化跟踪相机参数。Dang、Hansen、Warren、Ling & Shen 等工作奠定了长期在线跟踪的基本范式：

- 从当前或短时窗内的跨相机匹配构造对极残差；
- 对少量外参自由度迭代优化；
- 利用时间平滑抑制单帧噪声；
- 以垂直视差、对极误差或重投影误差作为校正质量指标。

这一路线的优点是物理可解释、参数少、部署代价低。弱点也很明确：它依赖匹配质量和场景几何；在低纹理、动态遮挡、重复结构、弱重叠或运动退化场景中，更新可能不稳定。

Ling & Shen 的高精度在线无靶标双目外参标定、ICRA 2024 的校正单应分解工作，说明经典几何仍能达到很高的校正精度。[Ling & Shen](https://arxiv.org/abs/1903.10705)；[Zhao et al.](https://arxiv.org/abs/2309.10314)

### 4.2 现代匹配器与几何优化结合

近年的改进不是完全抛弃几何，而是把更强的学习匹配或光流用于构造更稳定的残差：

- **FloSR（CVPR 2024）**：使用流引导的在线宽基线立体校正，重点解决大基线下对应和校正耦合问题。[论文](https://openaccess.thecvf.com/content/CVPR2024/papers/Kumar_Flow-Guided_Online_Stereo_Rectification_for_Wide_Baseline_Stereo_CVPR_2024_paper.pdf)
- **Gong et al.（CVPR 2025）**：引入面向校正任务的监督和受约束估计器，把匹配训练目标与最终校正质量对齐。[论文](https://openaccess.thecvf.com/content/CVPR2025/html/Gong_Rectification-specific_Supervision_and_Constrained_Estimator_for_Online_Stereo_Rectification_CVPR_2025_paper.html)
- **TESO（CVPR 2026）**：在本质矩阵流形上优化核相关损失，采用自适应在线随机优化，不依赖针对数据域的训练。其主来源报告 MAN TruckScenes 上关键旋转轴约 `0.12°` 精度，修正 KITTI 参考标定后可达约 `0.025°`；这些数字应和数据集、轴向及参考标定条件一并引用。[arXiv](https://arxiv.org/abs/2604.19420)

TESO 是非常重要的基线，因为它表明：**对于只有少量自由度的在线双目外参跟踪，精心设计的鲁棒几何目标可能比大型网络更经济，也能达到竞争性精度。** 因此，任何“基础模型驱动的外参精修”都必须证明其收益超过 TESO 类强几何基线，而不能只与固定标定或普通 RANSAC 比较。

### 4.3 在线校正路线解决了什么、没有解决什么

已解决或较成熟的部分：

- 旋转漂移和垂直视差可在时间上稳定跟踪；
- 强匹配器可提高宽基线、弱纹理情况下的鲁棒性；
- 外参可用低维、可解释方式更新；
- 无需训练或只需有限训练即可部署。

仍然薄弱的部分：

- 外参误差和现代深度网络的最终误差并非总是单调对应；
- 单帧/单对的平移尺度和某些旋转自由度存在天然可观性限制；
- 多数方法把“先校正、再深度”作为串联流程，没有对深度和标定之间的反馈进行统一建模；
- 很少同时给出外参误差、深度误差、置信区间和错误更新拒绝机制。

---

## 5. 研究谱系二：自监督深度、运动与外参联合学习

### 5.1 从 SfMLearner 到多相机 metric depth

SfMLearner、Monodepth2、PackNet-SfM、SC-Depth 等奠定了从视频光度一致性联合学习深度与相机运动的范式。单目视频的核心困难是尺度歧义，因此后续工作通过双目基线、车辆速度、IMU、相机高度或语义先验恢复 metric scale。

这一分支的重要经验是：

1. 光度损失不是纯几何真值，受遮挡、动态物体、反射、曝光变化影响；
2. 深度与位姿可以相互补偿，从而得到低光度误差但错误的几何；
3. 要获得 metric depth，必须引入可识别的尺度锚点；
4. 多摄像头刚性约束能提供额外监督，但也会把错误标定传播到深度。

### 5.2 SESC 是不能忽略的直接先例

**Robust Self-Supervised Extrinsic Self-Calibration（SESC，IROS 2023）**基于自监督单目深度和 ego-motion 学习，借助速度监督估计多相机外参，并在课程学习中联合优化外参、深度与位姿。论文在 DDAD 等车载多相机场景验证，并展示外参自标定能改善深度。[论文](https://arxiv.org/abs/2308.02153)

因此，以下宽泛表述是不准确的：

> “此前没有任何工作同时学习深度和显式外参。”

更准确的边界是：

> 在本次材料与复核范围内，尚未找到一个明确以**带噪工厂双目外参为输入条件**、在**单次或低延迟前馈**中输出**metric depth 与该先验的显式 `SE(3)` 残差修正**、并针对多级失标定做系统评测的方法。SESC 已覆盖“深度 + 显式外参联合学习”，但依赖运动序列、速度监督、课程训练和特定多相机自监督设定，不等同于上述问题。

这一区分会显著压缩可声明的创新空间。

### 5.3 标定条件化深度

CAM-Convs、BEVDepth、UniDepth、Metric3D v2、HomoDepth、CoL3D 等说明相机参数可以作为网络条件：

- **CAM-Convs**把内参编码为空间通道，提高跨相机泛化；
- **BEVDepth**显式使用相机模型把图像特征提升到三维空间；
- **UniDepth/Metric3D 系列**试图区分相机几何和场景深度；
- **HomoDepth**预测校正单应并直接处理不稳定双目，减少预处理延迟；
- **CoL3D**协同学习单目深度和内参。

但“使用标定作为条件”仍有两个层次：

- 条件被视作准确值，网络学习如何利用它；
- 条件本身带噪，网络需要识别其可信度、修正它或在必要时忽略它。

本主题真正关心的是第二层，而现有大量条件化模型主要解决第一层。

---

## 6. 研究谱系三：NeRF/3DGS 中的相机—场景联合优化

### 6.1 从 BARF 到无位姿 NeRF

BARF、SC-NeRF、NeRF--/NeRFmm、GARF、NoPe-NeRF、SPARF、Cameras as Rays 等把相机位姿甚至内参作为可优化变量，与辐射场一起通过渲染误差求解。

代表性思路包括：

- **BARF**：粗到细位置编码，改善相机位姿与场景表示的联合优化盆地；
- **SC-NeRF**：联合估计相机参数与辐射场；
- **NeRF--/NeRFmm**：在未知相机参数下优化 NeRF；
- **GARF**：通过更平滑的激活改善几何优化；
- **NoPe-NeRF/SPARF**：使用单目深度或稀疏对应约束缓解纯光度目标的局部极值；
- **Cameras as Rays**：以射线形式统一相机表示，便于学习相机和场景的耦合关系。

核心链接：[BARF](https://arxiv.org/abs/2104.06405)、[SC-NeRF](https://arxiv.org/abs/2108.13826)、[NeRFmm](https://arxiv.org/abs/2102.07064)、[GARF](https://arxiv.org/abs/2204.05735)、[NoPe-NeRF](https://arxiv.org/abs/2212.07388)、[SPARF](https://arxiv.org/abs/2211.11738)、[Cameras as Rays](https://arxiv.org/abs/2402.14817)。

### 6.2 3DGS 与前馈初始化

CF-3DGS、InstantSplat、ZeroGS、NoPoSplat、FLARE、LongSplat、GloSplat 等逐渐把“无 COLMAP/弱位姿”重建转向更强的学习初始化和后续优化：

- 前馈三维模型先给出点图、深度或相机初值；
- 3DGS/渲染优化负责高频外观和场景一致性精修；
- 长序列工作再引入分块、图优化或全局对齐。

这反映出一个稳定趋势：**前馈基础模型正在替代脆弱的随机或单位位姿初始化，但没有完全替代几何/渲染优化。**

代表链接：[CF-3DGS](https://arxiv.org/abs/2312.07504)、[InstantSplat](https://arxiv.org/abs/2403.20309)、[NoPoSplat](https://arxiv.org/abs/2410.24207)、[FLARE](https://arxiv.org/abs/2502.12138)、[LongSplat](https://arxiv.org/abs/2508.14041)、[GloSplat](https://arxiv.org/abs/2603.04847)。

### 6.3 为什么 NeRF/3DGS 不是弱标定双目深度的自然主干

从原始材料和任务结构看，NeRF/3DGS 更适合作为“优化思想来源”而非首选主干：

- 双目在线标定只有少量外参自由度，却要在 NeRF/3DGS 中同时优化庞大的场景表示，变量规模不匹配；
- 纯光度目标存在深度、位姿、外观互相补偿，尤其在小基线、动态和非朗伯表面上不稳定；
- 多数无位姿 NeRF/GS 关注新视角合成或完整场景重建，而不是低延迟稠密深度；
- 单场景迭代优化通常不满足在线部署需求；
- 单目或无标定重建仍存在尺度和坐标系自由度，不能自动提供物理基线约束下的 metric depth。

NeRF/GS 对本题最有价值的启发是：

1. 使用粗到细优化和稳健损失扩大位姿收敛域；
2. 用渲染或多视图一致性作为训练时的辅助监督；
3. 前馈初值后接少量可微优化，比纯前馈或从零迭代更可能稳定；
4. 显式处理尺度、坐标规约和 gauge freedom。

目前在本次检索范围内，没有发现以固定双目刚体的在线外参漂移和最终深度为主要目标的主流 NeRF/3DGS 方法。这是 **N 级负面检索结论**，不是“不可能”的证明。

---

## 7. 研究谱系四：前馈三维基础模型

### 7.1 DUSt3R、MASt3R、MUSt3R

DUSt3R 把两视图三维重建转化为点图回归，显著降低了传统 SfM/MVS 对显式匹配、三角化和相机标定的依赖。MASt3R 强化了匹配能力，MUSt3R 扩展到多视图共同推理。

它们的重要贡献不是达到工业双目标定精度，而是改变了系统接口：图像对可以直接产生稠密三维对应、相对几何和置信度，随后再由全局对齐或优化恢复相机。

局限包括：

- 原生点图往往存在尺度或坐标规约问题；
- 两视图大视角、低重叠和极端长基线仍可能失败；
- 直接相机恢复精度未必满足亚像素校正；
- 大模型置信度不等于经过校准的物理不确定性；
- 针对专用相机阵列通常仍需后端优化。

链接：[DUSt3R](https://arxiv.org/abs/2312.14132)、[MASt3R](https://arxiv.org/abs/2406.09756)、[MUSt3R](https://arxiv.org/abs/2503.01661)、[MASt3R-SfM](https://arxiv.org/abs/2409.19152)。

### 7.2 VGGT、π3、Fast3R 与后续系统

VGGT 统一输出相机、深度、点图和跟踪；π3强调置换等变的多视图几何学习；Fast3R追求高吞吐前馈重建。它们证明了“大规模数据 + 统一几何 token + 多任务监督”可以形成通用三维先验。

但弱标定双目有比通用三维重建更苛刻的局部目标：外参变化可能只有零点几度，却足以造成明显垂直视差和远距离深度偏差。通用模型平均意义上的相机精度，并不自动转化为可靠的在线校正精度。

链接：[VGGT](https://arxiv.org/abs/2503.11651)、[π3](https://arxiv.org/abs/2507.13347)、[Fast3R](https://arxiv.org/abs/2501.13928)、[Reloc3r](https://arxiv.org/abs/2412.08376)、[VGGT-SLAM](https://arxiv.org/abs/2505.12549)。

### 7.3 先验条件化模型：Pow3R、MapAnything、OmniVGGT

这是与“带噪标定先验”最接近的一组工作。

**Pow3R（CVPR 2025）**接受图像以及任意组合的内参、相对位姿、稠密/稀疏深度等辅助信息；训练时随机选择模态子集，使单一网络能在不同先验可用性下工作。它证明了相机和场景先验可以有效条件化 DUSt3R 系模型。[论文](https://arxiv.org/abs/2503.17316)

**MapAnything（3DV 2026）**接受一张或多张图像，以及可选的内参、位姿、深度或局部重建，直接回归度量场景几何和相机。其因子化输出包括深度、局部射线、相机位姿和 metric scale，是本题最完整的通用主干之一。[论文](https://arxiv.org/abs/2509.13414)

**OmniVGGT（CVPR 2026）**通过 GeoAdapter 将深度、内参和外参注入 VGGT，并在训练中随机采样模态组合，从而支持任意辅助几何输入。[论文](https://arxiv.org/abs/2511.10560)

三者共同削弱了“首次把标定输入三维基础模型”的创新说法。剩余可讨论的边界只能是：

- 先验不是准确值，而是带已知或未知分布的噪声；
- 模型不只利用先验，而要输出相对于先验的校正残差；
- 校正结果要在物理双目尺度和时间稳定性上可验证；
- 必须有“错误先验不如不给先验”的防护和置信度门控。

### 7.4 MapAnything 代码级可行性审计

服务器材料中对 MapAnything 做了较深入的代码审计，其结论可概括如下：

- 输入端能够接收 intrinsics/rays、depth、camera poses 和 metric-scale 标记；
- 各模态编码后以加性方式融合到 token，再进入多视图 Transformer；
- 输出包含 pose、depth、rays、confidence/mask 和 scale 相关分支；
- 双目相对位姿应由 `inv(T_w_left) @ T_w_right` 恢复，必须统一坐标约定；
- 若增加外参残差头，适合从与 pose head 相近的特征读取，而不是仅从最终深度图反推；
- 训练噪声应在相对位姿转换后、pose encoding 前注入，确保“观测到的是有噪先验，监督的是正确几何”；
- 适合先做冻结主干、只训练残差头或 LoRA 的低成本试验，再决定是否全量微调。

材料还记录了一项重要内部观察：在受测样本中，对输入 pose 施加约 `2°` 噪声可使深度中位量级变化约 `20%` 以上，说明模型会强烈信任几何条件，而不会天然修正错误条件。该结果是项目环境中的小规模诊断，不应当作论文级普遍结论，但它足以否定一个危险假设：

> “通用模型见过模态 dropout，所以自然会对带噪标定鲁棒。”

模态缺失增强和连续噪声增强不是同一件事。前者教模型在没有条件时工作，后者才可能教模型判断条件可信度和修正条件。

---

## 8. 研究谱系五：现代立体基础模型与未校正双目

### 8.1 校正双目基础模型

| 方法 | 主要输入 | 主要输出 | 对标定的假设 | 与本题关系 |
|---|---|---|---|---|
| FoundationStereo | 校正立体对 | 视差 | 依赖准确校正；metric 需 `f,b` | 强零样本深度基线，不估外参 |
| Fast-FoundationStereo | 同上 | 视差 | 同上 | 实时强基线 |
| MonSter / MonSter++ | 立体对，部分模式需已知 pose | 视差/深度 | rectified 或 posed MVS | 单目先验增强，但不修正 pose |
| DEFOM-Stereo | 校正立体对 | 视差 | 精确校正 | 深度基础模型先验注入 |
| Stereo Anywhere | 校正立体对 | 视差 | 精确校正 | 非朗伯和单目/立体互补 |
| S²M² | 校正立体对 | 视差、遮挡、置信度 | 精确校正 | 强全局匹配与可靠性估计 |
| UniMatch | 图像对 + 已知内参/位姿 | metric depth | 位姿为已知输入 | 支持 unrectified posed stereo，但不精修位姿 |

FoundationStereo 使用约百万规模的合成立体数据和自筛选流程，目标是跨域零样本立体匹配；其主来源明确仍是“stereo depth estimation”，并未引入在线外参恢复。[论文](https://arxiv.org/abs/2501.09898)

### 8.2 HomoDepth：学习单应而非显式外参

HomoDepth 针对 AR 眼镜中的不稳定双目系统，预测单应并引入 rectification positional encoding，从而取消传统校正预处理。其论文报告降低端到端延迟并提高错位输入下的深度精度。[论文](https://arxiv.org/abs/2411.10013)

它与“外参精修”的区别在于：单应是服务于图像对齐和深度推理的中间表示，不一定对应唯一、稳定、可解释的物理 `SE(3)`。如果下游只需要深度，这种隐式校正可能已经足够；如果系统还需要标定状态监控、跨模块共享或安全验证，则显式外参更有价值。

### 8.3 Unrectified-Stereo：二维视差，但不输出外参

Pattern Recognition 2026 的 **Unrectified-Stereo**直接在原始图像域预测水平和垂直二维视差，通过单目深度先验、深度增强相关和双分支迭代实现深度—视差互相修正；其正式页面还提供由 Scene Flow、ETH3D、KITTI 2012/2015 转换的未校正评测集，垂直视差最高覆盖到约 22 像素。[出版社页面](https://www.sciencedirect.com/science/article/pii/S0031320326010344)

这项工作封堵了“首次直接处理未校正双目并输出深度”的表述，但它仍不等于双目外参自标定：二维视差是稠密对应场，不是固定刚体外参。

### 8.4 StereoBench：问题设定层面的直接邻近

**StereoBench（CVPR 2026 Workshop 3DMV）**统一评测 26 个方法变体和 10 个数据集，核心发现是：许多专用立体方法在高质量标定基准上很强，却在真实世界立体数据上明显退化；经典在线校正并不能完全弥补这一差距，而把 VGGT、π3、MapAnything 等多视图几何模型改造成 stereo predictor 往往更稳健。[论文](https://openaccess.thecvf.com/content/CVPR2026W/3DMV/papers/Tan_Benchmarking_Stereo_Geometry_Estimation_in_the_Wild_CVPRW_2026_paper.pdf)

它是本题必须正面讨论的工作，因为它已经把“真实弱标定导致专用 stereo 失效”和“用通用三维基础模型规避标定依赖”讲得非常直接。其边界是：benchmark 与 calibration-robust prediction 不等于利用工厂先验并显式修正外参。

### 8.5 StereoGeo：输出标定，但不输出深度

**StereoGeo（EUSIPCO 2026）**从左右图像预测焦距、重力方向和相对外参，使用深层特征与可微优化器实现端到端双目标定。[论文](https://arxiv.org/abs/2606.14619)

它封堵了“首次端到端双目标定网络”的表述。其与目标组合的差别是没有以最终稠密 metric depth 为联合输出。因此它既是外参头的强基线，也是一个明显风险：若 `StereoGeo + FoundationStereo` 的简单串联就能达到相同效果，则联合模型的贡献不成立。

---

## 9. 关键近邻方法能力矩阵

符号：`✓` 明确具备；`△` 部分具备或通过后处理得到；`—` 不属于其主要能力；`?` 需进一步核实。

| 方法 | 无/弱标定输入 | 使用已有 pose 先验 | 显式外参输出 | 稠密深度 | metric | 单次前馈 | 专门建模先验噪声 |
|---|---:|---:|---:|---:|---:|---:|---:|
| SESC | ✓ | △（刚性结构/初始化） | ✓ | ✓ | ✓（速度锚定） | —（序列/课程学习） | — |
| TESO | ✓ | ✓（在线状态） | ✓（E/外参） | — | — | —（在线优化） | ✓（鲁棒跟踪意义） |
| FloSR / Gong et al. | ✓ | △ | △（校正表示） | — | — | △ | △ |
| HomoDepth | ✓ | — | △（单应） | ✓ | ✓/依设置 | ✓ | ✓（错位增强） |
| Unrectified-Stereo | ✓ | — | — | ✓ | ✓/依相机尺度 | ✓ | ✓（扰动数据） |
| FoundationStereo | — | — | — | ✓ | ✓（需准确 `f,b`） | ✓ | — |
| UniMatch posed stereo | ✓ | ✓（精确 pose） | — | ✓ | ✓ | ✓ | — |
| DUSt3R/MASt3R/VGGT | ✓ | —/△ | ✓/△ | ✓ | △ | ✓ | — |
| Pow3R | ✓ | ✓ | △ | ✓ | △ | ✓ | — |
| MapAnything | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| OmniVGGT | ✓ | ✓ | ✓/△ | ✓ | △ | ✓ | — |
| StereoBench 改造 | ✓ | — | — | ✓ | △ | ✓ | 面向鲁棒评测，不做残差精修 |
| StereoGeo | ✓ | — | ✓ | — | — | ✓ + 可微优化 | △ |
| Calib3R | ✓ | ✓（机器人运动） | ✓ | ✓（重建） | ✓ | —（统一优化） | — |

最重要的观察不是某个格子是否为空，而是：**目标组合只剩最后一列和任务约束的交叉处相对稀缺。** 这使得“组合式新颖性”很脆弱。

---

## 10. 度量尺度：所有路线都绕不开的约束

### 10.1 尺度来源

| 尺度锚点 | 优点 | 风险 |
|---|---|---|
| 已知双目基线 | 物理直接、最适合稳定刚体 | 基线长度也可能受装配误差影响；方向错误会污染三角化 |
| 焦距与校正视差 | 标准且高效 | 对内参和校正误差敏感 |
| 车辆速度/IMU | 可用于自监督序列 | 依赖同步和传感器质量 |
| 相机高度/地面 | 成本低 | 依赖场景和姿态假设 |
| 数据驱动 metric prior | 单帧可用 | 可能学习数据集统计，不是物理尺度保证 |
| 已知深度/稀疏点 | 稳定、可校准 | 需要额外传感器或人工测量 |
| 多视图/机器人运动链 | 能统一 camera-to-robot | 需要准确运动和时间同步 |

### 10.2 “metric”一词的三种不同含义

1. **物理锚定 metric**：通过已知基线、速度或传感器得到真实单位；
2. **训练得到 metric**：模型直接预测米制深度，但可能受训练分布影响；
3. **对齐后 metric**：预测本身尺度自由，评测时用 GT 或已知量对齐。

调研和论文中必须说明使用哪一种。把 scale-aligned depth 写成“metric depth”会夸大系统能力。

---

## 11. 失标定、未校正与异步成像的关系

### 11.1 外参扰动

旋转扰动通常比小幅基线长度误差更快地产生垂直视差和对应搜索偏离，尤其是 pitch/yaw 方向。平移方向和长度则直接影响三角化尺度。评测不应只使用单一高斯噪声，而应分轴、分幅度报告。

### 11.2 内参误差

焦距、主点和畸变误差会与外参误差共同表现为残余极线误差。TESO 对 KITTI 参考标定不一致的分析提醒我们：只优化外参却假设内参绝对准确，可能把一部分内参错误吸收到外参中。

### 11.3 时间不同步与 rolling shutter

当平台或物体运动时，左右曝光时间差会让静态双目几何失效；rolling shutter 又使同一图像不同行拥有不同位姿。这些效应可能看起来像外参漂移，但不能由固定 `SE(3)` 完全解释。

因此，一个声称“在线自标定”的方法必须至少有异常检测：如果残差来自同步/rolling shutter，盲目更新固定外参可能产生错误的长期状态。相关分支包括 rolling-shutter stereo 几何和 event stereo。[rolling-shutter relative pose](https://arxiv.org/abs/2006.07807)；[event stereo survey](https://arxiv.org/abs/2409.17680)

---

## 12. 数据集与评测协议建议

### 12.1 数据类型

| 类型 | 代表数据/构造方式 | 适合回答的问题 |
|---|---|---|
| 标准高质量立体 | KITTI 2012/2015、ETH3D、Middlebury、Scene Flow | 正常标定下的上限性能 |
| 合成失标定 | 对图像/相机施加可控 `SE(3)`、内参和畸变扰动 | 收敛域、分轴敏感性、可恢复上限 |
| 真实长期车载 | KITTI raw、DDAD、MAN TruckScenes 等 | 温漂、震动、跨帧稳定性和参考标定偏差 |
| 未校正 benchmark | Unrectified-Stereo 转换集、StereoBench 数据组合 | 真实/合成错位下的深度泛化 |
| 宽基线与低重叠 | 专门宽基线/稀疏视图数据 | 匹配和通用几何先验的失败边界 |
| AR/可变结构 | HomoDepth 场景 | 紧凑设备、延迟和机械不稳定 |

### 12.2 必须联合报告的指标

**外参指标**：旋转误差、平移方向误差、基线长度误差；最好按轴报告并提供时间序列。

**校正指标**：垂直视差、Sampson error、对极线距离、重校正后有效视野和重采样代价。

**深度指标**：AbsRel、RMSE、`δ1`、坏点率、尺度误差；近场和远场分别报告。

**可靠性指标**：置信度校准误差、失败检测 AUROC、错误更新率、漂移恢复时间。

**工程指标**：延迟、显存、参数量、滑窗长度、初始化时间、额外传感器依赖。

### 12.3 最小扰动网格

建议至少覆盖：

- 旋转：roll/pitch/yaw 分别从很小漂移到明显失配；
- 平移：基线长度与方向分别扰动；
- 内参：焦距、主点、畸变独立扰动；
- 组合扰动：模拟真实装配误差；
- 时间误差：不同速度下的左右帧偏移；
- 图像条件：低纹理、重复纹理、动态、曝光差、雨雾和非朗伯表面。

每个扰动点都应比较“准确标定上界、错误标定直接推理、不用标定的鲁棒模型、显式在线校正后推理、联合模型”五种设置。

---

## 13. 对原始创新性主张的修正

### 13.1 不能再使用的宽泛主张

- “首次联合深度与外参”：SESC 已经覆盖。
- “首次把相机先验输入三维基础模型”：Pow3R、MapAnything、OmniVGGT 已经覆盖。
- “首次处理未校正双目深度”：HomoDepth、UniMatch posed stereo、Unrectified-Stereo 等已经覆盖不同版本。
- “首次端到端双目标定”：StereoGeo 等已经覆盖。
- “经典在线校正不能应对真实数据，所以深度基础模型必然更好”：StereoBench 给出有力证据，但其结论依赖数据和评测协议，不能外推为所有场景的定理。

### 13.2 仍可谨慎陈述的窄边界

截至本次检索时点，未发现完全同构的以下设定：

> 给定左右图像与可能存在偏差的工厂内外参及其不确定性，网络在一次前馈或极少迭代内输出物理尺度深度、显式双目 `SE(3)` 校正残差和经校准的可信度；训练和评测覆盖多幅度失标定、内参与外参耦合、同步误差，并证明错误先验不会导致负迁移。

这只是一个任务定义缺口，不自动等于方法创新。它至少需要下列之一才能成为论文贡献：

1. 有理论或结构依据的噪声条件化/可信度门控机制；
2. 能稳定超过 `StereoGeo + 强 stereo`、`TESO + 强 stereo`、MapAnything 直接输出等简单组合的联合推理机制；
3. 新的真实失标定数据或可复现 benchmark；
4. 对“何时应修正先验、何时应忽略先验”的可验证不确定性建模；
5. 明确的在线状态更新与灾难性错误更新防护。

### 13.3 创新风险评级

| 可能贡献 | 新颖性风险 | 原因 |
|---|---|---|
| 给 MapAnything 加一个 6-DoF residual head | 很高 | 容易被视为直接结构改造；MapAnything 本身已输出相机和深度 |
| 用 LoRA 在合成扰动上微调 | 很高 | LoRA3D 等已证明低秩适配；训练技巧不是任务级创新 |
| 把 noisy pose 作为 augmentation | 高 | 合理但常规，除非有系统理论与大规模证据 |
| 显式不确定性门控 + 物理约束的联合估计 | 中 | 需要证明不确定性经过校准且能防止负更新 |
| 新真实失标定 benchmark + 强基线谱系 | 中低 | 数据真实性、可复现性和覆盖面决定价值 |
| 在线闭环、长期漂移恢复与安全拒绝 | 中 | 与单对前馈不同，工程和时序贡献可能成立 |

---

## 14. 如果继续研究，最严格的可行性门槛

本节不是投稿方案，而是判断该方向是否值得继续投入的停止条件。

### 14.1 三组不可缺少的强基线

1. **先标定后深度**：TESO、FloSR、Gong/StereoGeo + FoundationStereo/MonSter；
2. **直接鲁棒深度**：HomoDepth、Unrectified-Stereo、StereoBench 中的 VGGT/π3/MapAnything stereo 变体；
3. **通用联合几何**：MapAnything、Pow3R、OmniVGGT、VGGT 直接预测相机与深度。

### 14.2 必须出现的结果形态

- 不仅在大扰动上恢复，也要在接近正常标定的小扰动上不伤害性能；
- 对错误先验的结果优于“不给先验”和“直接使用先验”；
- 显式外参更准，并且这种提升确实转化为深度提升；
- 真实失标定上成立，而不是只在合成旋转上成立；
- 对未知噪声幅度、跨相机和跨数据域有稳定性；
- 失败时能拒绝更新，而不是输出高置信错误校正。

### 14.3 建议停止的信号

- 简单 `StereoGeo/TESO + stereo FM` 已达到或超过联合模型；
- MapAnything 直接无标定推理比“带噪先验条件化”更稳；
- 外参指标改善但深度不改善，说明显式外参不是瓶颈；
- 仅在合成扰动或单一数据集有效；
- 小扰动下频繁负迁移；
- 需要大规模专用训练，却只得到很小增益。

从综述角度看，这个方向不是物理上不可行，但**作为只靠模型改造的投稿选题，已经属于高风险、边界狭窄的方向**。若没有真实 benchmark、明确的可靠性机制或显著优于串联系统的结果，放弃该投稿方向是合理决策。

---

## 15. 跨路线综合判断

### 15.1 已经基本成立的共识

1. 准确校正仍然是专用立体网络的重要前提，真实数据中的标定质量差异会显著影响深度。
2. 通用三维基础模型为无/弱标定输入提供了更大收敛域，但不保证高精度物理外参。
3. 强学习对应与小规模几何优化的混合方案仍然非常有竞争力。
4. 光度/渲染优化能精修，但初始化、尺度和动态场景决定其稳定性。
5. 使用几何先验和对几何先验噪声鲁棒是两个不同问题。
6. 未校正深度、隐式图像校正和显式相机自标定是三个不同的输出目标。

### 15.2 当前最缺的不是另一个 backbone

现有生态已经拥有：

- 强零样本立体 backbone；
- 强通用三维 backbone；
- 在线本质矩阵跟踪；
- 端到端标定网络；
- 未校正二维视差网络；
- 可条件化的相机/深度先验输入。

真正薄弱的是统一、可信的评测闭环：**在真实可变标定条件下，输入先验何时有益、何时有害、是否应更新，以及更新后深度是否真正改善。** 因此，benchmark、可靠性估计和长期状态管理可能比“再加一个头”更有研究价值。

### 15.3 对“基础模型 + 标定残差头”路线的最终评价

技术可实现性：高。MapAnything 的输入输出接口和代码结构允许增加条件噪声与残差头。

科学可辨识性：中低。深度、位姿、内参和尺度可以互相补偿，单对图像尤其存在退化。

创新性：低到中，取决于是否提出超越组件拼接的新机制。

工程价值：在相机长期运行、标定状态可监控、系统需要显式外参共享时可能较高。

投稿风险：高。近邻工作密集且 2026 年仍在快速增长；必须用强基线和真实证据收紧主张。

---

## 16. 核心文献索引

### 16.1 在线标定与校正

- Ling & Shen, *High-Precision Online Markerless Stereo Extrinsic Calibration*, IROS 2016. https://arxiv.org/abs/1903.10705
- Zhao et al., *Dive Deeper into Rectifying Homography for Stereo Camera Online Self-Calibration*, ICRA 2024. https://arxiv.org/abs/2309.10314
- Kanai et al., *Robust Self-Supervised Extrinsic Self-Calibration*, IROS 2023. https://arxiv.org/abs/2308.02153
- Kumar et al., *Flow-Guided Online Stereo Rectification for Wide Baseline Stereo*, CVPR 2024. https://openaccess.thecvf.com/content/CVPR2024/papers/Kumar_Flow-Guided_Online_Stereo_Rectification_for_Wide_Baseline_Stereo_CVPR_2024_paper.pdf
- Gong et al., *Rectification-specific Supervision and Constrained Estimator for Online Stereo Rectification*, CVPR 2025. https://openaccess.thecvf.com/content/CVPR2025/html/Gong_Rectification-specific_Supervision_and_Constrained_Estimator_for_Online_Stereo_Rectification_CVPR_2025_paper.html
- Moravec et al., *TESO: Online Tracking of Essential Matrix by Stochastic Optimization*, CVPR 2026. https://arxiv.org/abs/2604.19420
- Meddour et al., *StereoGeo: an End-to-End Stereo Camera Calibration Method*, EUSIPCO 2026. https://arxiv.org/abs/2606.14619
- Allegro et al., *Calib3R*, 2025. https://arxiv.org/abs/2509.08813

### 16.2 前馈三维基础模型

- Wang et al., *DUSt3R: Geometric 3D Vision Made Easy*, CVPR 2024. https://arxiv.org/abs/2312.14132
- Leroy et al., *Grounding Image Matching in 3D with MASt3R*, ECCV 2024. https://arxiv.org/abs/2406.09756
- Cabon et al., *MUSt3R*, CVPR 2025. https://arxiv.org/abs/2503.01661
- Wang et al., *VGGT: Visual Geometry Grounded Transformer*, CVPR 2025. https://arxiv.org/abs/2503.11651
- Jang et al., *Pow3R*, CVPR 2025. https://arxiv.org/abs/2503.17316
- Keetha et al., *MapAnything: Universal Feed-Forward Metric 3D Reconstruction*, 3DV 2026. https://arxiv.org/abs/2509.13414
- Peng et al., *OmniVGGT*, CVPR 2026. https://arxiv.org/abs/2511.10560
- Lu et al., *LoRA3D*, 2024. https://arxiv.org/abs/2412.07746
- Dong et al., *MASt3R-SfM*, 3DV 2025. https://arxiv.org/abs/2409.19152

### 16.3 立体基础模型与未校正深度

- Wen et al., *FoundationStereo*, CVPR 2025. https://arxiv.org/abs/2501.09898
- Cheng et al., *MonSter / MonSter++*, CVPR 2025 / 2025 revision. https://arxiv.org/abs/2501.08643
- Jiang et al., *DEFOM-Stereo*, CVPR 2025. https://arxiv.org/abs/2501.09466
- Bartolomei et al., *Stereo Anywhere*, CVPR 2025. https://arxiv.org/abs/2412.04472
- Min et al., *S²M²*, ICCV 2025. https://arxiv.org/abs/2507.13229
- Xu et al., *UniMatch*, TPAMI 2023. https://arxiv.org/abs/2211.05783
- Liu & Kwon, *Efficient Depth Estimation for Unstable Stereo Camera Systems on AR Glasses (HomoDepth)*, CVPR 2025. https://arxiv.org/abs/2411.10013
- Zhang et al., *Unrectified-Stereo*, Pattern Recognition 2026. https://www.sciencedirect.com/science/article/pii/S0031320326010344
- Tan et al., *Benchmarking Stereo Geometry Estimation in the Wild (StereoBench)*, CVPRW 2026. https://openaccess.thecvf.com/content/CVPR2026W/3DMV/papers/Tan_Benchmarking_Stereo_Geometry_Estimation_in_the_Wild_CVPRW_2026_paper.pdf

### 16.4 NeRF/3DGS 相机—场景联合优化

- Lin et al., *BARF*, ICCV 2021. https://arxiv.org/abs/2104.06405
- Jeong et al., *SC-NeRF*, ICCV 2021. https://arxiv.org/abs/2108.13826
- Wang et al., *NeRF-- / NeRFmm*, 2021. https://arxiv.org/abs/2102.07064
- Chng et al., *GARF*, ECCV 2022. https://arxiv.org/abs/2204.05735
- Bian et al., *NoPe-NeRF*, CVPR 2023. https://arxiv.org/abs/2212.07388
- Truong et al., *SPARF*, CVPR 2023. https://arxiv.org/abs/2211.11738
- Zhang et al., *CF-3DGS*, CVPR 2024. https://arxiv.org/abs/2312.07504
- Fan et al., *InstantSplat*, 2024. https://arxiv.org/abs/2403.20309
- Chen et al., *NoPoSplat*, ICLR 2025. https://arxiv.org/abs/2410.24207
- Zhang et al., *FLARE*, CVPR 2025. https://arxiv.org/abs/2502.12138

### 16.5 自监督深度与相机条件化

- Zhou et al., *Unsupervised Learning of Depth and Ego-Motion from Video*, CVPR 2017.
- Godard et al., *Digging Into Self-Supervised Monocular Depth Estimation (Monodepth2)*, ICCV 2019.
- Facil et al., *CAM-Convs*, CVPR 2019. https://openaccess.thecvf.com/content_CVPR_2019/html/Facil_CAM-Convs_Camera-Aware_Multi-Scale_Convolutions_for_Single-View_Depth_CVPR_2019_paper.html
- Li et al., *BEVDepth*, AAAI 2023. https://arxiv.org/abs/2206.10092
- Piccinelli et al., *UniDepth*, CVPR 2024.
- Hu et al., *Metric3D v2*, TPAMI 2025.
- CoL3D, *Collaborative Learning of Single-view Depth and Camera Intrinsics*, 2025. https://arxiv.org/abs/2502.08902

---

## 17. 原始材料来源与可追溯性

本文基于以下服务器文件整理：

1. `/data1/czy/ws/survey/SURVEY_SUMMARY.md`
2. `/data1/czy/ws/survey/W1_online_self_calibration.md`
3. `/data1/czy/ws/survey/W2_nerf_gs_calibration.md`
4. `/data1/czy/ws/survey/W3_feedforward_geometry_fm.md`
5. `/data1/czy/ws/survey/W4_stereo_fm_unrectified.md`
6. `/data1/czy/ws/survey/W5_selfsupervised_depth_pose.md`
7. `/data1/czy/ws/survey/MAPANYTHING_DEEP_DIVE.md`

F 盘源文件快照副本位于：

`F:\idea-research\weak-stereo\survey_source_snapshot_20260901`

本文额外复核的主来源包括 MapAnything、Pow3R、SESC、HomoDepth、FoundationStereo、OmniVGGT、TESO、StereoBench、StereoGeo 和 Unrectified-Stereo 的 arXiv/CVF/出版社页面。其余精确实验数字和 2026 年新近工作的最终发表状态，正式引用前仍建议逐篇核对最终论文版本。

---

## 18. 一句话结论

弱标定双目不是“没有人做”的空白，而是一个已被在线几何、联合自监督、未校正匹配和三维基础模型多面包围的问题；当前真正有价值且仍不充分的部分，是**带噪先验的可信使用、显式校正与深度收益的闭环证明，以及真实长期失标定下可拒绝错误更新的系统性评测**。
