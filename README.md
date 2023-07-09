# fDAL-Segmentation

# An implementation of [Toward Optimal Strategies for Training Self-Driving perception Models in Simulation](https://arxiv.org/abs/2111.07971) paper

Modifications [Fateme]

1. Reduced the number of classes to 1.
2. Model's architecture consistent with fDAL.

What are the current issues:
1. fdal loss with multiclass.
2. sampling strategies inconsistent with the paper.
3. pseudo loss not tuned for positive classes wt.
