# Perturbation generators

Per `agent-catalog.md` `evaluation-runner` v2.2 spec, every question runs with 3-5 perturbed variants. Three mandatory classes:

## Numerical perturbation
- Trigger: question contains numerical values
- Method: replace with logically-equivalent variants

## Order perturbation
- Trigger: question contains lists or ordered sequences
- Method: shuffle items that are not order-dependent

## Surface perturbation
- Trigger: every question
- Method: cosmetic rephrasings that preserve meaning

## Reporting

Per question: mean ± standard deviation of accuracy across perturbed variants. Flag questions where some perturbations pass and others fail — these are the brittleness signals.

Implementations: TBD. Scripts in this directory when written.
