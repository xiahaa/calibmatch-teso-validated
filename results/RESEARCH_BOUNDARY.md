# Research boundary

The published positive comparison is limited to frozen LightGlue endpoint
refinement followed by an all-match rotation-only tracker.

The archived project also established the following negative results:

- translation-direction recovery did not pass the 5-DoF claim gate;
- oracle selection without endpoint correction worsened rotation by 16.84%;
- learned calibration-influence supervision added only 1.97% rotation
  improvement over its matched EPE/BCE control and worsened no-drift control;
- direct differentiable TESO supervision worsened full-1024 fixed-probe step
  error by 9.79% relative to endpoint-only training;
- a 200-frame downstream-depth pilot improved AbsRel by 8.80%, below its
  pre-registered 10% threshold;
- the full pre-registered CalibMatch paper route was therefore paused, and the
  sealed test split was not accessed.

These boundaries are part of the release so that the positive endpoint result
is not misread as evidence for the rejected claims.

